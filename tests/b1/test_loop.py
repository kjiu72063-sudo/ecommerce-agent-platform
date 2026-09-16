"""T03: Loop terminal semantics and the max_steps bound."""

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import (
    AgentRunResult,
    Harness,
    Loop,
    LoopDecision,
    TerminalDecision,
)
from presale.contracts import ProductQuestion


def question():
    return ProductQuestion(
        question_id="question-loop",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key="loop-key-000004",
    )


class FakeAgent:
    def __init__(self, *, need_human=False):
        self.need_human = need_human
        self.calls = 0

    async def run(self, question):
        self.calls += 1
        return AgentRunResult(run_ref="run_x", need_human=self.need_human)


class AlwaysContinueLoop(Loop):
    def decide(self, step):
        return LoopDecision.CONTINUE


class ContinueThenFinalizeLoop(Loop):
    def __init__(self, continues=2):
        self._continues = continues

    def decide(self, step):
        if step.index <= self._continues:
            return LoopDecision.CONTINUE
        return LoopDecision.FINALIZE


class NeedHumanLoop(Loop):
    def decide(self, step):
        return LoopDecision.NEED_HUMAN


@pytest.mark.asyncio
async def test_always_continue_is_bounded_by_max_steps():
    agent = FakeAgent()
    harness = Harness(loop=AlwaysContinueLoop(), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.MAX_STEPS
    assert len(outcome.steps) == 5
    assert agent.calls == 5
    assert outcome.steps[-1].index == 5


@pytest.mark.asyncio
async def test_continue_then_finalize_stops_without_exhausting():
    agent = FakeAgent()
    harness = Harness(loop=ContinueThenFinalizeLoop(continues=2), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 3
    assert agent.calls == 3


@pytest.mark.asyncio
async def test_need_human_stops_loop_immediately():
    agent = FakeAgent(need_human=True)
    harness = Harness(loop=NeedHumanLoop(), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    assert len(outcome.steps) == 1
    assert agent.calls == 1  # no continue after need_human


@pytest.mark.asyncio
async def test_default_loop_finalizes_single_step_without_continue():
    agent = FakeAgent(need_human=False)
    harness = Harness()  # default Loop returns FINALIZE (no continue)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 1
    assert agent.calls == 1
