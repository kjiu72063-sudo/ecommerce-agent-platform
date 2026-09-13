from datetime import datetime, timedelta, timezone

import pytest

from presale.adapters.in_memory import InMemoryRunTraceRepository
from presale.adapters.sqlite import SQLitePresaleStore, SQLiteRunTraceRepository
from presale.contracts import ProductQuestion
from presale.retention import RetentionService
from presale.trace import PresaleRunTracer, TraceError


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


def make_repo(backend, tmp_path):
    if backend == "sqlite":
        return SQLiteRunTraceRepository(SQLitePresaleStore(tmp_path / "retention.sqlite3"))
    return InMemoryRunTraceRepository()


async def start_trace(tracer, run_ref, *, age_days=0):
    await tracer.start(
        question=question(age_days=age_days),
        task_id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
        agent_run_id=run_ref,
        configuration_refs={},
    )


@pytest.mark.asyncio
async def test_default_retention_is_30_days():
    repo = InMemoryRunTraceRepository()
    service = RetentionService(repo)
    assert service.retention_policy().retain_days == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_expired_completed_record_is_archived_not_deleted(backend, tmp_path):
    repo = make_repo(backend, tmp_path)
    tracer = PresaleRunTracer(trace_repo=repo)
    run_ref = "run_01111111-1111-7111-8111-111111111111"
    await start_trace(tracer, run_ref, age_days=40)
    await tracer.mark_disposition_complete(run_ref, tenant_id="tenant-demo")

    service = RetentionService(repo)
    now = datetime.now(timezone.utc)
    archived = await service.archive_expired(tenant_id="tenant-demo", now=now)

    assert archived == [run_ref]
    trace = await tracer.get(run_ref, tenant_id="tenant-demo")
    assert trace.archived is True
    assert trace.stages  # 历史 stages/Event 留痕保留
    assert trace.question_id == "question-retention"


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_archive_is_idempotent(backend, tmp_path):
    repo = make_repo(backend, tmp_path)
    tracer = PresaleRunTracer(trace_repo=repo)
    run_ref = "run_01111111-1111-7111-8111-111111111111"
    await start_trace(tracer, run_ref, age_days=40)
    await tracer.mark_disposition_complete(run_ref, tenant_id="tenant-demo")

    service = RetentionService(repo)
    now = datetime.now(timezone.utc)
    first = await service.archive_expired(tenant_id="tenant-demo", now=now)
    second = await service.archive_expired(tenant_id="tenant-demo", now=now)

    assert first == [run_ref]
    assert second == []


@pytest.mark.asyncio
async def test_non_expired_completed_record_is_kept():
    repo = InMemoryRunTraceRepository()
    tracer = PresaleRunTracer(trace_repo=repo)
    run_ref = "run_01111111-1111-7111-8111-111111111111"
    await start_trace(tracer, run_ref, age_days=5)
    await tracer.mark_disposition_complete(run_ref, tenant_id="tenant-demo")

    service = RetentionService(repo)
    now = datetime.now(timezone.utc)
    archived = await service.archive_expired(tenant_id="tenant-demo", now=now)

    assert archived == []
    assert (await tracer.get(run_ref, tenant_id="tenant-demo")).archived is False


@pytest.mark.asyncio
async def test_expired_unfinished_or_escalated_record_is_kept():
    unfinished = "run_01111111-1111-7111-8111-111111111111"
    escalated = "run_02222222-2222-7222-8222-222222222222"
    repo = InMemoryRunTraceRepository()
    tracer = PresaleRunTracer(trace_repo=repo)
    await start_trace(tracer, unfinished, age_days=40)
    await start_trace(tracer, escalated, age_days=40)
    await tracer.mark_disposition_escalated(escalated, tenant_id="tenant-demo")

    service = RetentionService(repo)
    now = datetime.now(timezone.utc)
    archived = await service.archive_expired(tenant_id="tenant-demo", now=now)

    assert archived == []
    assert (await tracer.get(unfinished, tenant_id="tenant-demo")).archived is False
    assert (await tracer.get(escalated, tenant_id="tenant-demo")).archived is False


@pytest.mark.asyncio
async def test_archive_requires_tenant_scope():
    repo = InMemoryRunTraceRepository()
    service = RetentionService(repo)
    with pytest.raises(TraceError, match="TENANT_ID_REQUIRED"):
        await service.archive_expired(tenant_id="", now=datetime.now(timezone.utc))


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_archive_expired_is_isolated_per_tenant(backend, tmp_path):
    repo = make_repo(backend, tmp_path)
    tracer = PresaleRunTracer(trace_repo=repo)
    run_a = "run_01111111-1111-7111-8111-111111111111"
    run_b = "run_02222222-2222-7222-8222-222222222222"

    async def start_tenant(run_ref, tenant_id):
        await tracer.start(
            question=ProductQuestion(
                question_id=f"q-{tenant_id}",
                tenant_id=tenant_id,
                submitted_by={"actor_type": "user", "actor_id": "usr_seed"},
                product_id="product-001",
                question_text="这款商品适合夏季使用吗？",
                requested_at=datetime.now(timezone.utc) - timedelta(days=40),
                idempotency_key=f"{tenant_id}-key",
            ),
            task_id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
            agent_run_id=run_ref,
            configuration_refs={},
        )
        await tracer.mark_disposition_complete(run_ref, tenant_id=tenant_id)

    await start_tenant(run_a, "tenant-a")
    await start_tenant(run_b, "tenant-b")

    service = RetentionService(repo)
    now = datetime.now(timezone.utc)
    archived_a = await service.archive_expired(tenant_id="tenant-a", now=now)

    assert archived_a == [run_a]
    assert (await tracer.get(run_a, tenant_id="tenant-a")).archived is True
    # tenant-b's trace must be untouched by tenant-a's archive run.
    assert (await tracer.get(run_b, tenant_id="tenant-b")).archived is False
