"""Multi-agent sequential orchestration (AgentCoordinator).

Runs a linear pipeline of ``AgentProtocol`` instances, each driven by its own
``Harness`` (with optional per-agent ``LoopStrategy`` / ``max_steps``). The
previous agent's ``answer_draft.answer_text`` is passed to the next agent as
its question; when an agent yields no draft, the original question is used.

Short-circuit semantics: the first sub-run that reaches NEED_HUMAN or
MAX_STEPS stops the pipeline — later agents do not run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agent_runtime.harness import (
    AgentOutcome,
    AgentRunResult,
    Harness,
    LoopStrategy,
    TerminalDecision,
)


class AgentLike(Protocol):
    """An agent shape the coordinator can drive (duck-typed for test fakes)."""

    async def run(self, question: Any, step_context: Any | None = None) -> AgentRunResult: ...


@dataclass
class CoordinatorOutcome:
    """The observable result of a multi-agent pipeline."""

    sub_outcomes: list[AgentOutcome]
    overall_terminal: TerminalDecision
    overall_answer_draft: Any | None = None


class AgentCoordinator:
    """Sequentially orchestrate multiple agents, short-circuiting on terminal states.

    Each agent is wrapped in a fresh :class:`Harness`; the harness loop strategy
    and max_steps can be configured per agent. The previous agent's
    ``answer_draft.answer_text`` becomes the next agent's question when present;
    otherwise the original question is forwarded.
    """

    def __init__(
        self,
        agents: list[AgentLike],
        *,
        loops: list[LoopStrategy | None] | None = None,
        max_steps: int | list[int] | None = None,
    ):
        if not agents:
            raise ValueError("AgentCoordinator requires at least one agent")
        self._agents = agents
        max_steps_list = (
            [max_steps] * len(agents)
            if isinstance(max_steps, int)
            else (max_steps or [5] * len(agents))
        )
        if len(max_steps_list) != len(agents):
            raise ValueError("max_steps list length must match agents length")
        self._max_steps = max_steps_list
        loops_list = loops or [None] * len(agents)
        self._loops = loops_list

    async def execute(self, question: Any) -> CoordinatorOutcome:
        sub_outcomes: list[AgentOutcome] = []
        current_question = question
        overall_terminal = TerminalDecision.FINALIZE
        overall_draft: Any | None = None

        for index, agent in enumerate(self._agents):
            harness = Harness(loop=self._loops[index], max_steps=self._max_steps[index])
            outcome = await harness.execute(current_question, agent)
            sub_outcomes.append(outcome)

            if outcome.terminal is not TerminalDecision.FINALIZE:
                overall_terminal = outcome.terminal
                overall_draft = outcome.answer_draft
                break

            overall_draft = outcome.answer_draft
            # Forward the answer text (if any) as the next agent's question.
            draft = outcome.answer_draft
            if draft is not None and getattr(draft, "answer_text", None):
                current_question = draft.answer_text
            else:
                current_question = question

        return CoordinatorOutcome(
            sub_outcomes=sub_outcomes,
            overall_terminal=overall_terminal,
            overall_answer_draft=overall_draft,
        )


def format_coordinator_outcome(outcome: CoordinatorOutcome) -> dict[str, Any]:
    """Render a CoordinatorOutcome as observable, machine-readable output."""
    from agent_runtime.harness import format_outcome

    return {
        "overall_terminal": outcome.overall_terminal.value,
        "overall_answer_id": (
            outcome.overall_answer_draft.answer_id if outcome.overall_answer_draft else None
        ),
        "overall_answer_text": (
            outcome.overall_answer_draft.answer_text if outcome.overall_answer_draft else None
        ),
        "sub_outcomes": [format_outcome(sub) for sub in outcome.sub_outcomes],
    }


__all__ = [
    "AgentCoordinator",
    "AgentLike",
    "CoordinatorOutcome",
    "format_coordinator_outcome",
]
