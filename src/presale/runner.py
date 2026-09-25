"""V1 presale end-to-end application seam."""

from __future__ import annotations

from uuid import UUID, uuid4

from agent_platform_contracts.policies import canonical_sha256

from .answer import AnswerGenerationError, GeneratorPort, PresaleAnswerGenerator
from .context import ContextBuildError, PresaleContextBuilder
from .contracts import ProductQuestion
from .definitions import (
    DefinitionResolutionError,
    DefinitionSource,
    StaticDefinitionSource,
)
from .disposition import AnswerDispositionService, HumanDispositionRecord
from .idempotency import IdempotencyConflictError as IdempotencyConflictError
from .idempotency import IdempotencyRecord
from .knowledge import (
    DeterministicKnowledgeRetriever,
    KnowledgeSource,
    RetrievalPort,
    RetrievalResult,
    RetrievalStatus,
)
from .ports import (
    AnswerDraftRepository,
    DispositionRepository,
    EvidenceRepository,
    IdempotencyRepository,
    ProductQuestionRepository,
    RunTraceRepository,
)
from .trace import PresaleRunTracer, TraceError


class QaRuntimeError(ValueError):
    """A presale QA run failed without a trustworthy result."""


def _uuid7() -> UUID:
    value = uuid4().int
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0x3 << 62)
    value |= 0x2 << 62
    return UUID(int=value)


class PresaleQaResult:
    """A completed presale QA run and its entry points."""

    def __init__(self, *, run_ref: str, answer_draft, trace, evidence_items=None):
        self.run_ref = run_ref
        self.answer_draft = answer_draft
        self.trace = trace
        # Retrieval evidence (with content) for this run; empty when the run
        # found nothing or a replay could not reload persisted evidence.
        self.evidence_items = list(evidence_items or [])


class PresaleQaRunner:
    """Compose retrieval, context, generation, disposition and tracing.

    The runner is an application facade: it wires the domain services and
    delegates all persistence to injected ports. It is async because the
    port adapters are async.
    """

    def __init__(
        self,
        *,
        sources: list[KnowledgeSource],
        retriever: RetrievalPort | None = None,
        generator: GeneratorPort | None = None,
        context_budget_tokens: int = 1000,
        min_evidence_for_answer: int = 1,
        task_id: str | None = None,
        agent_run_id: str | None = None,
        definition_source: DefinitionSource | None = None,
        question_repo: ProductQuestionRepository | None = None,
        evidence_repo: EvidenceRepository | None = None,
        answer_repo: AnswerDraftRepository | None = None,
        disposition_repo: DispositionRepository | None = None,
        trace_repo: RunTraceRepository | None = None,
        idempotency_repo: IdempotencyRepository | None = None,
    ):
        from .adapters.in_memory import (
            InMemoryAnswerDraftRepository,
            InMemoryDispositionRepository,
            InMemoryEvidenceRepository,
            InMemoryIdempotencyRepository,
            InMemoryProductQuestionRepository,
            InMemoryRunTraceRepository,
        )

        self._retriever = (
            retriever if retriever is not None else DeterministicKnowledgeRetriever(sources)
        )
        self._min_evidence_for_answer = min_evidence_for_answer
        self._context_builder = PresaleContextBuilder(
            total_tokens=context_budget_tokens,
            per_source_tokens={"evidence": context_budget_tokens},
        )
        self._generator = generator if generator is not None else PresaleAnswerGenerator()
        self._question_repo = question_repo or InMemoryProductQuestionRepository()
        self._evidence_repo = evidence_repo or InMemoryEvidenceRepository()
        self._answer_repo = answer_repo or InMemoryAnswerDraftRepository()
        self._dispositions = AnswerDispositionService(
            disposition_repo or InMemoryDispositionRepository(),
            answer_repo or InMemoryAnswerDraftRepository(),
        )
        self._tracer = PresaleRunTracer(trace_repo or InMemoryRunTraceRepository())
        self._idempotency_repo = idempotency_repo or InMemoryIdempotencyRepository()
        self._definition_source = definition_source or StaticDefinitionSource()
        self._task_id = task_id
        self._agent_run_id = agent_run_id

    @staticmethod
    def _escalation(retrieval: RetrievalResult, min_evidence: int) -> tuple[bool, str | None]:
        """Corrective-RAG policy: should this retrieval be routed to a human?

        Low confidence -> require human review regardless of the generator: no
        evidence at all (``NO_EVIDENCE``), conflicting sources (``CONFLICT``), or a
        matched retrieval with fewer than ``min_evidence`` supporting items.
        """
        if retrieval.status is RetrievalStatus.NO_EVIDENCE:
            return True, "NO_EVIDENCE"
        if retrieval.status is RetrievalStatus.CONFLICT:
            return True, "CONFLICT"
        if (
            retrieval.status is RetrievalStatus.MATCHED
            and len(retrieval.evidence_items) < min_evidence
        ):
            return True, "LOW_CONFIDENCE"
        return False, None

    async def ask(self, question: ProductQuestion) -> PresaleQaResult:
        business_content = (question.product_id, question.question_text)
        business_digest = canonical_sha256(
            {"product_id": business_content[0], "question_text": business_content[1]}
        )
        run_id = self._agent_run_id or f"run_{_uuid7()}"
        task_id = self._task_id or f"tsk_{_uuid7()}"
        run_ref = {"kind": "AgentRun", "id": run_id}
        claim = await self._idempotency_repo.claim(
            IdempotencyRecord(
                tenant_id=question.tenant_id,
                idempotency_key=question.idempotency_key,
                business_content_digest=business_digest,
                run_ref=run_id,
                created_at=question.requested_at,
            )
        )
        # A durable draft for the claimed run means a prior attempt produced an
        # answer; replay it instead of generating again, even when a fixed
        # agent_run_id makes claim.run_ref == run_id.
        try:
            draft = await self._answer_repo.get_by_run(claim.run_ref, tenant_id=question.tenant_id)
        except Exception as exc:
            # A storage fault while reading the durable draft must surface
            # cleanly and leave the claim unchanged (retryable), not propagate
            # raw out of ask().
            raise QaRuntimeError(str(exc)) from exc
        if claim.run_ref != run_id or claim.status == "succeeded" or draft is not None:
            if draft is None:
                raise QaRuntimeError("IDEMPOTENCY_RESULT_NOT_READY")
            try:
                trace = await self._tracer.get(claim.run_ref, tenant_id=question.tenant_id)
            except Exception as exc:
                # Mirror the answer-read guard: any storage/deserialization fault
                # while reading the trace must surface cleanly and leave the claim
                # unchanged (retryable), not propagate raw out of ask().
                raise QaRuntimeError(str(exc)) from exc
            self._dispositions.register(draft, technical_status="succeeded")
            # Only finalize an in_progress claim to succeeded once the replayed
            # trace actually carries the answer, mirroring the fresh path's
            # completeness guard. Finalizing an unattached trace would freeze an
            # incomplete record as canonical with no recovery path.
            if trace.answer_draft_id is not None:
                await self._confirm_succeeded(question)
            try:
                replay_evidence = await self._evidence_repo.get_by_run(
                    claim.run_ref, tenant_id=question.tenant_id
                )
            except Exception:
                # Missing/failed evidence reload must not block a replayed
                # answer; the UI degrades to locator-only evidence.
                replay_evidence = []
            return PresaleQaResult(
                run_ref=claim.run_ref,
                answer_draft=draft,
                trace=trace,
                evidence_items=replay_evidence,
            )

        trace_id: str | None = None
        answer_persisted = False
        completed = False
        try:
            frozen = await self._definition_source.resolve(tenant_id=question.tenant_id)
            configuration_refs = frozen.configuration_refs

            await self._question_repo.save(question)

            trace_id = await self._tracer.start(
                question=question,
                task_id=task_id,
                agent_run_id=run_id,
                configuration_refs=configuration_refs,
            )

            retrieval = self._retriever.retrieve(question)
            if retrieval.status.value in {"matched"}:
                await self._tracer.record_stage(
                    trace_id,
                    tenant_id=question.tenant_id,
                    stage="knowledge_retrieved",
                    detail=retrieval.status.value,
                )
                await self._evidence_repo.save_evidence(run_id, retrieval.evidence_items)
                context_package = self._context_builder.build(
                    question,
                    [{"evidence": item, "priority": 80} for item in retrieval.evidence_items],
                    run_ref=run_ref,
                    policy_ref=frozen.policy_ref,
                )
                await self._tracer.attach_context(
                    trace_id, tenant_id=question.tenant_id, context_package=context_package
                )
                await self._tracer.record_stage(
                    trace_id,
                    tenant_id=question.tenant_id,
                    stage="context_built",
                    detail=context_package.run_ref.id,
                )
            draft = self._generator.generate(
                question,
                retrieval,
                run_ref=run_ref,
                configuration_refs=configuration_refs,
            )

            # Corrective-RAG: low retrieval confidence forces a human-review draft
            # regardless of the generator, so the answer routes to human review.
            escalate, reason = self._escalation(retrieval, self._min_evidence_for_answer)
            if escalate and not draft.need_human:
                draft = draft.model_copy(
                    update={
                        "need_human": True,
                        "reason_codes": [*draft.reason_codes, reason],
                    }
                )

            await self._answer_repo.save(draft, tenant_id=question.tenant_id)
            answer_persisted = True
            self._dispositions.register(draft, technical_status="succeeded")
            await self._tracer.attach_answer(trace_id, tenant_id=question.tenant_id, answer=draft)
            await self._tracer.record_stage(
                trace_id,
                tenant_id=question.tenant_id,
                stage="answer_generated",
                detail=draft.answer_id,
            )

            result = PresaleQaResult(
                run_ref=run_id,
                answer_draft=draft,
                trace=await self._tracer.get(trace_id, tenant_id=question.tenant_id),
                evidence_items=retrieval.evidence_items,
            )
            completed = True
            await self._idempotency_repo.update_status(
                question.tenant_id, question.idempotency_key, "succeeded"
            )
            return result
        except DefinitionResolutionError as exc:
            await self._mark_failed(question, trace_id=None, reason=str(exc), mark_trace=False)
            raise QaRuntimeError(str(exc)) from exc
        except (AnswerGenerationError, ContextBuildError) as exc:
            await self._mark_failed(question, trace_id=trace_id, reason=str(exc), mark_trace=True)
            raise QaRuntimeError(str(exc)) from exc
        except Exception as exc:
            if completed:
                # The full result (draft + readable trace) was built; only the
                # final succeeded write is in doubt. Best-effort confirm it; a
                # transient failure leaves the claim in_progress and a retry
                # replays the already-built result.
                await self._confirm_succeeded(question)
            elif answer_persisted:
                # The draft is durable but the trace could not be confirmed
                # (attach/record/read failed). Do NOT mark succeeded (not
                # replayable) nor failed (would force a duplicate); leave the
                # claim in_progress so a retry replays the durable draft.
                pass
            else:
                await self._mark_failed(
                    question,
                    trace_id=trace_id,
                    reason="ANSWER_GENERATION_FAILED",
                    mark_trace=True,
                )
            raise QaRuntimeError("ANSWER_GENERATION_FAILED") from exc

    async def _mark_failed(
        self,
        question: ProductQuestion,
        *,
        trace_id: str | None,
        reason: str,
        mark_trace: bool,
    ) -> None:
        """Best-effort failure cleanup that must never mask the original error.

        Trace marking and claim (idempotency) marking are independent: a failure
        in one must not prevent the other, so the claim can never be left stuck
        in_progress because the trace cleanup raised.
        """
        if mark_trace and trace_id is not None:
            try:
                await self._tracer.fail(trace_id, tenant_id=question.tenant_id, reason=reason)
            except Exception:
                pass
        try:
            await self._idempotency_repo.update_status(
                question.tenant_id, question.idempotency_key, "failed"
            )
        except Exception:
            pass

    async def _confirm_succeeded(self, question: ProductQuestion) -> None:
        """Best-effort mark a completed run as succeeded (already durable)."""
        try:
            await self._idempotency_repo.update_status(
                question.tenant_id, question.idempotency_key, "succeeded"
            )
        except Exception:
            pass

    async def accept(
        self, answer_id: str, *, actor_id: str, reason: str, tenant_id: str
    ) -> HumanDispositionRecord:
        record = await self._dispositions.accept(
            answer_id, actor_id=actor_id, reason=reason, tenant_id=tenant_id
        )
        await self._trace_disposition(record, escalated=False)
        return record

    async def edit(
        self,
        answer_id: str,
        *,
        edited_text: str,
        actor_id: str,
        reason: str,
        tenant_id: str,
    ) -> HumanDispositionRecord:
        record = await self._dispositions.edit(
            answer_id,
            edited_text=edited_text,
            actor_id=actor_id,
            reason=reason,
            tenant_id=tenant_id,
        )
        await self._trace_disposition(record, escalated=False)
        return record

    async def escalate(
        self, answer_id: str, *, actor_id: str, reason: str, tenant_id: str
    ) -> HumanDispositionRecord:
        record = await self._dispositions.escalate(
            answer_id, actor_id=actor_id, reason=reason, tenant_id=tenant_id
        )
        await self._trace_disposition(record, escalated=True)
        return record

    async def discard(
        self, answer_id: str, *, actor_id: str, reason: str, tenant_id: str
    ) -> HumanDispositionRecord:
        record = await self._dispositions.discard(
            answer_id, actor_id=actor_id, reason=reason, tenant_id=tenant_id
        )
        await self._trace_disposition(record, escalated=False)
        return record

    async def _trace_disposition(self, record: HumanDispositionRecord, *, escalated: bool) -> None:
        run_ref = record.original_answer.run_ref.id
        if escalated:
            await self._tracer.mark_disposition_escalated(run_ref, tenant_id=record.tenant_id)
        else:
            await self._tracer.mark_disposition_complete(run_ref, tenant_id=record.tenant_id)

    async def get_trace(self, run_ref: str, *, tenant_id: str | None = None):
        if not tenant_id:
            raise TraceError("TENANT_ID_REQUIRED")
        return await self._tracer.get(run_ref, tenant_id=tenant_id)


__all__ = ["IdempotencyConflictError", "PresaleQaResult", "PresaleQaRunner", "QaRuntimeError"]
