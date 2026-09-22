"""方向3: B5 remaining Loop strategies - ReactLoop / RepairLoop / ReviewRefineLoop.

All three read deterministic signals from AgentStep (tool_calls status /
need_human / index) and return LoopDecision — no LLM calls in the Loop layer.
"""

from __future__ import annotations

import pytest

from agent_runtime.harness import (
    AgentRunResult,
    AgentStep,
    Harness,
    LoopDecision,
    ReactLoop,
    RepairLoop,
    ReviewRefineLoop,
    TerminalDecision,
)


def _step(index: int, *, need_human: bool = False, tool_calls: list[dict] | None = None):
    return AgentStep(index=index, need_human=need_human, tool_calls=tool_calls or [])


# --- RepairLoop ---


def test_repair_loop_continues_on_error():
    """RepairLoop continues while a tool_call reports error status."""
    loop = RepairLoop(max_attempts=3)
    step = _step(1, tool_calls=[{"tool": "write", "status": "error"}])
    assert loop.decide(step) is LoopDecision.CONTINUE


def test_repair_loop_finalizes_when_no_error():
    """RepairLoop finalizes when the step has no error."""
    loop = RepairLoop(max_attempts=3)
    step = _step(1, tool_calls=[{"tool": "write", "status": "ok"}])
    assert loop.decide(step) is LoopDecision.FINALIZE


def test_repair_loop_stops_after_max_attempts():
    """RepairLoop gives up (STOP) when attempts are exhausted."""
    loop = RepairLoop(max_attempts=3)
    step = _step(3, tool_calls=[{"tool": "write", "status": "error"}])
    assert loop.decide(step) is LoopDecision.STOP


def test_repair_loop_need_human_is_terminal():
    """RepairLoop never continues after need_human."""
    loop = RepairLoop(max_attempts=3)
    step = _step(1, need_human=True, tool_calls=[{"tool": "write", "status": "error"}])
    assert loop.decide(step) is LoopDecision.NEED_HUMAN


# --- ReviewRefineLoop ---


def test_review_refine_loop_continues_on_review():
    """ReviewRefineLoop continues while a tool_call reports review status."""
    loop = ReviewRefineLoop(max_refinements=2)
    step = _step(1, tool_calls=[{"tool": "generate", "status": "review"}])
    assert loop.decide(step) is LoopDecision.CONTINUE


def test_review_refine_loop_finalizes_on_approved():
    """ReviewRefineLoop finalizes when the step is approved (no review signal)."""
    loop = ReviewRefineLoop(max_refinements=2)
    step = _step(1, tool_calls=[{"tool": "generate", "status": "approved"}])
    assert loop.decide(step) is LoopDecision.FINALIZE


def test_review_refine_loop_stops_after_max_refinements():
    """ReviewRefineLoop stops when refinements are exhausted."""
    loop = ReviewRefineLoop(max_refinements=2)
    step = _step(3, tool_calls=[{"tool": "generate", "status": "review"}])
    assert loop.decide(step) is LoopDecision.STOP


# --- ReactLoop ---


def test_react_loop_continues_on_action():
    """ReactLoop continues while the agent wants to act again."""
    loop = ReactLoop(max_actions=3)
    step = _step(1, tool_calls=[{"tool": "search", "status": "act"}])
    assert loop.decide(step) is LoopDecision.CONTINUE


def test_react_loop_finalizes_when_done():
    """ReactLoop finalizes when the agent is done."""
    loop = ReactLoop(max_actions=3)
    step = _step(2, tool_calls=[{"tool": "search", "status": "done"}])
    assert loop.decide(step) is LoopDecision.FINALIZE


def test_react_loop_stops_after_max_actions():
    """ReactLoop stops when max actions are exhausted."""
    loop = ReactLoop(max_actions=3)
    step = _step(3, tool_calls=[{"tool": "search", "status": "act"}])
    assert loop.decide(step) is LoopDecision.STOP


def test_react_loop_need_human_is_terminal():
    """ReactLoop never continues after need_human."""
    loop = ReactLoop(max_actions=3)
    step = _step(1, need_human=True, tool_calls=[{"tool": "search", "status": "act"}])
    assert loop.decide(step) is LoopDecision.NEED_HUMAN


# --- Harness integration (multi-step) ---


class FakeStepAgent:
    """Agent that exposes a scripted result per call."""

    def __init__(self, statuses: list[str]):
        self._statuses = statuses
        self.calls = 0

    async def run(self, question, step_context=None):
        idx = min(self.calls, len(self._statuses) - 1)
        self.calls += 1
        status = self._statuses[idx]
        return AgentRunResult(
            run_ref="run_x",
            need_human=False,
            tool_calls=[{"tool": "t", "status": status}],
        )


@pytest.mark.asyncio
async def test_harness_repair_loop_retries_then_finalizes():
    """Harness + RepairLoop: error -> continue -> ok -> finalize."""
    agent = FakeStepAgent(["error", "ok"])
    harness = Harness(loop=RepairLoop(max_attempts=3), max_steps=5)

    outcome = await harness.execute("q", agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert agent.calls == 2
    assert len(outcome.steps) == 2


@pytest.mark.asyncio
async def test_harness_repair_loop_exhausts_steps():
    """Harness + RepairLoop: persistent errors exhaust -> MAX_STEPS."""
    agent = FakeStepAgent(["error"])
    harness = Harness(loop=RepairLoop(max_attempts=2), max_steps=5)

    outcome = await harness.execute("q", agent)

    assert outcome.terminal is TerminalDecision.MAX_STEPS
    assert agent.calls == 2  # 1 initial + 1 retry then STOP


@pytest.mark.asyncio
async def test_harness_react_loop_multi_action():
    """Harness + ReactLoop: act -> act -> done -> finalize."""
    agent = FakeStepAgent(["act", "act", "done"])
    harness = Harness(loop=ReactLoop(max_actions=4), max_steps=5)

    outcome = await harness.execute("q", agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert agent.calls == 3
