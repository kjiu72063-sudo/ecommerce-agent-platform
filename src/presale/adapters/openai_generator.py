"""OpenAI-compatible LLM GeneratorPort adapter for the presale slice.

Calls an OpenAI-compatible ``/chat/completions`` endpoint synchronously and maps
the response to a tenant-scoped ``AnswerDraft``. The HTTP transport and prompt
builder are injectable so the adapter is fully testable offline and external
calls only happen when explicitly wired at assembly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from agent_platform_contracts.models import ObjectRef, ResourceKind

from ..answer import AnswerGenerationError, GeneratorPort
from ..contracts import AnswerDraft, EvidenceRef, ProductQuestion
from ..knowledge import RetrievalResult, RetrievalStatus

Transport = Callable[..., dict[str, Any]]
PromptBuilder = Callable[..., str]


def retry_after_seconds(exc: BaseException) -> float | None:
    """Extract Retry-After seconds from an httpx 429/503 response, if present.

    Accepts both delta-seconds (``"45"``) and HTTP-date forms. Returns None for
    non-rate-limit errors or an unusable header so callers fall back to
    fixed backoff.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    status = getattr(response, "status_code", None)
    if status not in (429, 503):
        return None
    raw = (getattr(response, "headers", None) or {}).get("Retry-After")
    if not raw:
        return None
    text = str(raw).strip()
    if text.isdigit():
        return float(text)
    try:
        from email.utils import parsedate_to_datetime

        when = parsedate_to_datetime(text)
        delta = (when - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return None


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


def build_stream_prompt(
    question: ProductQuestion,
    retrieval: RetrievalResult,
    configuration_refs: dict[str, str],
    history: list[dict[str, str]] | None = None,
) -> str:
    """Prompt for the streaming endpoint: optional multi-turn context prefix.

    ``history`` entries are ``{"question": ..., "answer": ...}`` from earlier
    turns of the same session; they only help resolve follow-up references
    (\"那防水呢\") and never replace the evidence block.
    """
    base = default_prompt_builder(question, retrieval, configuration_refs)
    if not history:
        return base
    lines = []
    for turn in history[-3:]:
        lines.append(f"Q: {turn.get('question', '')}")
        lines.append(f"A: {turn.get('answer', '')}")
    prefix = (
        "对话历史（仅供理解追问中的指代，回答仍须只依据下方证据）：\n" + "\n".join(lines) + "\n\n"
    )
    return prefix + base


def stream_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    timeout_s: float = 60.0,
):
    """Yield text deltas from an OpenAI-compatible streaming chat completion."""
    import json as _json

    import httpx

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {"model": model, "messages": messages, "stream": True}
    with httpx.Client(timeout=timeout_s) as client:
        with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = _json.loads(data)
                    delta = chunk["choices"][0].get("delta", {}).get("content")
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
                if delta:
                    yield delta


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
            wait = retry_after_seconds(exc)
            if wait is not None:
                # Keep the seconds in the message so QaRuntimeError(str) —
                # which drops attributes — still carries them to the replay
                # backoff. Attribute is set for callers that hold the error.
                raise AnswerGenerationError(
                    f"LLM_RATE_LIMITED retry_after={int(wait)}", retry_after=wait
                ) from exc
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
            run_ref=ObjectRef(kind=ResourceKind(run_ref["kind"]), id=run_ref["id"]),
            answer_text=llm_text,
            evidence_refs=evidence_refs,
            confidence_signal=confidence,
            need_human=need_human,
            reason_codes=reason,
            configuration_refs=dict(configuration_refs),
            generated_at=datetime.now(timezone.utc),
        )


__all__ = [
    "OpenAICompatibleGenerator",
    "build_stream_prompt",
    "default_prompt_builder",
    "default_transport",
    "retry_after_seconds",
    "stream_completion",
]
