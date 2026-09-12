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
TENANT = "tenant-demo"
ACTOR = "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"


def source(*, source_id="catalog-001", season="适合夏季使用", tenant_id="tenant-demo", product_id="product-001", status="published"):
    return KnowledgeSource(
        source_id=source_id,
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id=product_id,
        status=status,
        fields={"spec": {"season": season, "material": "轻量透气面料"}},
    )


@pytest.mark.asyncio
async def test_no_evidence_results_in_human_review_not_fake_success():
    runner = PresaleQaRunner(sources=[source(season="仅适合室内收纳", product_id="product-other")])

    result = await runner.ask(QUESTION)

    assert result.answer_draft.need_human is True
    assert result.answer_draft.evidence_refs == []
    assert result.answer_draft.reason_codes
    assert result.trace.answer_draft_id == result.answer_draft.answer_id


@pytest.mark.asyncio
async def test_conflicting_evidence_results_in_human_review():
    runner = PresaleQaRunner(
        sources=[
            source(source_id="catalog-a", season="适合夏季使用"),
            source(source_id="catalog-b", season="不适合夏季使用"),
        ]
    )

    result = await runner.ask(QUESTION)

    assert result.answer_draft.need_human is True
    assert result.answer_draft.confidence_signal == "conflicting"
    assert "CONFLICTING_EVIDENCE" in result.answer_draft.reason_codes


@pytest.mark.asyncio
async def test_cross_tenant_and_cross_product_sources_are_out_of_scope():
    cross_tenant = source(tenant_id="tenant-other")
    cross_product = source(product_id="product-other")

    for out_of_scope_source in (cross_tenant, cross_product):
        result = await PresaleQaRunner(sources=[out_of_scope_source]).ask(QUESTION)
        assert result.answer_draft.need_human is True
        assert "OUT_OF_SCOPE" in result.answer_draft.reason_codes


@pytest.mark.asyncio
async def test_context_budget_overflow_is_explicit_failure_with_budget_reason():
    runner = PresaleQaRunner(sources=[source()], context_budget_tokens=1)

    with pytest.raises(QaRuntimeError, match="TOKEN_BUDGET_EXCEEDED"):
        await runner.ask(QUESTION)


@pytest.mark.asyncio
async def test_generation_failure_is_explicit():
    class ExplodingGenerator:
        def generate(self, *args, **kwargs):
            raise RuntimeError("boom")

    runner = PresaleQaRunner(sources=[source()], generator=ExplodingGenerator())

    with pytest.raises(QaRuntimeError, match="ANSWER_GENERATION_FAILED"):
        await runner.ask(QUESTION)


@pytest.mark.asyncio
async def test_pipeline_never_invokes_write_side_effects():
    calls = []

    class ReadOnlyGenerator:
        def generate(self, *args, **kwargs):
            calls.append("generate")
            from presale.answer import PresaleAnswerGenerator

            return PresaleAnswerGenerator().generate(*args, **kwargs)

        def change_price(self, *a, **k):
            calls.append("change_price")

        def create_order(self, *a, **k):
            calls.append("create_order")

        def write_inventory(self, *a, **k):
            calls.append("write_inventory")

        def make_payment(self, *a, **k):
            calls.append("make_payment")

        def send_message(self, *a, **k):
            calls.append("send_message")

    generator = ReadOnlyGenerator()
    runner = PresaleQaRunner(sources=[source()], generator=generator)

    result = await runner.ask(QUESTION)
    await runner.accept(
        result.answer_draft.answer_id,
        actor_id=ACTOR,
        reason="确认",
        tenant_id=TENANT,
    )

    assert calls == ["generate"], f"write side effects invoked: {calls}"
