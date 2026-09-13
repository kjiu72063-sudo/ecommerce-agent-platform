from datetime import datetime, timezone

import pytest

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
from presale.ports import NotFoundError

QUESTION = ProductQuestion(
    question_id="question-restart",
    tenant_id="tenant-demo",
    submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    product_id="product-001",
    question_text="这款商品适合夏季使用吗？",
    requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    idempotency_key="restart-key-001",
)


def source():
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id="product-001",
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def sqlite_runner(store):
    return PresaleQaRunner(
        sources=[source()],
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
    )


@pytest.mark.asyncio
async def test_answer_draft_can_be_loaded_by_id_after_restart(tmp_path):
    store = SQLitePresaleStore(tmp_path / "restart.sqlite3")
    first = sqlite_runner(store)
    result = await first.ask(QUESTION)

    draft = await SQLiteAnswerDraftRepository(store).get_by_id(
        result.answer_draft.answer_id, tenant_id="tenant-demo"
    )

    assert draft is not None
    assert draft.answer_id == result.answer_draft.answer_id
    store.close()


@pytest.mark.asyncio
async def test_new_runner_can_continue_disposition_after_restart(tmp_path):
    store = SQLitePresaleStore(tmp_path / "restart.sqlite3")
    first = sqlite_runner(store)
    result = await first.ask(QUESTION)

    restarted = sqlite_runner(store)
    disposition = await restarted.accept(
        result.answer_draft.answer_id,
        actor_id="usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        reason="重启后确认",
        tenant_id="tenant-demo",
    )

    assert disposition.disposition == "accepted"
    trace = await restarted.get_trace(result.run_ref, tenant_id="tenant-demo")
    assert trace.disposition_state.value == "complete"
    store.close()


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_restarted_runner_rejects_duplicate_disposition(tmp_path):
    store = SQLitePresaleStore(tmp_path / "restart.sqlite3")
    first = sqlite_runner(store)
    result = await first.ask(QUESTION)
    await first.accept(
        result.answer_draft.answer_id,
        actor_id="usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        reason="首次确认",
        tenant_id="tenant-demo",
    )

    restarted = sqlite_runner(store)
    with pytest.raises(Exception, match="ALREADY_DISPOSED"):
        await restarted.discard(
            result.answer_draft.answer_id,
            actor_id="usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
            reason="重复处置",
            tenant_id="tenant-demo",
        )
    store.close()


@pytest.mark.asyncio
async def test_wrong_tenant_cannot_load_persisted_draft(tmp_path):
    store = SQLitePresaleStore(tmp_path / "restart.sqlite3")
    first = sqlite_runner(store)
    result = await first.ask(QUESTION)

    with pytest.raises(NotFoundError):
        await SQLiteAnswerDraftRepository(store).get_by_id(
            result.answer_draft.answer_id, tenant_id="tenant-other"
        )
    store.close()
