"""Reusable Agent execution shell (Harness) and loop decision (Loop)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class TerminalDecision(StrEnum):
    FINALIZE = "finalize"
    NEED_HUMAN = "need_human"
    MAX_STEPS = "max_steps"


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
    """Decide the terminal outcome after each AgentStep.

    Bounded and safe: a step that needs human review is terminal (no further
    loop); otherwise the step finalizes. Multi-step ``continue`` is structurally
    reserved for later tools and is not triggered by the single-step presale
    agent.
    """

    def decide(self, step: AgentStep) -> TerminalDecision:
        if step.need_human:
            return TerminalDecision.NEED_HUMAN
        return TerminalDecision.FINALIZE


class Harness:
    """Execute an Agent, record steps, and run the Loop to a terminal decision."""

    def __init__(self, *, loop: Loop | None = None, max_steps: int = 5):
        self._loop = loop or Loop()
        self._max_steps = max_steps

    async def execute(self, question: Any, agent: Agent) -> AgentOutcome:
        run = await agent.run(question)
        steps = [
            AgentStep(
                index=1,
                need_human=run.need_human,
                tool_calls=list(run.tool_calls),
            )
        ]
        if len(steps) >= self._max_steps:
            terminal = TerminalDecision.MAX_STEPS
        else:
            terminal = self._loop.decide(steps[0])
        return AgentOutcome(
            run_ref=run.run_ref,
            steps=steps,
            terminal=terminal,
            answer_draft=run.answer_draft,
            trace=run.trace,
        )


__all__ = [
    "Agent",
    "AgentOutcome",
    "AgentRunResult",
    "AgentStep",
    "Harness",
    "Loop",
    "TerminalDecision",
]
