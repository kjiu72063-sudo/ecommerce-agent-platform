from datetime import datetime, timezone

import pytest

from agent_platform_contracts.policies import canonical_sha256
from presale.answer import PresaleAnswerGenerator
from presale.contracts import ProductQuestion
from presale.disposition import AnswerDispositionService, DispositionError, DispositionType
from presale.knowledge import EvidenceItem, RetrievalResult, RetrievalStatus

QUESTION = ProductQuestion(
    question_id="question-001",
    tenant_id="tenant-demo",
    submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    product_id="product-001",
    question_text="这款商品适合夏季使用吗？",
    requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    idempotency_key="question-001-key",
)
RUN_REF = {"kind": "AgentRun", "id": "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"}
TENANT = "tenant-demo"
ACTOR = "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"


def draft():
    evidence = EvidenceItem(
        source_id="catalog-001",
        source_version="2026.09.01",
        locator="spec.season",
        content_digest=canonical_sha256({"content": "适合夏季使用"}),
        tenant_id="tenant-demo",
        product_id="product-001",
        content="适合夏季使用",
    )
    return PresaleAnswerGenerator().generate(
        QUESTION,
        RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=[evidence]),
        run_ref=RUN_REF,
        configuration_refs={"agent_spec": "1.0.0"},
    )


@pytest.mark.asyncio
async def test_accept_records_internal_adoption_without_send_side_effect():
    service = AnswerDispositionService()
    original = draft()
    service.register(original)

    result = await service.accept(
        original.answer_id, actor_id=ACTOR, reason="客服确认可用", tenant_id=TENANT
    )

    assert result.disposition is DispositionType.ACCEPTED
    assert result.original_answer == original
    assert result.edited_answer is None
    assert result.sent_to_consumer is False
    assert result.actor_id.endswith("f411")


@pytest.mark.asyncio
async def test_edit_preserves_original_and_records_new_version():
    service = AnswerDispositionService()
    original = draft()
    service.register(original)

    result = await service.edit(
        original.answer_id,
        edited_text="根据商品资料，适合夏季使用。",
        actor_id=ACTOR,
        reason="补充客服语气",
        tenant_id=TENANT,
    )

    assert result.disposition is DispositionType.EDITED
    assert result.original_answer == original
    assert result.edited_answer is not None
    assert result.edited_answer.answer_text == "根据商品资料，适合夏季使用。"
    assert result.edited_answer.answer_id != original.answer_id
    assert result.reason == "补充客服语气"
    assert result.sent_to_consumer is False
    assert service.get_original(original.answer_id) == original


@pytest.mark.asyncio
async def test_escalate_records_reason_without_changing_technical_status():
    service = AnswerDispositionService()
    original = draft()
    service.register(original, technical_status="succeeded")

    result = await service.escalate(
        original.answer_id, actor_id=ACTOR, reason="需要人工确认商品政策", tenant_id=TENANT
    )

    assert result.disposition is DispositionType.ESCALATED
    assert result.reason == "需要人工确认商品政策"
    assert result.technical_status == "succeeded"
    assert result.sent_to_consumer is False


@pytest.mark.asyncio
async def test_discard_records_non_adoption():
    service = AnswerDispositionService()
    original = draft()
    service.register(original)

    result = await service.discard(
        original.answer_id, actor_id=ACTOR, reason="内容不适用", tenant_id=TENANT
    )

    assert result.disposition is DispositionType.DISCARDED
    assert result.reason == "内容不适用"
    assert result.original_answer == original
    assert result.sent_to_consumer is False


@pytest.mark.asyncio
async def test_edit_rejects_blank_text_and_already_disposed_draft():
    service = AnswerDispositionService()
    original = draft()
    service.register(original)

    with pytest.raises(DispositionError, match="EMPTY_EDIT"):
        await service.edit(
            original.answer_id,
            edited_text="   ",
            actor_id=ACTOR,
            reason="无效编辑",
            tenant_id=TENANT,
        )

    await service.accept(original.answer_id, actor_id=ACTOR, reason="确认", tenant_id=TENANT)
    with pytest.raises(DispositionError, match="ALREADY_DISPOSED"):
        await service.discard(
            original.answer_id, actor_id=ACTOR, reason="重复操作", tenant_id=TENANT
        )


@pytest.mark.asyncio
async def test_missing_draft_fails_explicitly():
    with pytest.raises(DispositionError, match="DRAFT_NOT_FOUND"):
        await AnswerDispositionService().accept(
            "missing-answer", actor_id=ACTOR, reason="不存在", tenant_id=TENANT
        )
