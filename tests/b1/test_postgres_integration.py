"""B-01/B-02/B-03: PostgreSQL adapter integration tests.

Requires a running PostgreSQL instance. When PRESALE_PG_DSN is not set,
all tests are skipped (same pattern as Milvus integration tests).
"""

import os
import uuid

import pytest

from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource

PG_DSN = os.environ.get("PRESALE_PG_DSN")
pytestmark = pytest.mark.skipif(
    not PG_DSN, reason="set PRESALE_PG_DSN to run PostgreSQL integration tests"
)

from datetime import datetime, timezone

from agent_runtime.harness import Harness, TerminalDecision
from presale.ports import NotFoundError
from presale.runtime import PresaleRuntimeFactory


def _uuid7_str() -> str:
    """Generate a UUIDv7-compatible string for tests (with run_ prefix)."""
    import uuid as _uuid
    value = _uuid.uuid4().int
    value = (value & ~(0xF << 76)) | (0x7 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)
    return f"run_{_uuid.UUID(int=value)}"


def _question(*, key="pg-test-key-0001"):
    uid = uuid.uuid4().hex[:8]
    return ProductQuestion(
        question_id=f"question-pg-{uid}",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_pg_001"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        idempotency_key=key,
    )


def _source():
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id="product-001",
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def _definition(kind, object_id, key):
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


class _Registry:
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


# --- B-01: PostgresPresaleStore + schema ---


@pytest.mark.asyncio
async def test_postgres_store_creates_tables():
    """B-01: PostgresPresaleStore connects and creates schema."""
    from presale.adapters.postgres import PostgresPresaleStore

    store = PostgresPresaleStore(dsn=PG_DSN)
    pool = await store._ensure_init()
    # Tables should exist after store creation
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name LIKE 'presale_%'"
        )
        table_names = {r["table_name"] for r in rows}
        expected = {
            "presale_questions",
            "presale_idempotency",
            "presale_evidence",
            "presale_answers",
            "presale_dispositions",
            "presale_traces",
        }
        assert expected.issubset(table_names)
    await store.close()


# --- B-02: PostgreSQL Repository adapters ---


@pytest.mark.asyncio
async def test_postgres_question_repository():
    """B-02: PostgresProductQuestionRepository save/get/find."""
    from presale.adapters.postgres import PostgresPresaleStore, PostgresProductQuestionRepository

    store = PostgresPresaleStore(dsn=PG_DSN)
    repo = PostgresProductQuestionRepository(store)
    q = _question(key=f"pg-repo-q-{uuid.uuid4().hex[:8]}")

    await repo.save(q)
    found = await repo.get(q.question_id, tenant_id="tenant-demo")
    assert found.question_id == q.question_id

    by_key = await repo.find_by_idempotency("tenant-demo", q.idempotency_key)
    assert by_key is not None
    assert by_key.question_id == q.question_id

    # Cross-tenant must fail
    with pytest.raises(NotFoundError):
        await repo.get(q.question_id, tenant_id="other-tenant")

    await store.close()


@pytest.mark.asyncio
async def test_postgres_answer_repository():
    """B-02: PostgresAnswerDraftRepository save/get_by_id/get_by_run."""
    from presale.adapters.postgres import PostgresAnswerDraftRepository, PostgresPresaleStore
    from presale.answer import AnswerDraft

    store = PostgresPresaleStore(dsn=PG_DSN)
    repo = PostgresAnswerDraftRepository(store)
    run_id = _uuid7_str()
    draft = AnswerDraft(
        answer_id="ans-pg-001",
        question_id=f"q-pg-{uuid.uuid4().hex[:8]}",
        run_ref={"kind": "AgentRun", "id": run_id},
        answer_text="PG answer",
        evidence_refs=[],
        confidence_signal="supported",
        need_human=True,
        reason_codes=["NO_EVIDENCE"],
        configuration_refs={},
        generated_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )

    await repo.save(draft, tenant_id="tenant-demo")
    found = await repo.get_by_id("ans-pg-001", tenant_id="tenant-demo")
    assert found.answer_text == "PG answer"

    by_run = await repo.get_by_run(run_id, tenant_id="tenant-demo")
    assert by_run is not None
    assert by_run.answer_id == "ans-pg-001"

    await store.close()


@pytest.mark.asyncio
async def test_postgres_idempotency_repository():
    """B-02: PostgresIdempotencyRepository claim/get/update_status."""
    from presale.adapters.postgres import PostgresIdempotencyRepository, PostgresPresaleStore
    from presale.idempotency import IdempotencyRecord

    store = PostgresPresaleStore(dsn=PG_DSN)
    repo = PostgresIdempotencyRepository(store)
    key = f"pg-idem-{uuid.uuid4().hex[:8]}"
    record = IdempotencyRecord(
        tenant_id="tenant-demo",
        idempotency_key=key,
        business_content_digest="sha256:" + "a" * 64,
        run_ref=_uuid7_str(),
        created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        status="in_progress",
    )

    claimed = await repo.claim(record)
    assert claimed.idempotency_key == key

    # Second claim with same key returns existing
    claimed2 = await repo.claim(record)
    assert claimed2.status == "in_progress"

    # Update status
    updated = await repo.update_status("tenant-demo", key, "succeeded")
    assert updated.status == "succeeded"

    await store.close()


@pytest.mark.asyncio
async def test_postgres_trace_repository():
    """B-02: PostgresRunTraceRepository save/get/list/mark."""
    from presale.adapters.postgres import PostgresPresaleStore, PostgresRunTraceRepository
    from presale.trace import PresaleRunTrace, DispositionState

    store = PostgresPresaleStore(dsn=PG_DSN)
    repo = PostgresRunTraceRepository(store)
    trace = PresaleRunTrace(
        run_ref="run-pg-trace-001",
        tenant_id="tenant-demo",
        question_id="q-pg-trace-001",
        task_id="tsk-pg-001",
        agent_run_id="run-pg-trace-001",
        stages=[],
        configuration_refs={"agent_spec": "sha256:" + "a" * 64, "prompt_package": "sha256:" + "b" * 64},
        disposition_state=DispositionState.PENDING,
        archived=False,
    )

    await repo.save(trace)
    found = await repo.get("run-pg-trace-001", tenant_id="tenant-demo")
    assert found.run_ref == "run-pg-trace-001"

    traces = await repo.list_by_tenant(tenant_id="tenant-demo")
    assert any(t.run_ref == "run-pg-trace-001" for t in traces)

    await repo.mark_disposition("run-pg-trace-001", tenant_id="tenant-demo", state="complete")
    updated = await repo.get("run-pg-trace-001", tenant_id="tenant-demo")
    assert updated.disposition_state == DispositionState.COMPLETE

    await store.close()


# --- B-03: create_postgres() + end-to-end ---


def _factory():
    """Create a PostgreSQL-backed factory with valid UUIDv7 definition IDs."""
    def _id(prefix: str) -> str:
        import uuid as _uuid
        value = _uuid.uuid4().int
        value = (value & ~(0xF << 76)) | (0x7 << 76)
        value = (value & ~(0x3 << 62)) | (0x2 << 62)
        u = _uuid.UUID(int=value)
        return f"{prefix}_{u}"

    registry = _Registry(
        [
            _definition("AgentSpec", _id("agt"), "presale-agent"),
            _definition("PromptPackage", _id("prm"), "presale-prompt"),
            _definition("ContextPolicy", _id("cpo"), "presale-context"),
        ]
    )
    factory, store = PresaleRuntimeFactory.create_postgres(
        dsn=PG_DSN,
        definition_repository=registry,
        definition_selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"},
            "prompt_package": {"kind": "PromptPackage", "namespace": "presale", "key": "presale-prompt"},
            "context_policy": {"kind": "ContextPolicy", "namespace": "presale", "key": "presale-context"},
        },
        sources=[_source()],
    )
    return factory, store


@pytest.mark.asyncio
async def test_create_postgres_end_to_end():
    """B-03: create_postgres() + PresaleAgent + Harness → FINALIZE."""
    factory, store = _factory()

    agent = factory.create_agent()
    outcome = await Harness().execute(_question(key=f"pg-e2e-{uuid.uuid4().hex[:8]}"), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert outcome.answer_draft is not None
    assert outcome.answer_draft.need_human is False

    await store.close()


@pytest.mark.asyncio
async def test_create_postgres_idempotent_replay():
    """B-03: Same key → same answer_draft on PostgreSQL."""
    factory, store = _factory()

    agent = factory.create_agent()
    key = f"pg-idem-e2e-{uuid.uuid4().hex[:8]}"
    first = await Harness().execute(_question(key=key), agent)
    second = await Harness().execute(_question(key=key), agent)

    assert second.answer_draft.answer_id == first.answer_draft.answer_id
    assert second.answer_draft.answer_text == first.answer_draft.answer_text

    await store.close()
