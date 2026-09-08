"""V1 presale end-to-end application seam."""

from __future__ import annotations

from uuid import UUID, uuid4

from agent_platform_contracts.policies import canonical_sha256

from .answer import AnswerGenerationError, PresaleAnswerGenerator
from .context import ContextBuildError, PresaleContextBuilder
from .contracts import ProductQuestion
from .disposition import AnswerDispositionService, HumanDispositionRecord
from .knowledge import DeterministicKnowledgeRetriever, KnowledgeSource
from .trace import PresaleRunTracer


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

    def __init__(self, *, run_ref: str, answer_draft, trace):
        self.run_ref = run_ref
        self.answer_draft = answer_draft
        self.trace = trace


class PresaleQaRunner:
    """Compose retrieval, context, generation, disposition and tracing."""

    def __init__(
        self,
        *,
        sources: list[KnowledgeSource],
        generator: object | None = None,
        context_budget_tokens: int = 1000,
        task_id: str | None = None,
        agent_run_id: str | None = None,
        policy_ref: dict | None = None,
        artifact_ref: dict | None = None,
    ):
        self._retriever = DeterministicKnowledgeRetriever(sources)
        self._context_builder = PresaleContextBuilder(
            total_tokens=context_budget_tokens,
            per_source_tokens={"evidence": context_budget_tokens},
        )
        self._generator = generator if generator is not None else PresaleAnswerGenerator()
        self._dispositions = AnswerDispositionService()
        self._tracer = PresaleRunTracer()
        self._task_id = task_id
        self._agent_run_id = agent_run_id
        self._policy_ref = policy_ref or {
            "kind": "ContextPolicy",
            "id": "cpo_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
            "version": "1.0.0",
            "digest": canonical_sha256({"policy": "presale"}),
        }
        self._artifact_ref = artifact_ref or {
            "id": "art_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f427",
            "digest": canonical_sha256({"artifact": "context"}),
        }

    def ask(self, question: ProductQuestion) -> PresaleQaResult:
        run_id = self._agent_run_id or f"run_{_uuid7()}"
        task_id = self._task_id or f"tsk_{_uuid7()}"
        run_ref = {"kind": "AgentRun", "id": run_id}
        configuration_refs = {"agent_spec": "1.0.0", "prompt_package": "1.0.0"}

        trace_id = self._tracer.start(
            question=question,
            task_id=task_id,
            agent_run_id=run_id,
            configuration_refs=configuration_refs,
        )

        retrieval = self._retriever.retrieve(question)
        try:
            if retrieval.status.value in {"matched"}:
                self._tracer.record_stage(trace_id, "knowledge_retrieved", retrieval.status.value)
                context_package = self._context_builder.build(
                    question,
                    [{"evidence": item, "priority": 80} for item in retrieval.evidence_items],
                    run_ref=run_ref,
                    policy_ref=self._policy_ref,
                    artifact_ref=self._artifact_ref,
                )
                self._tracer.attach_context(trace_id, context_package)
                self._tracer.record_stage(trace_id, "context_built", context_package.run_ref.id)
            draft = self._generator.generate(
                question,
                retrieval,
                run_ref=run_ref,
                configuration_refs=configuration_refs,
            )
        except AnswerGenerationError as exc:
            self._tracer.fail(trace_id, str(exc))
            raise QaRuntimeError(str(exc)) from exc
        except ContextBuildError as exc:
            self._tracer.fail(trace_id, str(exc))
            raise QaRuntimeError(str(exc)) from exc
        except Exception as exc:
            self._tracer.fail(trace_id, "ANSWER_GENERATION_FAILED")
            raise QaRuntimeError("ANSWER_GENERATION_FAILED") from exc

        self._dispositions.register(draft, technical_status="succeeded")
        self._tracer.attach_answer(trace_id, draft)
        self._tracer.record_stage(trace_id, "answer_generated", draft.answer_id)

        return PresaleQaResult(run_ref=run_id, answer_draft=draft, trace=self._tracer.get(trace_id))

    def accept(self, answer_id: str, *, actor_id: str, reason: str) -> HumanDispositionRecord:
        return self._dispositions.accept(answer_id, actor_id=actor_id, reason=reason)

    def edit(
        self, answer_id: str, *, edited_text: str, actor_id: str, reason: str
    ) -> HumanDispositionRecord:
        return self._dispositions.edit(
            answer_id, edited_text=edited_text, actor_id=actor_id, reason=reason
        )

    def escalate(self, answer_id: str, *, actor_id: str, reason: str) -> HumanDispositionRecord:
        return self._dispositions.escalate(answer_id, actor_id=actor_id, reason=reason)

    def discard(self, answer_id: str, *, actor_id: str, reason: str) -> HumanDispositionRecord:
        return self._dispositions.discard(answer_id, actor_id=actor_id, reason=reason)

    def get_trace(self, run_ref: str):
        return self._tracer.get(run_ref)
