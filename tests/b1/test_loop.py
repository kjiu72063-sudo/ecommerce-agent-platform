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

    async def run(self, question, step_context=None):
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


# --- B5 T02: Harness multi-step loop + StepContext passing ---


class ContextTrackingAgent:
    """FakeAgent that records step_context received at each step."""

    def __init__(self, *, need_human=False, tool_calls=None):
        self.need_human = need_human
        self._tool_calls = tool_calls or []
        self.received_contexts: list[StepContext | None] = []
        self.calls = 0

    async def run(self, question, step_context=None):
        self.received_contexts.append(step_context)
        self.calls += 1
        return AgentRunResult(
            run_ref="run_track",
            need_human=self.need_human,
            tool_calls=list(self._tool_calls),
        )


class AlwaysContinueLoop:
    def decide(self, step):
        return LoopDecision.CONTINUE


class ContinueThenFinalize:
    def __init__(self, continues=2):
        self._continues = continues

    def decide(self, step):
        if step.index <= self._continues:
            return LoopDecision.CONTINUE
        return LoopDecision.FINALIZE


@pytest.mark.asyncio
async def test_step_context_none_on_first_step():
    """First step receives step_context=None."""
    agent = ContextTrackingAgent()
    harness = Harness(loop=ContinueThenFinalize(continues=0), max_steps=5)

    await harness.execute(question(), agent)

    assert agent.received_contexts[0] is None


@pytest.mark.asyncio
async def test_step_context_passed_on_subsequent_steps():
    """Step N+1 receives StepContext with N's index and tool_calls."""
    tool_calls_step1 = [{"tool": "retrieve", "status": "no_evidence"}]
    agent = ContextTrackingAgent(tool_calls=tool_calls_step1)
    harness = Harness(loop=ContinueThenFinalize(continues=1), max_steps=5)

    await harness.execute(question(), agent)

    assert len(agent.received_contexts) == 2  # step1 + step2
    assert agent.received_contexts[0] is None
    ctx2 = agent.received_contexts[1]
    assert ctx2 is not None
    assert ctx2.step_index == 2
    assert ctx2.previous_tool_calls == tool_calls_step1


@pytest.mark.asyncio
async def test_max_steps_terminal_outputs_last_answer_draft():
    """MAX_STEPS terminal includes last step's answer_draft (D-B11)."""

    class DraftAgent:
        def __init__(self):
            self.calls = 0

        async def run(self, question, step_context=None):
            self.calls += 1
            return AgentRunResult(
                run_ref="run_draft",
                need_human=False,
                answer_draft=f"draft_step_{self.calls}",
            )

    agent = DraftAgent()
    harness = Harness(loop=AlwaysContinueLoop(), max_steps=3)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.MAX_STEPS
    assert outcome.answer_draft == "draft_step_3"
    assert len(outcome.steps) == 3


@pytest.mark.asyncio
async def test_agent_exception_propagates_from_multi_step():
    """Agent exception at step 2 propagates uncaught (D-B13)."""

    class FailOnSecondStep:
        def __init__(self):
            self.calls = 0

        async def run(self, question, step_context=None):
            self.calls += 1
            if self.calls >= 2:
                raise RuntimeError("step 2 failure")
            return AgentRunResult(run_ref="run_fail", need_human=False)

    agent = FailOnSecondStep()
    harness = Harness(loop=AlwaysContinueLoop(), max_steps=5)

    with pytest.raises(RuntimeError, match="step 2 failure"):
        await harness.execute(question(), agent)

    assert agent.calls == 2  # step1 succeeded, step2 raised


@pytest.mark.asyncio
async def test_format_outcome_renders_multi_step():
    """format_outcome correctly renders multi-step outcome."""
    from agent_runtime.harness import format_outcome

    agent = ContextTrackingAgent(tool_calls=[{"tool": "retrieve"}])
    harness = Harness(loop=ContinueThenFinalize(continues=1), max_steps=5)

    outcome = await harness.execute(question(), agent)
    result = format_outcome(outcome)

    assert result["terminal"] == "finalize"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["index"] == 1
    assert result["steps"][1]["index"] == 2


# --- B5 T03: RetryOnLowEvidenceLoop ---


from agent_runtime.harness import RetryOnLowEvidenceLoop


class SteppedAgent:
    """Agent that returns different tool_calls per step to simulate varied evidence."""

    def __init__(self, step_results: list[list[dict]]):
        self._step_results = step_results
        self.calls = 0

    async def run(self, question, step_context=None):
        idx = min(self.calls, len(self._step_results) - 1)
        tool_calls = self._step_results[idx]
        self.calls += 1
        need = any(
            tc.get("status") in ("no_evidence", "conflict", "out_of_scope")
            and not any(t.get("status") == "matched" for t in tool_calls)
            for tc in tool_calls
        )
        return AgentRunResult(
            run_ref="run_stepped",
            need_human=False,
            tool_calls=tool_calls,
            answer_draft=f"draft_{self.calls}",
        )


@pytest.mark.asyncio
async def test_retry_evidence_found_finalize_immediately():
    """T04: Evidence matched -> FINALIZE, 1 step."""
    agent = SteppedAgent(step_results=[[{"tool": "retrieve", "status": "matched"}]])
    harness = Harness(loop=RetryOnLowEvidenceLoop(), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 1
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_retry_no_evidence_then_matched():
    """T05: No evidence -> CONTINUE -> matched -> FINALIZE, 2 steps."""
    agent = SteppedAgent(
        step_results=[
            [{"tool": "retrieve", "status": "no_evidence"}],
            [{"tool": "retrieve", "status": "matched"}],
        ]
    )
    harness = Harness(loop=RetryOnLowEvidenceLoop(max_retries=2), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 2
    assert agent.calls == 2


@pytest.mark.asyncio
async def test_retry_no_evidence_exhausts_retries():
    """T06: No evidence -> continuous -> MAX_STEPS (max_retries+1 steps)."""
    agent = SteppedAgent(
        step_results=[[{"tool": "retrieve", "status": "no_evidence"}]]
    )
    harness = Harness(loop=RetryOnLowEvidenceLoop(max_retries=2), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.MAX_STEPS
    assert len(outcome.steps) == 3  # 1 initial + 2 retries
    assert agent.calls == 3


@pytest.mark.asyncio
async def test_retry_need_human_stops_mid_retry():
    """T07: No evidence -> CONTINUE -> need_human=True -> NEED_HUMAN."""

    class NeedHumanOnSecondStep:
        def __init__(self):
            self.calls = 0

        async def run(self, question, step_context=None):
            self.calls += 1
            if self.calls == 1:
                return AgentRunResult(
                    run_ref="run_nh",
                    need_human=False,
                    tool_calls=[{"tool": "retrieve", "status": "no_evidence"}],
                )
            return AgentRunResult(run_ref="run_nh", need_human=True, tool_calls=[])

    agent = NeedHumanOnSecondStep()
    harness = Harness(loop=RetryOnLowEvidenceLoop(max_retries=3), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    assert len(outcome.steps) == 2
    assert agent.calls == 2


def test_retry_max_retries_configurable():
    """RetryOnLowEvidenceLoop accepts custom max_retries."""
    loop = RetryOnLowEvidenceLoop(max_retries=5)
    assert loop._max_retries == 5


@pytest.mark.asyncio
async def test_retry_default_max_retries():
    """RetryOnLowEvidenceLoop defaults to max_retries=2."""
    agent = SteppedAgent(
        step_results=[[{"tool": "retrieve", "status": "no_evidence"}]]
    )
    harness = Harness(loop=RetryOnLowEvidenceLoop(), max_steps=10)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.MAX_STEPS
    assert len(outcome.steps) == 3  # 1 initial + 2 default retries


@pytest.mark.asyncio
async def test_retry_with_conflict_status():
    """Conflict evidence also triggers CONTINUE (not just no_evidence)."""
    agent = SteppedAgent(
        step_results=[
            [{"tool": "retrieve", "status": "conflict"}],
            [{"tool": "retrieve", "status": "matched"}],
        ]
    )
    harness = Harness(loop=RetryOnLowEvidenceLoop(max_retries=2), max_steps=5)

    outcome = await harness.execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 2
