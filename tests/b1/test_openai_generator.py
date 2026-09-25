"""Contract tests for OpenAICompatibleGenerator (offline, injected transport)."""

from datetime import datetime, timezone

import pytest

from presale.adapters.openai_generator import OpenAICompatibleGenerator
from presale.answer import AnswerGenerationError, GeneratorPort
from presale.contracts import ProductQuestion
from presale.knowledge import (
    DeterministicKnowledgeRetriever,
    KnowledgeSource,
)

RUN_REF = {"kind": "AgentRun", "id": "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"}


def source(*, tenant_id="tenant-demo", product_id="product-001"):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id=product_id,
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def question():
    return ProductQuestion(
        question_id="question-llm",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key="llm-key-000002",
    )


def matched_retrieval():
    return DeterministicKnowledgeRetriever([source()]).retrieve(question())


def no_evidence_retrieval():
    return DeterministicKnowledgeRetriever([source(tenant_id="tenant-other")]).retrieve(question())


def fake_transport(content="根据商品资料，适合夏季使用。", captured=None):
    def _transport(*, api_key, base_url, model, messages, timeout_s):
        if captured is not None:
            captured.update({"messages": messages, "model": model, "base_url": base_url})
        return {"choices": [{"message": {"content": content}}]}

    return _transport


def generator(transport, **kw):
    return OpenAICompatibleGenerator(
        model="gpt-test", api_key="test-key", transport=transport, **kw
    )


def test_openai_generator_conforms_to_generator_port():
    assert issubclass(OpenAICompatibleGenerator, GeneratorPort)


def test_generate_maps_llm_text_to_scoped_draft():
    captured = {}
    gen = generator(fake_transport(captured=captured))

    draft = gen.generate(
        question(), matched_retrieval(), run_ref=RUN_REF, configuration_refs={"agent_spec": "1.0.0"}
    )

    assert draft.answer_text == "根据商品资料，适合夏季使用。"
    assert draft.answer_id == f"answer-{RUN_REF['id']}"
    assert draft.question_id == "question-llm"
    assert draft.evidence_refs  # scoped evidence carried through
    assert all(ref.source_id == "catalog-001" for ref in draft.evidence_refs)
    assert draft.need_human is False
    assert draft.confidence_signal == "supported"
    # prompt built from question + evidence and sent through the transport
    assert captured["model"] == "gpt-test"
    assert any("这款商品适合夏季使用吗" in m["content"] for m in captured["messages"])


def test_no_evidence_routes_to_human_review():
    gen = generator(fake_transport(content="我无法确定"))

    draft = gen.generate(
        question(), no_evidence_retrieval(), run_ref=RUN_REF, configuration_refs={}
    )

    assert draft.need_human is True
    assert draft.confidence_signal == "unavailable"
    assert "NO_EVIDENCE" in draft.reason_codes
    assert draft.evidence_refs == []


def test_transport_failure_is_explicit():
    def boom(*, api_key, base_url, model, messages, timeout_s):
        raise RuntimeError("network down")

    with pytest.raises(AnswerGenerationError, match="LLM_CALL_FAILED"):
        generator(boom).generate(
            question(), matched_retrieval(), run_ref=RUN_REF, configuration_refs={}
        )


def test_empty_llm_response_is_explicit():
    gen = generator(fake_transport(content="   "))

    with pytest.raises(AnswerGenerationError, match="LLM_EMPTY_RESPONSE"):
        gen.generate(question(), matched_retrieval(), run_ref=RUN_REF, configuration_refs={})


def test_malformed_completion_is_explicit():
    def malformed(*, api_key, base_url, model, messages, timeout_s):
        return {"unexpected": True}

    with pytest.raises(AnswerGenerationError, match="LLM_MALFORMED_RESPONSE"):
        generator(malformed).generate(
            question(), matched_retrieval(), run_ref=RUN_REF, configuration_refs={}
        )


def test_custom_prompt_builder_is_used():
    captured = {}

    def custom_builder(question, retrieval, configuration_refs):
        return "自定义提示词-12345"

    gen = OpenAICompatibleGenerator(
        model="m",
        api_key="k",
        transport=fake_transport(captured=captured),
        prompt_builder=custom_builder,
    )

    gen.generate(question(), matched_retrieval(), run_ref=RUN_REF, configuration_refs={})

    assert any("自定义提示词-12345" in m["content"] for m in captured["messages"])


@pytest.mark.asyncio
async def test_openai_generator_plugs_into_runner():
    from presale.runner import PresaleQaRunner

    gen = OpenAICompatibleGenerator(
        model="m", api_key="k", transport=fake_transport(content="根据资料，适合夏季使用。")
    )
    runner = PresaleQaRunner(sources=[source()], generator=gen)

    result = await runner.ask(question())

    assert result.answer_draft.answer_text == "根据资料，适合夏季使用。"
    assert result.answer_draft.need_human is False
    assert result.answer_draft.evidence_refs


def test_retry_after_seconds_from_httpx_429():
    """C-5: Retry-After delta-seconds on 429 is parsed from the HTTP response."""
    import httpx

    from presale.adapters.openai_generator import retry_after_seconds

    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    resp = httpx.Response(429, headers={"Retry-After": "45"}, request=req)
    exc = httpx.HTTPStatusError("429", request=req, response=resp)
    assert retry_after_seconds(exc) == 45.0


def test_retry_after_seconds_http_date_and_ignores_other_status():
    import httpx

    from presale.adapters.openai_generator import retry_after_seconds

    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    resp = httpx.Response(
        503,
        headers={"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"},
        request=req,
    )
    exc = httpx.HTTPStatusError("503", request=req, response=resp)
    wait = retry_after_seconds(exc)
    assert wait is not None and wait > 0

    resp400 = httpx.Response(400, headers={"Retry-After": "10"}, request=req)
    exc400 = httpx.HTTPStatusError("400", request=req, response=resp400)
    assert retry_after_seconds(exc400) is None
    assert retry_after_seconds(RuntimeError("no response")) is None


def test_rate_limit_maps_to_answer_error_with_retry_after_in_message():
    """C-5: 429 becomes LLM_RATE_LIMITED retry_after=N (survives QaRuntimeError str())."""
    import httpx

    from presale.adapters.generation_eval import _retry_delay_seconds

    def limited(*, api_key, base_url, model, messages, timeout_s):
        req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
        resp = httpx.Response(429, headers={"Retry-After": "77"}, request=req)
        raise httpx.HTTPStatusError("429", request=req, response=resp)

    with pytest.raises(AnswerGenerationError, match="LLM_RATE_LIMITED retry_after=77") as exc_info:
        generator(limited).generate(
            question(), matched_retrieval(), run_ref=RUN_REF, configuration_refs={}
        )
    assert exc_info.value.retry_after == 77.0

    # Message-form propagation: the runner only keeps str(exc).
    wrapped = ValueError(str(exc_info.value))
    assert _retry_delay_seconds(wrapped, fallback=30.0) == 77.0
    # Cap at 120s.
    assert _retry_delay_seconds(ValueError("LLM_RATE_LIMITED retry_after=999"), 30.0) == 120.0
    # No header → fixed backoff.
    assert _retry_delay_seconds(ValueError("LLM_CALL_FAILED"), 30.0) == 30.0
