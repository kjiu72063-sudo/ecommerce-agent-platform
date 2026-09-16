"""OpenAI-compatible LLM GeneratorPort adapter for the presale slice.

Calls an OpenAI-compatible ``/chat/completions`` endpoint synchronously and maps
the response to a tenant-scoped ``AnswerDraft``. The HTTP transport and prompt
builder are injectable so the adapter is fully testable offline and external
calls only happen when explicitly wired at assembly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from ..answer import AnswerGenerationError, GeneratorPort
from ..contracts import AnswerDraft, EvidenceRef, ProductQuestion
from ..knowledge import RetrievalResult, RetrievalStatus

Transport = Callable[..., dict[str, Any]]
PromptBuilder = Callable[..., str]


def default_transport(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    timeout_s: float,
) -> dict[str, Any]:
    """POST ``/chat/completions`` and return the parsed completion JSON."""
    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": messages}
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def default_prompt_builder(
    question: ProductQuestion, retrieval: RetrievalResult, configuration_refs: dict[str, str]
) -> str:
    evidence = "\n".join(
        f"- [{item.source_id}@{item.source_version}#{item.locator}] {item.content}"
        for item in retrieval.evidence_items
    )
    return (
        "你是电商售前客服助手，请仅依据给定证据回答用户对商品的提问。\n"
        f"租户: {question.tenant_id}  商品: {question.product_id}\n"
        f"用户问题: {question.question_text}\n"
        f"证据:\n{evidence or '(无证据——请说明无法确定，需要转人工复核)'}\n"
        "请给出简洁、准确、仅基于证据的中文回答。"
    )


class OpenAICompatibleGenerator(GeneratorPort):
    """Call an OpenAI-compatible chat completion to produce an AnswerDraft."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        timeout_s: float = 30.0,
        transport: Transport | None = None,
        prompt_builder: PromptBuilder | None = None,
    ):
        self._model = model
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport or default_transport
        self._prompt_builder = prompt_builder or default_prompt_builder

    def generate(
        self,
        question: ProductQuestion,
        retrieval: RetrievalResult,
        *,
        run_ref: dict[str, str],
        configuration_refs: dict[str, str],
    ) -> AnswerDraft:
        prompt = self._prompt_builder(question, retrieval, configuration_refs)
        try:
            completion = self._transport(
                api_key=self._api_key,
                base_url=self._base_url,
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                timeout_s=self._timeout_s,
            )
        except AnswerGenerationError:
            raise
        except Exception as exc:
            raise AnswerGenerationError("LLM_CALL_FAILED") from exc

        try:
            text = completion["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AnswerGenerationError("LLM_MALFORMED_RESPONSE") from exc

        if not text or not text.strip():
            raise AnswerGenerationError("LLM_EMPTY_RESPONSE")

        return self._build_draft(question, retrieval, run_ref, configuration_refs, text.strip())

    def _build_draft(
        self,
        question: ProductQuestion,
        retrieval: RetrievalResult,
        run_ref: dict[str, str],
        configuration_refs: dict[str, str],
        llm_text: str,
    ) -> AnswerDraft:
        evidence_refs = [
            EvidenceRef(
                source_id=item.source_id,
                source_version=item.source_version,
                locator=item.locator,
                content_digest=item.content_digest,
            )
            for item in retrieval.evidence_items
        ]
        if retrieval.status is RetrievalStatus.NO_EVIDENCE:
            need_human, confidence, reason = True, "unavailable", ["NO_EVIDENCE"]
        elif retrieval.status is RetrievalStatus.CONFLICT:
            need_human, confidence, reason = True, "conflicting", ["CONFLICTING_EVIDENCE"]
        else:
            need_human, confidence, reason = False, "supported", []
        return AnswerDraft(
            answer_id=f"answer-{run_ref['id']}",
            question_id=question.question_id,
            run_ref=run_ref,
            answer_text=llm_text,
            evidence_refs=evidence_refs,
            confidence_signal=confidence,
            need_human=need_human,
            reason_codes=reason,
            configuration_refs=dict(configuration_refs),
            generated_at=datetime.now(timezone.utc),
        )


__all__ = ["OpenAICompatibleGenerator", "default_prompt_builder", "default_transport"]
