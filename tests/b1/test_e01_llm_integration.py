"""E-01/E-02: Real LLM integration verification.

Tests the OpenAI-compatible generator and SQLite assembly with
injected transports (no real API calls). Verifies success, failure,
idempotency, and error propagation paths.
"""

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import Harness, TerminalDecision
from presale.answer import AnswerGenerationError
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runner import QaRuntimeError
from presale.runtime import PresaleRuntimeFactory


class Registry:
    def __init__(self, objects):
        self.objects = objects

    async def list_by_filter(self, filter, limit=100, offset=0):
        return [
            obj
            for obj in self.objects
            if obj["kind"] == filter.kind
            and obj["metadata"]["namespace"] == filter.namespace
            and obj["metadata"]["key"] == filter.key
            and obj["status"]["phase"] == filter.phase
            and obj["metadata"]["scope"]["tenant_id"] == filter.tenant_id
        ]


def definition(kind, object_id, key):
    return {
        "kind": kind,
        "metadata": {
            "id": object_id,
            "key": key,
            "namespace": "presale",
            "version": "1.0.0",
            "content_digest": "sha256:" + "a" * 64,
            "scope": {"type": "tenant", "tenant_id": "tenant-demo"},
        },
        "status": {"phase": "active"},
    }


def source(*, product_id="product-001"):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id=product_id,
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def question(*, key="e01-key-0001"):
    return ProductQuestion(
        question_id="question-e01",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        idempotency_key=key,
    )


def factory():
    registry = Registry(
        [
            definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
            definition(
                "PromptPackage", "prm_01111111-1111-7111-8111-111111111111", "presale-prompt"
            ),
            definition(
                "ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111", "presale-context"
            ),
        ]
    )
    return PresaleRuntimeFactory(
        definition_repository=registry,
        definition_selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"},
            "prompt_package": {
                "kind": "PromptPackage",
                "namespace": "presale",
                "key": "presale-prompt",
            },
            "context_policy": {
                "kind": "ContextPolicy",
                "namespace": "presale",
                "key": "presale-context",
            },
        },
        sources=[source()],
    )


# --- E-01: create_openai_agent() assembly + generation ---


@pytest.mark.asyncio
async def test_create_openai_agent_assembly_finalizes():
    """E-01: create_openai_agent + fake transport → FINALIZE + answer_draft."""
    def fake_transport(*, api_key, base_url, model, messages, timeout_s):
        return {"choices": [{"message": {"content": "根据资料，适合夏季使用。"}}]}

    f = factory()
    agent = f.create_openai_agent(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="test-key",
        transport=fake_transport,
    )

    outcome = await Harness().execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert outcome.answer_draft is not None
    assert outcome.answer_draft.answer_text == "根据资料，适合夏季使用。"
    assert outcome.answer_draft.need_human is False
    assert outcome.answer_draft.evidence_refs


@pytest.mark.asyncio
async def test_create_openai_agent_empty_response():
    """E-01: LLM returns empty content → AnswerGenerationError."""
    def empty_transport(*, api_key, base_url, model, messages, timeout_s):
        return {"choices": [{"message": {"content": ""}}]}

    f = factory()
    agent = f.create_openai_agent(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="test-key",
        transport=empty_transport,
    )

    with pytest.raises(QaRuntimeError, match="LLM_EMPTY_RESPONSE"):
        await Harness().execute(question(), agent)


@pytest.mark.asyncio
async def test_create_openai_agent_malformed_response():
    """E-01: LLM returns malformed JSON → QaRuntimeError(LLM_MALFORMED_RESPONSE)."""
    def malformed_transport(*, api_key, base_url, model, messages, timeout_s):
        return {"not_choices": []}

    f = factory()
    agent = f.create_openai_agent(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="test-key",
        transport=malformed_transport,
    )

    with pytest.raises(QaRuntimeError, match="LLM_MALFORMED_RESPONSE"):
        await Harness().execute(question(), agent)


@pytest.mark.asyncio
async def test_create_openai_agent_transport_exception():
    """E-01: Transport raises → QaRuntimeError(LLM_CALL_FAILED)."""
    def failing_transport(*, api_key, base_url, model, messages, timeout_s):
        raise ConnectionError("LLM unreachable")

    f = factory()
    agent = f.create_openai_agent(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="test-key",
        transport=failing_transport,
    )

    with pytest.raises(QaRuntimeError, match="LLM_CALL_FAILED"):
        await Harness().execute(question(), agent)


# --- E-02: create_sqlite() full assembly + idempotency + failure ---

import shutil
import tempfile
from pathlib import Path

from presale.adapters.openai_generator import OpenAICompatibleGenerator
from presale.runtime import PresaleRuntimeFactory


class CallCountingTransport:
    """Transport that counts calls and returns configurable responses."""

    def __init__(self, responses=None, *, fail_on_call=False):
        self._responses = responses or [
            {"choices": [{"message": {"content": "SQLite LLM answer."}}]}
        ]
        self._fail_on_call = fail_on_call
        self.calls = 0

    def __call__(self, *, api_key, base_url, model, messages, timeout_s):
        self.calls += 1
        if self._fail_on_call:
            raise ConnectionError("LLM unreachable")
        idx = min(self.calls - 1, len(self._responses) - 1)
        return self._responses[idx]


def _sqlite_assembly(transport):
    """Create a SQLite-backed factory with injected generator transport."""
    tmp = Path(tempfile.mkdtemp(prefix="e02_sqlite_"))
    db = tmp / "presale.sqlite3"
    registry = Registry(
        [
            definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
            definition(
                "PromptPackage", "prm_01111111-1111-7111-8111-111111111111", "presale-prompt"
            ),
            definition(
                "ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111", "presale-context"
            ),
        ]
    )
    generator = OpenAICompatibleGenerator(
        model="gpt-test",
        base_url="https://example.test/v1",
        api_key="test-key",
        transport=transport,
    )
    factory, store = PresaleRuntimeFactory.create_sqlite(
        database=str(db),
        definition_repository=registry,
        definition_selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"},
            "prompt_package": {
                "kind": "PromptPackage",
                "namespace": "presale",
                "key": "presale-prompt",
            },
            "context_policy": {
                "kind": "ContextPolicy",
                "namespace": "presale",
                "key": "presale-context",
            },
        },
        sources=[source()],
        generator=generator,
    )
    return factory, store, tmp


@pytest.mark.asyncio
async def test_sqlite_assembly_with_real_generator():
    """E-02: create_sqlite + injected generator → FINALIZE + answer_draft."""
    transport = CallCountingTransport()
    factory, store, tmp = _sqlite_assembly(transport)
    try:
        agent = factory.create_agent()

        outcome = await Harness().execute(question(), agent)

        assert outcome.terminal is TerminalDecision.FINALIZE
        assert outcome.answer_draft is not None
        assert outcome.answer_draft.answer_text == "SQLite LLM answer."
        assert transport.calls == 1
    finally:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_sqlite_idempotent_replay_skips_generator():
    """E-02: Same key replay → same answer_draft, generator NOT called again."""
    transport = CallCountingTransport()
    factory, store, tmp = _sqlite_assembly(transport)
    try:
        agent = factory.create_agent()

        first = await Harness().execute(question(key="e02-idem-0001"), agent)
        assert transport.calls == 1

        # Second call with same key should replay, not re-generate
        second = await Harness().execute(question(key="e02-idem-0001"), agent)
        assert transport.calls == 1  # still 1, not 2
        assert second.answer_draft.answer_id == first.answer_draft.answer_id
        assert second.answer_draft.answer_text == first.answer_draft.answer_text
    finally:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.asyncio
async def test_sqlite_generator_failure_marks_claim():
    """E-02: Generator exception → QaRuntimeError, claim not dangling."""
    transport = CallCountingTransport(fail_on_call=True)
    factory, store, tmp = _sqlite_assembly(transport)
    try:
        agent = factory.create_agent()

        with pytest.raises(QaRuntimeError, match="LLM_CALL_FAILED"):
            await Harness().execute(question(key="e02-fail-0001"), agent)

        # Verify claim is in failed state (not dangling)
        from presale.adapters.sqlite import SQLiteIdempotencyRepository

        repo = SQLiteIdempotencyRepository(store)
        record = await repo.get("tenant-demo", "e02-fail-0001")
        assert record is not None
        assert record.status == "failed"
    finally:
        store.close()
        shutil.rmtree(tmp, ignore_errors=True)
