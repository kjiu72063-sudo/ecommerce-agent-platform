"""Drive an existing PresaleQaRunner as a reusable, single-step Agent."""

from __future__ import annotations

from agent_runtime.harness import AgentRunResult

from .contracts import ProductQuestion
from .runner import PresaleQaRunner


class PresaleAgent:
    """Adapt a PresaleQaRunner into the Agent protocol (single step)."""

    def __init__(self, runner: PresaleQaRunner):
        self._runner = runner

    async def run(self, question: ProductQuestion) -> AgentRunResult:
        result = await self._runner.ask(question)
        return AgentRunResult(
            run_ref=result.run_ref,
            answer_draft=result.answer_draft,
            trace=result.trace,
            need_human=result.answer_draft.need_human,
            tool_calls=[],
        )


__all__ = ["PresaleAgent"]
