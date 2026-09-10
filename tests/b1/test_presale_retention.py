from datetime import datetime, timedelta, timezone

import pytest

from presale.contracts import ProductQuestion
from presale.trace import TraceError, PresaleRunTracer, DispositionState


def question(*, age_days=0):
    return ProductQuestion(
        question_id="question-retention",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        idempotency_key="retention-key-001",
    )


def start_trace(tracer, run_ref, *, age_days=0):
    tracer.start(
        question=question(age_days=age_days),
        task_id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
        agent_run_id=run_ref,
        configuration_refs={},
    )


def test_default_retention_is_30_days():
    tracer = PresaleRunTracer()
    start_trace(tracer, "run_01111111-1111-7111-8111-111111111111")
    now = datetime.now(timezone.utc)

    policy = tracer.retention_policy()
    assert policy.retain_days == 30


def test_expired_completed_record_is_archived_noth_deleted():
    tracer = PresaleRunTracer()
    run_ref = "run_01111111-1111-7111-8111-111111111111"
    start_trace(tracer, run_ref, age_days=40)
    tracer.mark_disposition_complete(run_ref)

    now = datetime.now(timezone.utc)
    archived = tracer.archive_expired(tenant_id="tenant-demo", now=now)

    assert archived == [run_ref]
    trace = tracer.get(run_ref, tenant_id="tenant-demo")
    assert trace.archived is True
    assert trace.stages  # 历史 stages/Event 留痕保留
    assert trace.question_id == "question-retention"


def test_archive_is_idempotent():
    tracer = PresaleRunTracer()
    run_ref = "run_01111111-1111-7111-8111-111111111111"
    start_trace(tracer, run_ref, age_days=40)
    tracer.mark_disposition_complete(run_ref)

    now = datetime.now(timezone.utc)
    first = tracer.archive_expired(tenant_id="tenant-demo", now=now)
    second = tracer.archive_expired(tenant_id="tenant-demo", now=now)

    assert first == [run_ref]
    assert second == []


def test_non_expired_completed_record_is_kept():
    tracer = PresaleRunTracer()
    run_ref = "run_01111111-1111-7111-8111-111111111111"
    start_trace(tracer, run_ref, age_days=5)
    tracer.mark_disposition_complete(run_ref)

    now = datetime.now(timezone.utc)
    archived = tracer.archive_expired(tenant_id="tenant-demo", now=now)

    assert archived == []
    assert tracer.get(run_ref, tenant_id="tenant-demo").archived is False


def test_expired_unfinished_or_escalated_record_is_kept():
    unfinished = "run_01111111-1111-7111-8111-111111111111"
    escalated = "run_02222222-2222-7222-8222-222222222222"
    tracer = PresaleRunTracer()
    start_trace(tracer, unfinished, age_days=40)
    start_trace(tracer, escalated, age_days=40)
    tracer.mark_disposition_escalated(escalated)

    now = datetime.now(timezone.utc)
    archived = tracer.archive_expired(tenant_id="tenant-demo", now=now)

    assert archived == []
    assert tracer.get(unfinished, tenant_id="tenant-demo").archived is False
    assert tracer.get(escalated, tenant_id="tenant-demo").archived is False


def test_archive_requires_tenant_scope():
    tracer = PresaleRunTracer()
    start_trace(tracer, "run_01111111-1111-7111-8111-111111111111")

    with pytest.raises(TraceError, match="TENANT_ID_REQUIRED"):
        tracer.archive_expired(tenant_id="", now=datetime.now(timezone.utc))