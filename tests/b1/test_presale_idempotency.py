from datetime import datetime, timezone

import pytest

from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runner import IdempotencyConflictError, PresaleQaRunner


def question(*, question_id="question-001", tenant_id="tenant-demo", text="这款商品适合夏季使用吗？"):
    return ProductQuestion(
        question_id=question_id,
        tenant_id=tenant_id,
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text=text,
        requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        idempotency_key="question-001-key",
    )


def source(tenant_id="tenant-demo"):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id="product-001",
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def test_same_tenant_and_key_returns_existing_result():
    runner = PresaleQaRunner(sources=[source()])
    first = runner.ask(question())
    second = runner.ask(question(question_id="question-002"))

    assert second is first
    assert second.run_ref == first.run_ref
    assert second.answer_draft.answer_id == first.answer_draft.answer_id


def test_same_key_with_different_business_content_is_conflict():
    runner = PresaleQaRunner(sources=[source()])
    runner.ask(question())

    with pytest.raises(IdempotencyConflictError, match="IDEMPOTENCY_CONFLICT"):
        runner.ask(question(text="这款商品是什么材质？"))


def test_same_key_different_tenants_do_not_collide():
    runner = PresaleQaRunner(sources=[source(), source(tenant_id="tenant-other")])
    first = runner.ask(question())
    other = runner.ask(question(question_id="question-other", tenant_id="tenant-other"))

    assert other is not first
    assert other.run_ref != first.run_ref


def test_missing_or_invalid_idempotency_key_is_rejected_by_contract():
    invalid = {**question().model_dump(mode="json"), "idempotency_key": "short"}

    with pytest.raises(ValueError):
        ProductQuestion.model_validate(invalid)
