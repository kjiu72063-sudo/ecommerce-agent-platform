"""T03: Loop terminal semantics and the max_steps bound."""

import inspect
from datetime import datetime, timezone

import pytest

from agent_runtime.harness import (
    Agent,
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


# --- B5 T01: LoopStrategy Protocol + SinglePassLoop ---


from agent_runtime.harness import LoopStrategy, SinglePassLoop, StepContext


def test_single_pass_loop_need_human():
    """SinglePassLoop returns NEED_HUMAN when step.need_human is True."""
    loop = SinglePassLoop()
    step_need = type("S", (), {"need_human": True})()
    assert loop.decide(step_need) is LoopDecision.NEED_HUMAN


def test_single_pass_loop_finalize():
    """SinglePassLoop returns FINALIZE when step.need_human is False."""
    loop = SinglePassLoop()
    step_ok = type("S", (), {"need_human": False})()
    assert loop.decide(step_ok) is LoopDecision.FINALIZE


def test_loop_alias_is_single_pass_loop():
    """Loop is an alias for SinglePassLoop (backward compatibility)."""
    assert Loop is SinglePassLoop


def test_single_pass_loop_satisfies_loop_strategy():
    """SinglePassLoop satisfies the LoopStrategy Protocol (structural typing)."""
    loop = SinglePassLoop()
    # Protocol check: must have a decide method accepting AgentStep
    assert hasattr(loop, "decide") and callable(loop.decide)


@pytest.mark.asyncio
async def test_harness_accepts_loop_strategy_protocol():
    """Harness accepts any object satisfying LoopStrategy (not just Loop subclass)."""

    class CustomStrategy:
        def decide(self, step):
            if step.need_human:
                return LoopDecision.NEED_HUMAN
            return LoopDecision.FINALIZE

    agent = FakeAgent(need_human=False)
    harness = Harness(loop=CustomStrategy(), max_steps=3)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 1


def test_step_context_creation():
    """StepContext carries step_index and previous_tool_calls."""
    ctx = StepContext(step_index=2, previous_tool_calls=[{"tool": "retrieve", "status": "no_evidence"}])
    assert ctx.step_index == 2
    assert len(ctx.previous_tool_calls) == 1
    assert ctx.previous_tool_calls[0]["status"] == "no_evidence"


@pytest.mark.asyncio
async def test_agent_protocol_accepts_step_context():
    """Agent.run accepts optional step_context (D-B10 / ADR-0001)."""

    class ContextRecordingAgent:
        def __init__(self):
            self.received_ctx = None

        async def run(self, question, step_context=None):
            self.received_ctx = step_context
            return AgentRunResult(run_ref="run_ctx", need_human=False)

    agent = ContextRecordingAgent()
    ctx = StepContext(step_index=2, previous_tool_calls=[{"tool": "retrieve"}])

    # Calling with step_context should not raise
    result = await agent.run(question(), step_context=ctx)

    assert agent.received_ctx is ctx
    assert result.run_ref == "run_ctx"


@pytest.mark.asyncio
async def test_agent_run_without_step_context_backward_compat():
    """Agent.run called without step_context still works (backward compat)."""

    class SimpleAgent:
        async def run(self, question, step_context=None):
            return AgentRunResult(run_ref="run_simple", need_human=False)

    agent = SimpleAgent()
    result = await agent.run(question())

    assert result.run_ref == "run_simple"


def test_agent_protocol_signature_includes_step_context():
    """Agent Protocol declares step_context in its run signature."""
    import inspect

    sig = inspect.signature(Agent.run)
    params = list(sig.parameters.keys())
    assert "step_context" in params, f"Agent.run params: {params}"


def test_presale_agent_accepts_step_context():
    """PresaleAgent.run signature accepts step_context parameter."""
    from presale.agent import PresaleAgent

    sig = inspect.signature(PresaleAgent.run)
    params = list(sig.parameters.keys())
    assert "step_context" in params, f"PresaleAgent.run params: {params}"
