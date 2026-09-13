"""Production persistence guarantees: ports are really used end to end,
and a trace survives across a new runner instance (restart semantics)."""

from datetime import datetime, timezone

import pytest

from presale.adapters.sqlite import (
    SQLiteAnswerDraftRepository,
    SQLiteDispositionRepository,
    SQLiteEvidenceRepository,
    SQLiteIdempotencyRepository,
    SQLitePresaleStore,
    SQLiteProductQuestionRepository,
    SQLiteRunTraceRepository,
)
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runner import PresaleQaRunner

QUESTION = ProductQuestion(
    question_id="question-persist",
    tenant_id="tenant-demo",
    submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    product_id="product-001",
    question_text="这款商品适合夏季使用吗？",
    requested_at=datetime.now(timezone.utc),
    idempotency_key="persist-key-001",
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


def _sqlite_runner(store):
    return PresaleQaRunner(
        sources=[source()],
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
        idempotency_repo=SQLiteIdempotencyRepository(store),
    )


@pytest.mark.asyncio
async def test_ports_persist_main_path(tmp_path):
    store = SQLitePresaleStore(tmp_path / "presale.sqlite3")
    runner = _sqlite_runner(store)
    result = await runner.ask(QUESTION)
    assert result.answer_draft.evidence_refs
    assert result.trace.run_ref == result.run_ref
    store.close()


@pytest.mark.asyncio
async def test_duplicate_submission_after_restart_reuses_existing_result(tmp_path):
    store = SQLitePresaleStore(tmp_path / "presale.sqlite3")
    first = _sqlite_runner(store)
    result = await first.ask(QUESTION)

    restarted = _sqlite_runner(store)
    replay = await restarted.ask(QUESTION)

    assert replay.run_ref == result.run_ref
    assert replay.answer_draft.answer_id == result.answer_draft.answer_id
    store.close()


@pytest.mark.asyncio
async def test_failed_claim_can_be_retried(tmp_path):
    store = SQLitePresaleStore(tmp_path / "presale.sqlite3")

    class FailingGenerator:
        def generate(self, *args, **kwargs):
            raise RuntimeError("temporary")

    first = PresaleQaRunner(
        sources=[source()],
        generator=FailingGenerator(),
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
        idempotency_repo=SQLiteIdempotencyRepository(store),
    )
    with pytest.raises(Exception, match="ANSWER_GENERATION_FAILED"):
        await first.ask(QUESTION)

    retry = PresaleQaRunner(
        sources=[source()],
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
        idempotency_repo=SQLiteIdempotencyRepository(store),
    )
    result = await retry.ask(QUESTION)
    assert result.answer_draft.need_human is False
    store.close()


@pytest.mark.asyncio
async def test_trace_is_readable_by_a_new_runner_instance(tmp_path):
    """A fresh runner (after process 'restart') can read the persisted trace."""
    store = SQLitePresaleStore(tmp_path / "presale.sqlite3")
    first = PresaleQaRunner(
        sources=[source()],
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
    )
    result = await first.ask(QUESTION)
    run_ref = result.run_ref

    # simulate restart: brand-new runner/tracer with no in-memory state
    second = PresaleQaRunner(
        sources=[source()],
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
    )
    trace = await second.get_trace(run_ref, tenant_id="tenant-demo")
    assert trace.run_ref == run_ref
    assert trace.tenant_id == "tenant-demo"
    assert trace.answer_draft_id == result.answer_draft.answer_id
    store.close()
