"""V1 presale run-trace boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from .answer import AnswerDraft
from .contracts import ProductQuestion

if TYPE_CHECKING:
    from .ports import RunTraceRepository


class TraceError(ValueError):
    """A presale run trace could not be read or mutated."""


class RunStage(StrEnum):
    SUBMITTED = "submitted"
    KNOWLEDGE_RETRIEVED = "knowledge_retrieved"
    CONTEXT_BUILT = "context_built"
    ANSWER_GENERATED = "answer_generated"
    FAILED = "failed"


class DispositionState(StrEnum):
    PENDING = "pending"
    ESCALATED = "escalated"
    COMPLETE = "complete"


@dataclass(frozen=True)
class RetentionPolicy:
    """Immutable retention rule for V1 prototype run traces."""

    retain_days: int = 30

    def is_expired(self, created_at: datetime, now: datetime) -> bool:
        if created_at.tzinfo is None or now.tzinfo is None:
            raise TraceError("TIMEZONE_REQUIRED")
        return created_at <= now - timedelta(days=self.retain_days)


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
    disposition_state: DispositionState = DispositionState.PENDING
    archived: bool = False
    failed: bool = False
    failure_reason: str | None = None


class PresaleRunTracer:
    """Coordinate run provenance persistence through a RunTraceRepository.

    The tracer owns the timeline semantics (stage order, disposition markers)
    and delegates all storage to an injected repository. It is async because
    the repository ports are async.
    """

    def __init__(
        self,
        trace_repo: RunTraceRepository | None = None,
        retention_policy: RetentionPolicy | None = None,
    ):
        if trace_repo is None:
            from .adapters.in_memory import InMemoryRunTraceRepository

            trace_repo = InMemoryRunTraceRepository()
        self._repo = trace_repo
        self._retention = retention_policy or RetentionPolicy()
        self._tenants: dict[str, str] = {}

    def retention_policy(self) -> RetentionPolicy:
        return self._retention

    async def start(
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
                    occurred_at=question.requested_at,
                )
            ],
        )
        self._tenants[run_ref] = question.tenant_id
        await self._repo.save(trace)
        return run_ref

    async def record_stage(self, run_ref: str, *, tenant_id: str, stage: str, detail: str) -> None:
        trace = await self._require(run_ref, tenant_id=tenant_id)
        await self._repo.save(
            trace.model_copy(
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
        )

    async def attach_context(self, run_ref: str, *, tenant_id: str, context_package: Any) -> None:
        trace = await self._require(run_ref, tenant_id=tenant_id)
        await self._repo.save(
            trace.model_copy(update={"context_package_ref": context_package.run_ref.id})
        )

    async def attach_answer(self, run_ref: str, *, tenant_id: str, answer: AnswerDraft) -> None:
        trace = await self._require(run_ref, tenant_id=tenant_id)
        await self._repo.save(trace.model_copy(update={"answer_draft_id": answer.answer_id}))

    async def fail(self, run_ref: str, *, tenant_id: str, reason: str) -> None:
        trace = await self._require(run_ref, tenant_id=tenant_id)
        await self._repo.save(
            trace.model_copy(
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
        )

    async def mark_disposition(
        self, run_ref: str, *, tenant_id: str, state: DispositionState
    ) -> None:
        await self._repo.mark_disposition(run_ref, tenant_id=tenant_id, state=str(state.value))

    async def mark_disposition_complete(self, run_ref: str, *, tenant_id: str) -> None:
        await self.mark_disposition(run_ref, tenant_id=tenant_id, state=DispositionState.COMPLETE)

    async def mark_disposition_escalated(self, run_ref: str, *, tenant_id: str) -> None:
        await self.mark_disposition(run_ref, tenant_id=tenant_id, state=DispositionState.ESCALATED)

    async def get(self, run_ref: str, *, tenant_id: str | None = None) -> PresaleRunTrace:
        if not tenant_id:
            raise TraceError("TENANT_ID_REQUIRED")
        from .ports import NotFoundError

        try:
            return await self._repo.get(run_ref, tenant_id=tenant_id)
        except NotFoundError as exc:
            owner_tenant = self._tenants.get(run_ref)
            if owner_tenant is not None and owner_tenant != tenant_id:
                raise TraceError("OUT_OF_SCOPE") from exc
            raise TraceError("TRACE_NOT_FOUND") from exc

    async def _require(self, run_ref: str, *, tenant_id: str) -> PresaleRunTrace:
        from .ports import NotFoundError

        try:
            return await self._repo.get(run_ref, tenant_id=tenant_id)
        except NotFoundError as exc:
            raise TraceError("TRACE_NOT_FOUND") from exc
