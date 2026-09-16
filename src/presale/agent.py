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
            tool_calls=[self._retrieve_tool_call(result, question)],
        )

    @staticmethod
    def _retrieve_tool_call(result, question: ProductQuestion) -> dict:
        draft = result.answer_draft
        reason_codes = list(getattr(draft, "reason_codes", []))
        evidence_refs = list(getattr(draft, "evidence_refs", []))
        if evidence_refs:
            status = "matched"
        elif "OUT_OF_SCOPE" in reason_codes:
            status = "out_of_scope"
        elif "CONFLICTING_EVIDENCE" in reason_codes:
            status = "conflict"
        else:
            status = "no_evidence"
        return {
            "tool": "retrieve",
            "tenant_id": question.tenant_id,
            "product_id": question.product_id,
            "status": status,
            "evidence_count": len(evidence_refs),
            "reason_codes": reason_codes,
        }


__all__ = ["PresaleAgent"]
