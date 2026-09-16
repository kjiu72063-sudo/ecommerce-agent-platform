"""T04: Harness persistence, replay, and disposition separation."""

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import Harness, TerminalDecision
from presale.adapters.sqlite import (
    SQLiteAnswerDraftRepository,
    SQLiteIdempotencyRepository,
    SQLitePresaleStore,
    SQLiteRunTraceRepository,
)
from presale.agent import PresaleAgent
from presale.contracts import ProductQuestion
from presale.disposition import DispositionType
from presale.knowledge import KnowledgeSource
from presale.runner import PresaleQaRunner

ACTOR = "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"


def source(*, product_id="product-001"):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id=product_id,
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def question(*, idempotency_key="harness-persist-key"):
    return ProductQuestion(
        question_id="question-harness-persist",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": ACTOR},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key=idempotency_key,
    )


def sqlite_runner(store):
    return PresaleQaRunner(
        sources=[source()],
        idempotency_repo=SQLiteIdempotencyRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
    )


@pytest.mark.asyncio
async def test_harness_replay_consistent_across_sqlite_instances(tmp_path):
    store = SQLitePresaleStore(tmp_path / "b4b6.sqlite3")
    q = question()
    try:
        first = await Harness().execute(q, PresaleAgent(sqlite_runner(store)))
        # A fresh runner over the same store replays the same outcome.
        second = await Harness().execute(q, PresaleAgent(sqlite_runner(store)))

        assert second.answer_draft.answer_id == first.answer_draft.answer_id
        assert second.run_ref == first.run_ref
        assert second.terminal is first.terminal
        assert second.steps[0].tool_calls == first.steps[0].tool_calls
        assert second.steps[0].tool_calls[0]["status"] == "matched"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_accept_is_distinct_from_technical_terminal():
    runner = PresaleQaRunner(sources=[source()])
    outcome = await Harness().execute(
        question(idempotency_key="harness-accept-key"), PresaleAgent(runner)
    )

    assert outcome.terminal is TerminalDecision.FINALIZE

    record = await runner.accept(
        outcome.answer_draft.answer_id, actor_id=ACTOR, reason="确认", tenant_id="tenant-demo"
    )

    assert record.disposition is DispositionType.ACCEPTED
    assert record.original_answer.answer_id == outcome.answer_draft.answer_id
    # The technical terminal decision is not mutated by a business disposition.
    assert outcome.terminal is TerminalDecision.FINALIZE
