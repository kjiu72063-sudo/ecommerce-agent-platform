from datetime import datetime, timezone

import pytest

from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runner import PresaleQaRunner, QaRuntimeError

QUESTION = ProductQuestion(
    question_id="question-001",
    tenant_id="tenant-demo",
    submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    product_id="product-001",
    question_text="这款商品适合夏季使用吗？",
    requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    idempotency_key="question-001-key",
)
ACTOR = "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"


def published_source(*, season="适合夏季使用", product_id="product-001", status="published"):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id=product_id,
        status=status,
        fields={"spec": {"season": season, "material": "轻量透气面料"}},
    )


@pytest.mark.asyncio
async def test_end_to_end_matched_path_is_reproducible_and_traceable():
    runner = PresaleQaRunner(sources=[published_source()])

    first = await runner.ask(QUESTION)
    second = await runner.ask(QUESTION)

    assert first.answer_draft.evidence_refs, "expected evidence"
    assert first.answer_draft.need_human is False
    assert first.answer_draft.run_ref.id == first.run_ref
    assert first.answer_draft.answer_text == second.answer_draft.answer_text
    assert first.answer_draft.evidence_refs == second.answer_draft.evidence_refs
    assert first.trace.question_id == "question-001"
    assert "answer_generated" in [stage.stage for stage in first.trace.stages]


@pytest.mark.asyncio
async def test_end_to_end_accept_disposition_is_available_and_no_send():
    runner = PresaleQaRunner(sources=[published_source()])
    result = await runner.ask(QUESTION)

    disposition = await runner.accept(
        result.answer_draft.answer_id, actor_id=ACTOR, reason="确认", tenant_id="tenant-demo"
    )

    assert disposition.disposition == "accepted"
    assert disposition.sent_to_consumer is False
    assert disposition.original_answer.answer_id == result.answer_draft.answer_id


@pytest.mark.asyncio
async def test_end_to_end_no_evidence_requires_human_and_trace_marks_answer():
    runner = PresaleQaRunner(
        sources=[published_source(season="仅适合室内收纳", product_id="product-other")]
    )

    result = await runner.ask(QUESTION)

    assert result.answer_draft.need_human is True
    assert result.answer_draft.reason_codes
    assert result.trace.answer_draft_id == result.answer_draft.answer_id


@pytest.mark.asyncio
async def test_end_to_end_failure_path_is_explicit():
    class ExplodingGenerator:
        def generate(self, *args, **kwargs):
            raise RuntimeError("simulated failure")

    runner = PresaleQaRunner(sources=[published_source()], generator=ExplodingGenerator())

    with pytest.raises(QaRuntimeError, match="ANSWER_GENERATION_FAILED"):
        await runner.ask(QUESTION)


@pytest.mark.asyncio
async def test_end_to_end_run_ref_is_traceable():
    runner = PresaleQaRunner(sources=[published_source()])
    result = await runner.ask(QUESTION)

    trace = await runner.get_trace(result.run_ref, tenant_id="tenant-demo")

    assert trace.run_ref == result.run_ref
    assert trace.tenant_id == "tenant-demo"
