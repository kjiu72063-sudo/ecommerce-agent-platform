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

    async def run(self, question: Any) -> AgentRunResult: ...


class Loop:
    """Decide, after each AgentStep, whether to continue or reach a terminal.

    Safe by default: a step that needs human review is terminal (never loops
    again); a completed step finalizes. The single-step presale agent never
    triggers ``CONTINUE``; multi-step looping is exercised by other agents.
    """

    def decide(self, step: AgentStep) -> LoopDecision:
        if step.need_human:
            return LoopDecision.NEED_HUMAN
        return LoopDecision.FINALIZE


class Harness:
    """Execute an Agent, record steps, and run the Loop to a terminal decision."""

    def __init__(self, *, loop: Loop | None = None, max_steps: int = 5):
        self._loop = loop or Loop()
        self._max_steps = max_steps

    async def execute(self, question: Any, agent: Agent) -> AgentOutcome:
        steps: list[AgentStep] = []
        last: AgentRunResult | None = None
        for _ in range(self._max_steps):
            last = await agent.run(question)
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
    "TerminalDecision",
    "format_outcome",
]
