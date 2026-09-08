"""V1 presale run-trace boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .answer import AnswerDraft
from .contracts import ProductQuestion


class TraceError(ValueError):
    """A presale run trace could not be read or mutated."""


class RunStage(StrEnum):
    SUBMITTED = "submitted"
    KNOWLEDGE_RETRIEVED = "knowledge_retrieved"
    CONTEXT_BUILT = "context_built"
    ANSWER_GENERATED = "answer_generated"
    FAILED = "failed"


class StageRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    stage: RunStage
    detail: str
    occurred_at: datetime


class PresaleRunTrace(BaseModel):
    """Read-only trace of one ProductQuestion run."""

    model_config = ConfigDict(frozen=True)

    run_ref: str
    tenant_id: str
    question_id: str
    task_id: str
    agent_run_id: str
    configuration_refs: dict[str, str]
    stages: list[StageRecord]
    context_package_ref: str | None = None
    answer_draft_id: str | None = None
    failed: bool = False
    failure_reason: str | None = None


class PresaleRunTracer:
    """Record and query minimal run provenance for one presale question."""

    def __init__(self):
        self._traces: dict[str, PresaleRunTrace] = {}

    def start(
        self,
        *,
        question: ProductQuestion,
        task_id: str,
        agent_run_id: str,
        configuration_refs: dict[str, str],
    ) -> str:
        run_ref = agent_run_id
        trace = PresaleRunTrace(
            run_ref=run_ref,
            tenant_id=question.tenant_id,
            question_id=question.question_id,
            task_id=task_id,
            agent_run_id=agent_run_id,
            configuration_refs=dict(configuration_refs),
            stages=[
                StageRecord(
                    stage=RunStage.SUBMITTED,
                    detail=question.question_id,
                    occurred_at=datetime.now(timezone.utc),
                )
            ],
        )
        self._traces[run_ref] = trace
        return run_ref

    def record_stage(self, run_ref: str, stage: str, detail: str) -> None:
        trace = self._require(run_ref)
        self._traces[run_ref] = trace.model_copy(
            update={
                "stages": [
                    *trace.stages,
                    StageRecord(
                        stage=RunStage(stage),
                        detail=detail,
                        occurred_at=datetime.now(timezone.utc),
                    ),
                ]
            }
        )

    def attach_context(self, run_ref: str, context_package: object) -> None:
        trace = self._require(run_ref)
        self._traces[run_ref] = trace.model_copy(
            update={"context_package_ref": context_package.run_ref.id}
        )

    def attach_answer(self, run_ref: str, answer: AnswerDraft) -> None:
        trace = self._require(run_ref)
        self._traces[run_ref] = trace.model_copy(update={"answer_draft_id": answer.answer_id})

    def fail(self, run_ref: str, reason: str) -> None:
        trace = self._require(run_ref)
        self._traces[run_ref] = trace.model_copy(
            update={
                "failed": True,
                "failure_reason": reason,
                "stages": [
                    *trace.stages,
                    StageRecord(
                        stage=RunStage.FAILED,
                        detail=reason,
                        occurred_at=datetime.now(timezone.utc),
                    ),
                ],
            }
        )

    def get(self, run_ref: str, *, tenant_id: str | None = None) -> PresaleRunTrace:
        trace = self._traces.get(run_ref)
        if trace is None:
            raise TraceError("TRACE_NOT_FOUND")
        if tenant_id is not None and trace.tenant_id != tenant_id:
            raise TraceError("OUT_OF_SCOPE")
        return trace

    def _require(self, run_ref: str) -> PresaleRunTrace:
        trace = self._traces.get(run_ref)
        if trace is None:
            raise TraceError("TRACE_NOT_FOUND")
        return trace
