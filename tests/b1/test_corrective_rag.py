"""Corrective-RAG: low-confidence retrieval auto-escalates to human review."""

from datetime import datetime, timezone

import pytest

from agent_platform_contracts.models import ObjectRef, ResourceKind
from agent_platform_contracts.policies import canonical_sha256
from presale.contracts import AnswerDraft, EvidenceRef, ProductQuestion
from presale.knowledge import EvidenceItem, RetrievalResult, RetrievalStatus
from presale.runner import PresaleQaRunner


def question(*, key="corrective-key-001", text="这款商品退货运费谁出？"):
    return ProductQuestion(
        question_id="question-c1",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_corrective"},
        product_id="product-001",
        question_text=text,
        requested_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        idempotency_key=key,
    )


def evidence(content="七天无理由退货"):
    return EvidenceItem(
        source_id="catalog-001",
        source_version="2026.09.01",
        locator="returns",
        content_digest=canonical_sha256({"content": content}),
        tenant_id="tenant-demo",
        product_id="product-001",
        content=content,
    )


class _FixedRetriever:
    def __init__(self, result):
        self._result = result

    def retrieve(self, question):
        return self._result


class _SupportedGenerator:
    """Mimics an LLM that always returns a confident supported draft (need_human=False)."""

    def generate(self, question, retrieval, *, run_ref, configuration_refs):
        refs = [
            EvidenceRef(
                source_id=item.source_id,
                source_version=item.source_version,
                locator=item.locator,
                content_digest=item.content_digest,
            )
            for item in retrieval.evidence_items
        ]
        return AnswerDraft(
            answer_id=f"answer-{run_ref['id']}",
            question_id=question.question_id,
            run_ref=ObjectRef(kind=ResourceKind.AGENT_RUN, id=run_ref["id"]),
            answer_text="可以，退货运费由买家承担。",
            evidence_refs=refs,
            confidence_signal="supported",
            need_human=False,
            reason_codes=[],
            configuration_refs=dict(configuration_refs),
            generated_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_matched_but_below_min_evidence_escalates_to_human():
    retriever = _FixedRetriever(
        RetrievalResult(
            status=RetrievalStatus.MATCHED,
            evidence_items=[evidence()],  # 1 item, below min_evidence=2
        )
    )
    runner = PresaleQaRunner(
        sources=[],
        retriever=retriever,
        generator=_SupportedGenerator(),
        min_evidence_for_answer=2,
    )

    result = await runner.ask(question())

    assert result.answer_draft.need_human is True
    assert "LOW_CONFIDENCE" in result.answer_draft.reason_codes


@pytest.mark.asyncio
async def test_matched_with_enough_evidence_does_not_escalate():
    retriever = _FixedRetriever(
        RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=[evidence(), evidence()])
    )
    runner = PresaleQaRunner(
        sources=[], retriever=retriever, generator=_SupportedGenerator(), min_evidence_for_answer=2
    )

    result = await runner.ask(question())

    assert result.answer_draft.need_human is False
    assert "LOW_CONFIDENCE" not in result.answer_draft.reason_codes


@pytest.mark.asyncio
async def test_no_evidence_structurally_requires_human_review():
    retriever = _FixedRetriever(
        RetrievalResult(status=RetrievalStatus.NO_EVIDENCE, reason_codes=["NO_EVIDENCE"])
    )
    runner = PresaleQaRunner(sources=[], retriever=retriever, min_evidence_for_answer=1)

    result = await runner.ask(question())

    assert result.answer_draft.need_human is True
    assert "NO_EVIDENCE" in result.answer_draft.reason_codes


@pytest.mark.asyncio
async def test_replay_returns_persisted_draft_unchanged():
    # First ask persists a draft; replay must return it as-is (gate only in fresh path).
    retriever = _FixedRetriever(
        RetrievalResult(
            status=RetrievalStatus.MATCHED,
            evidence_items=[evidence(), evidence()],
        )
    )
    runner = PresaleQaRunner(
        sources=[],
        retriever=retriever,
        generator=_SupportedGenerator(),
        min_evidence_for_answer=1,  # 2 evidence >= 1, so fresh path does not escalate
    )

    first = await runner.ask(question())
    replay = await runner.ask(question())

    assert first.answer_draft.need_human is False  # enough evidence in fresh path
    assert replay.answer_draft.answer_id == first.answer_draft.answer_id
    assert replay.answer_draft.answer_text == first.answer_draft.answer_text
