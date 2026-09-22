"""Reusable Agent execution shell (Harness) and loop decision (Loop)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class TerminalDecision(StrEnum):
    FINALIZE = "finalize"
    NEED_HUMAN = "need_human"
    MAX_STEPS = "max_steps"


class LoopDecision(StrEnum):
    CONTINUE = "continue"
    FINALIZE = "finalize"
    NEED_HUMAN = "need_human"
    STOP = "stop"


@dataclass
class StepContext:
    """Information Harness passes to Agent between steps in a multi-step loop.

    First step gets ``None``; subsequent steps carry the previous step's index
    and tool_calls so the Agent can adapt its behaviour.
    """

    step_index: int
    previous_tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentRunResult:
    """The raw result an Agent produces from one execution."""

    run_ref: str
    answer_draft: Any | None = None
    trace: Any | None = None
    need_human: bool = False
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentStep:
    """One recorded execution step of an AgentRun."""

    index: int
    need_human: bool = False
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentOutcome:
    """The observable result of running an Agent to a terminal decision."""

    run_ref: str
    steps: list[AgentStep]
    terminal: TerminalDecision
    answer_draft: Any | None = None
    trace: Any | None = None


class Agent(Protocol):
    """A reusable business capability driven by the Harness."""

    async def run(
        self, question: Any, step_context: StepContext | None = None
    ) -> AgentRunResult: ...


class LoopStrategy(Protocol):
    """Injectable decision strategy for multi-step agent loops.

    Any object with a ``decide(step) -> LoopDecision`` method satisfies this
    protocol — no inheritance required (structural typing).
    """

    def decide(self, step: AgentStep) -> LoopDecision: ...


class SinglePassLoop:
    """Default loop strategy: finalize or need_human on every step, never continue.

    Safe by default: a step that needs human review is terminal (never loops
    again); a completed step finalizes. The single-step presale agent never
    triggers ``CONTINUE``.
    """

    def decide(self, step: AgentStep) -> LoopDecision:
        if step.need_human:
            return LoopDecision.NEED_HUMAN
        return LoopDecision.FINALIZE


# Backward-compatible alias: existing code using `Loop()` continues to work.
Loop = SinglePassLoop


class RetryOnLowEvidenceLoop:
    """Loop strategy that retries when retrieval has no evidence.

    Decision logic (in order):
    1. ``step.need_human`` is True → NEED_HUMAN
    2. At least one tool_call with ``status == "matched"`` → FINALIZE
    3. ``step.index >= max_retries + 1`` → FINALIZE (retries exhausted)
    4. Otherwise → CONTINUE

    ``max_retries`` defaults to 2 (3 total attempts including the first).
    The strategy is deterministic: it reads only AgentStep signals, no LLM.
    """

    def __init__(self, max_retries: int = 2):
        self._max_retries = max_retries

    def decide(self, step: AgentStep) -> LoopDecision:
        if step.need_human:
            return LoopDecision.NEED_HUMAN
        if any(tc.get("status") == "matched" for tc in step.tool_calls):
            return LoopDecision.FINALIZE
        if step.index >= self._max_retries + 1:
            return LoopDecision.STOP
        return LoopDecision.CONTINUE


def _any_status(step: AgentStep, status: str) -> bool:
    return any(tc.get("status") == status for tc in step.tool_calls)


class RepairLoop:
    """Loop strategy that retries a failed step (status == "error").

    Decision logic:
    1. ``step.need_human`` → NEED_HUMAN
    2. Any tool_call with ``status == "error"``:
       - ``step.index < max_attempts`` → CONTINUE (retry)
       - otherwise → STOP (attempts exhausted)
    3. Otherwise → FINALIZE

    ``max_attempts`` defaults to 3 (initial + 2 retries).
    """

    def __init__(self, max_attempts: int = 3):
        self._max_attempts = max_attempts

    def decide(self, step: AgentStep) -> LoopDecision:
        if step.need_human:
            return LoopDecision.NEED_HUMAN
        if _any_status(step, "error"):
            return LoopDecision.CONTINUE if step.index < self._max_attempts else LoopDecision.STOP
        return LoopDecision.FINALIZE


class ReviewRefineLoop:
    """Loop strategy that iterates a draft through review (status == "review").

    Decision logic:
    1. ``step.need_human`` → NEED_HUMAN
    2. Any tool_call with ``status == "review"``:
       - ``step.index < max_refinements`` → CONTINUE (refine again)
       - otherwise → STOP (refinements exhausted)
    3. Otherwise (e.g. status == "approved") → FINALIZE

    ``max_refinements`` defaults to 2 (initial draft + 2 polish rounds).
    """

    def __init__(self, max_refinements: int = 2):
        self._max_refinements = max_refinements

    def decide(self, step: AgentStep) -> LoopDecision:
        if step.need_human:
            return LoopDecision.NEED_HUMAN
        if _any_status(step, "review"):
            return (
                LoopDecision.CONTINUE if step.index < self._max_refinements else LoopDecision.STOP
            )
        return LoopDecision.FINALIZE


class ReactLoop:
    """Loop strategy for observe-act-repeat agents (status == "act" to keep going).

    Decision logic:
    1. ``step.need_human`` → NEED_HUMAN
    2. Any tool_call with ``status == "act"``:
       - ``step.index < max_actions`` → CONTINUE
       - otherwise → STOP (action budget exhausted)
    3. Otherwise (status == "done" or no action signal) → FINALIZE

    ``max_actions`` defaults to 5, bounded by the Harness ``max_steps``.
    """

    def __init__(self, max_actions: int = 5):
        self._max_actions = max_actions

    def decide(self, step: AgentStep) -> LoopDecision:
        if step.need_human:
            return LoopDecision.NEED_HUMAN
        if _any_status(step, "act"):
            return LoopDecision.CONTINUE if step.index < self._max_actions else LoopDecision.STOP
        return LoopDecision.FINALIZE


class Harness:
    """Execute an Agent, record steps, and run the Loop to a terminal decision."""

    def __init__(self, *, loop: LoopStrategy | None = None, max_steps: int = 5):
        self._loop = loop or SinglePassLoop()
        self._max_steps = max_steps

    async def execute(self, question: Any, agent: Agent) -> AgentOutcome:
        steps: list[AgentStep] = []
        last: AgentRunResult | None = None
        for i in range(self._max_steps):
            ctx = (
                StepContext(step_index=i + 1, previous_tool_calls=list(steps[-1].tool_calls))
                if i > 0
                else None
            )
            last = await agent.run(question, step_context=ctx)
            steps.append(
                AgentStep(
                    index=len(steps) + 1,
                    need_human=last.need_human,
                    tool_calls=list(last.tool_calls),
                )
            )
            decision = self._loop.decide(steps[-1])
            if decision is LoopDecision.FINALIZE:
                terminal = TerminalDecision.FINALIZE
                break
            if decision is LoopDecision.NEED_HUMAN:
                terminal = TerminalDecision.NEED_HUMAN
                break
            if decision is LoopDecision.STOP:
                terminal = TerminalDecision.MAX_STEPS
                break
            # CONTINUE: run another step (bounded by the range / max_steps).
        else:
            terminal = TerminalDecision.MAX_STEPS
        assert last is not None
        return AgentOutcome(
            run_ref=last.run_ref,
            steps=steps,
            terminal=terminal,
            answer_draft=last.answer_draft,
            trace=last.trace,
        )


def format_outcome(outcome: AgentOutcome) -> dict[str, Any]:
    """Render an AgentOutcome as observable, machine-readable output."""
    return {
        "run_ref": outcome.run_ref,
        "terminal": outcome.terminal.value,
        "steps": [
            {
                "index": step.index,
                "need_human": step.need_human,
                "tool_calls": step.tool_calls,
            }
            for step in outcome.steps
        ],
        "answer_id": outcome.answer_draft.answer_id if outcome.answer_draft else None,
        "answer_text": outcome.answer_draft.answer_text if outcome.answer_draft else None,
        "need_human": outcome.answer_draft.need_human if outcome.answer_draft else None,
    }


__all__ = [
    "Agent",
    "AgentOutcome",
    "AgentRunResult",
    "AgentStep",
    "Harness",
    "Loop",
    "LoopDecision",
    "LoopStrategy",
    "ReactLoop",
    "RepairLoop",
    "RetryOnLowEvidenceLoop",
    "ReviewRefineLoop",
    "SinglePassLoop",
    "TerminalDecision",
    "format_outcome",
]
