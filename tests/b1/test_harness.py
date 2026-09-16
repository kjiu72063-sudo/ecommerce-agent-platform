"""T01: Harness drives the presale QA agent to an observable terminal."""

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import Harness, TerminalDecision
from presale.agent import PresaleAgent
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runner import PresaleQaRunner


def source(
    *, season="适合夏季使用", tenant_id="tenant-demo", product_id="product-001", status="published"
):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id=product_id,
        status=status,
        fields={"spec": {"season": season}},
    )


def question(*, idempotency_key="harness-key-0001"):
    return ProductQuestion(
        question_id="question-harness",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key=idempotency_key,
    )


@pytest.mark.asyncio
async def test_matched_question_finalizes():
    runner = PresaleQaRunner(sources=[source()])
    harness = Harness()

    outcome = await harness.execute(question(), PresaleAgent(runner))

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 1
    assert outcome.steps[0].index == 1
    assert outcome.answer_draft is not None
    assert outcome.answer_draft.need_human is False
    assert outcome.run_ref


@pytest.mark.asyncio
async def test_no_evidence_reaches_need_human_terminal():
    runner = PresaleQaRunner(sources=[source(product_id="product-other")])
    harness = Harness()

    outcome = await harness.execute(question(), PresaleAgent(runner))

    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    assert outcome.answer_draft.need_human is True


@pytest.mark.asyncio
async def test_harness_preserves_idempotency():
    runner = PresaleQaRunner(
        sources=[source()],
        agent_run_id="run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
    )
    harness = Harness()

    first = await harness.execute(question(), PresaleAgent(runner))
    second = await harness.execute(question(), PresaleAgent(runner))

    assert first.run_ref == second.run_ref
    assert first.answer_draft.answer_id == second.answer_draft.answer_id
    assert first.terminal is second.terminal


@pytest.mark.asyncio
async def test_presale_runner_ask_still_usable_directly():
    runner = PresaleQaRunner(sources=[source()])

    result = await runner.ask(question(idempotency_key="harness-key-0002"))

    assert result.answer_draft.answer_text
    assert result.answer_draft.need_human is False
