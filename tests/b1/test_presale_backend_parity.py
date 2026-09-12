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
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runner import PresaleQaRunner

QUESTION = ProductQuestion(
    question_id="question-parity",
    tenant_id="tenant-demo",
    submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    product_id="product-001",
    question_text="这款商品适合夏季使用吗？",
    requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    idempotency_key="parity-key-001",
)


def source():
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id="product-001",
        status="published",
        fields={"spec": {"season": "适合夏季使用", "material": "轻量透气面料"}},
    )


def build_in_memory_runner():
    return PresaleQaRunner(
        sources=[source()],
        question_repo=InMemoryProductQuestionRepository(),
        evidence_repo=InMemoryEvidenceRepository(),
        answer_repo=InMemoryAnswerDraftRepository(),
        disposition_repo=InMemoryDispositionRepository(),
        trace_repo=InMemoryRunTraceRepository(),
    )


def build_sqlite_runner(tmp_path):
    store = SQLitePresaleStore(tmp_path / "parity.sqlite3")
    runner = PresaleQaRunner(
        sources=[source()],
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
    )
    return runner, store


async def run_and_accept(runner):
    result = await runner.ask(QUESTION)
    disposition = await runner.accept(
        result.answer_draft.answer_id,
        actor_id="usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        reason="parity test",
        tenant_id="tenant-demo",
    )
    trace = await runner.get_trace(result.run_ref, tenant_id="tenant-demo")
    return result, disposition, trace


@pytest.mark.asyncio
async def test_inmemory_and_sqlite_have_same_business_result(tmp_path):
    memory_result, memory_disposition, memory_trace = await run_and_accept(
        build_in_memory_runner()
    )
    sqlite_runner, store = build_sqlite_runner(tmp_path)
    sqlite_result, sqlite_disposition, sqlite_trace = await run_and_accept(sqlite_runner)

    assert memory_result.answer_draft.answer_text == sqlite_result.answer_draft.answer_text
    assert memory_result.answer_draft.evidence_refs == sqlite_result.answer_draft.evidence_refs
    assert memory_result.answer_draft.confidence_signal == (
        sqlite_result.answer_draft.confidence_signal
    )
    assert memory_result.answer_draft.need_human == sqlite_result.answer_draft.need_human
    assert memory_trace.context_package_ref == memory_result.run_ref
    assert sqlite_trace.context_package_ref == sqlite_result.run_ref
    assert [stage.stage for stage in memory_trace.stages] == [
        stage.stage for stage in sqlite_trace.stages
    ]
    assert memory_disposition.disposition == sqlite_disposition.disposition
    assert memory_disposition.sent_to_consumer is False
    assert sqlite_disposition.sent_to_consumer is False
    assert memory_trace.disposition_state == sqlite_trace.disposition_state
    store.close()


@pytest.mark.asyncio
async def test_sqlite_result_survives_new_runner_instance(tmp_path):
    runner, store = build_sqlite_runner(tmp_path)
    result = await runner.ask(QUESTION)
    await runner.accept(
        result.answer_draft.answer_id,
        actor_id="usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        reason="persisted",
        tenant_id="tenant-demo",
    )

    restarted, _ = build_sqlite_runner(tmp_path)
    trace = await restarted.get_trace(result.run_ref, tenant_id="tenant-demo")
    assert trace.answer_draft_id == result.answer_draft.answer_id
    assert trace.disposition_state.value == "complete"
    store.close()
