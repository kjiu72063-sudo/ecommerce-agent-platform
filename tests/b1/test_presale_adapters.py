import asyncio
from datetime import datetime, timezone

import pytest

from presale.adapters.in_memory import (
    InMemoryAnswerDraftRepository,
    InMemoryDispositionRepository,
    InMemoryEvidenceRepository,
    InMemoryProductQuestionRepository,
    InMemoryRunTraceRepository,
)
from presale.adapters.sqlite import (
    SQLiteAnswerDraftRepository,
    SQLiteDispositionRepository,
    SQLiteEvidenceRepository,
    SQLitePresaleStore,
    SQLiteProductQuestionRepository,
    SQLiteRunTraceRepository,
)
from presale.answer import PresaleAnswerGenerator
from presale.contracts import ProductQuestion
from presale.disposition import DispositionType, HumanDispositionRecord
from presale.knowledge import EvidenceItem, RetrievalResult, RetrievalStatus
from presale.ports import NotFoundError
from presale.trace import DispositionState, PresaleRunTrace, RunStage, StageRecord


def question():
    return ProductQuestion(
        question_id="question-adapter",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime.now(timezone.utc),
        idempotency_key="adapter-key-001",
    )


RUN_REF = {"kind": "AgentRun", "id": "run_02222222-2222-7222-8222-222222222222"}


def evidence():
    return EvidenceItem(
        source_id="catalog-001",
        source_version="2026.09.01",
        locator="spec.season",
        content_digest="sha256:" + "a" * 64,
        tenant_id="tenant-demo",
        product_id="product-001",
        content="适合夏季使用",
    )


def draft():
    return PresaleAnswerGenerator().generate(
        question(),
        RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=[evidence()]),
        run_ref=RUN_REF,
        configuration_refs={},
    )


def disposition():
    return HumanDispositionRecord(
        disposition=DispositionType.ACCEPTED,
        original_answer=draft(),
        actor_id="usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        reason="确认",
        occurred_at=datetime.now(timezone.utc),
        tenant_id="tenant-demo",
    )


def trace():
    return PresaleRunTrace(
        run_ref=RUN_REF["id"],
        tenant_id="tenant-demo",
        question_id="question-adapter",
        task_id="tsk_02222222-2222-7222-8222-222222222222",
        agent_run_id=RUN_REF["id"],
        configuration_refs={},
        stages=[
            StageRecord(
                stage=RunStage.SUBMITTED,
                detail="q",
                occurred_at=datetime.now(timezone.utc),
            )
        ],
    )


def _in_memory(_tmp_path=None):
    store = type("S", (), {})()
    store.questions = InMemoryProductQuestionRepository()
    store.evidence = InMemoryEvidenceRepository()
    store.drafts = InMemoryAnswerDraftRepository()
    store.dispositions = InMemoryDispositionRepository()
    store.traces = InMemoryRunTraceRepository()
    return store


def _sqlite(tmp_path):
    store = SQLitePresaleStore(tmp_path / "test.sqlite3")
    repo = type("S", (), {})()
    repo.questions = SQLiteProductQuestionRepository(store)
    repo.evidence = SQLiteEvidenceRepository(store)
    repo.drafts = SQLiteAnswerDraftRepository(store)
    repo.dispositions = SQLiteDispositionRepository(store)
    repo.traces = SQLiteRunTraceRepository(store)
    repo._store = store
    return repo


@pytest.mark.parametrize(
    "backend_factory",
    [_in_memory, lambda tmp_path: _sqlite(tmp_path)],
    ids=["in-memory", "sqlite"],
)
def test_adapters_behave_identically_and_enforce_tenant(backend_factory, tmp_path):
    repo = backend_factory(tmp_path)

    async def run():
        await repo.questions.save(question())
        got = await repo.questions.get("question-adapter", tenant_id="tenant-demo")
        assert got.question_id == "question-adapter"
        with pytest.raises(NotFoundError):
            await repo.questions.get("question-adapter", tenant_id="tenant-other")

        await repo.evidence.save_evidence(RUN_REF["id"], [evidence()])
        items = await repo.evidence.get_by_run(RUN_REF["id"], tenant_id="tenant-demo")
        assert len(items) == 1
        with pytest.raises(NotFoundError):
            await repo.evidence.get_by_run(RUN_REF["id"], tenant_id="tenant-other")

        await repo.drafts.save(draft(), tenant_id="tenant-demo")
        assert (await repo.drafts.get_by_run(RUN_REF["id"], tenant_id="tenant-demo")) is not None
        assert (await repo.drafts.get_by_run(RUN_REF["id"], tenant_id="tenant-other")) is None

        await repo.dispositions.save(disposition(), tenant_id="tenant-demo")
        answer_id = disposition().original_answer.answer_id
        got_disposition = await repo.dispositions.get_by_answer(answer_id, tenant_id="tenant-demo")
        assert got_disposition is not None
        assert (await repo.dispositions.get_by_answer(answer_id, tenant_id="tenant-other")) is None

        await repo.traces.save(trace())
        await repo.traces.mark_disposition(RUN_REF["id"], tenant_id="tenant-demo", state="complete")
        t = await repo.traces.get(RUN_REF["id"], tenant_id="tenant-demo")
        assert t.disposition_state is DispositionState.COMPLETE
        await repo.traces.mark_archived(RUN_REF["id"], tenant_id="tenant-demo")
        assert (await repo.traces.get(RUN_REF["id"], tenant_id="tenant-demo")).archived is True
        with pytest.raises(NotFoundError):
            await repo.traces.get(RUN_REF["id"], tenant_id="tenant-other")

        listed = await repo.traces.list_by_tenant(tenant_id="tenant-demo")
        assert len(listed) == 1
        assert listed[0].run_ref == RUN_REF["id"]
        assert await repo.traces.list_by_tenant(tenant_id="tenant-other") == []

    asyncio.run(run())
    if hasattr(repo, "_store"):
        repo._store.close()
