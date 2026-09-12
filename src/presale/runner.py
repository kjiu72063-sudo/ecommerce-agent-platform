"""V1 presale end-to-end application seam."""

from __future__ import annotations

from uuid import UUID, uuid4

from .answer import AnswerGenerationError, PresaleAnswerGenerator
from .context import ContextBuildError, PresaleContextBuilder
from .contracts import ProductQuestion
from .definitions import (
    DefinitionResolutionError,
    DefinitionSource,
    StaticDefinitionSource,
)
from .disposition import AnswerDispositionService, HumanDispositionRecord
from .knowledge import DeterministicKnowledgeRetriever, KnowledgeSource
from .ports import (
    AnswerDraftRepository,
    DispositionRepository,
    EvidenceRepository,
    ProductQuestionRepository,
    RunTraceRepository,
)
from .trace import PresaleRunTracer, TraceError


class QaRuntimeError(ValueError):
    """A presale QA run failed without a trustworthy result."""


class IdempotencyConflictError(ValueError):
    """The same idempotency key was reused with different business content."""


def _uuid7() -> UUID:
    value = uuid4().int
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0x3 << 62)
    value |= 0x2 << 62
    return UUID(int=value)


class PresaleQaResult:
    """A completed presale QA run and its entry points."""

    def __init__(self, *, run_ref: str, answer_draft, trace):
        self.run_ref = run_ref
        self.answer_draft = answer_draft
        self.trace = trace


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
        generator: object | None = None,
        context_budget_tokens: int = 1000,
        task_id: str | None = None,
        agent_run_id: str | None = None,
        definition_source: DefinitionSource | None = None,
        question_repo: ProductQuestionRepository | None = None,
        evidence_repo: EvidenceRepository | None = None,
        answer_repo: AnswerDraftRepository | None = None,
        disposition_repo: DispositionRepository | None = None,
        trace_repo: RunTraceRepository | None = None,
    ):
        from .adapters.in_memory import (
            InMemoryAnswerDraftRepository,
            InMemoryDispositionRepository,
            InMemoryEvidenceRepository,
            InMemoryProductQuestionRepository,
            InMemoryRunTraceRepository,
        )

        self._retriever = DeterministicKnowledgeRetriever(sources)
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
        self._definition_source = definition_source or StaticDefinitionSource()
        self._idempotency: dict[tuple[str, str], tuple[tuple[str, str], PresaleQaResult]] = {}
        self._task_id = task_id
        self._agent_run_id = agent_run_id

    async def ask(self, question: ProductQuestion) -> PresaleQaResult:
        idempotency_key = (question.tenant_id, question.idempotency_key)
        business_content = (question.product_id, question.question_text)
        existing = self._idempotency.get(idempotency_key)
        if existing:
            previous_content, previous_result = existing
            if previous_content != business_content:
                raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
            return previous_result

        run_id = self._agent_run_id or f"run_{_uuid7()}"
        task_id = self._task_id or f"tsk_{_uuid7()}"
        run_ref = {"kind": "AgentRun", "id": run_id}

        try:
            frozen = await self._definition_source.resolve(tenant_id=question.tenant_id)
        except DefinitionResolutionError as exc:
            raise QaRuntimeError(str(exc)) from exc
        configuration_refs = frozen.configuration_refs

        await self._question_repo.save(question)

        trace_id = await self._tracer.start(
            question=question,
            task_id=task_id,
            agent_run_id=run_id,
            configuration_refs=configuration_refs,
        )

        retrieval = self._retriever.retrieve(question)
        try:
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
                    artifact_ref=frozen.artifact_ref,
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
        except AnswerGenerationError as exc:
            await self._tracer.fail(trace_id, tenant_id=question.tenant_id, reason=str(exc))
            raise QaRuntimeError(str(exc)) from exc
        except ContextBuildError as exc:
            await self._tracer.fail(trace_id, tenant_id=question.tenant_id, reason=str(exc))
            raise QaRuntimeError(str(exc)) from exc
        except Exception as exc:
            await self._tracer.fail(
                trace_id, tenant_id=question.tenant_id, reason="ANSWER_GENERATION_FAILED"
            )
            raise QaRuntimeError("ANSWER_GENERATION_FAILED") from exc

        await self._answer_repo.save(draft, tenant_id=question.tenant_id)
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
        )
        self._idempotency[idempotency_key] = (business_content, result)
        return result

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
