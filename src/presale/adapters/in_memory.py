"""In-memory adapters for the presale persistence ports.

Each adapter implements one port and enforces the tenant-scoping and
not-found contract declared in :mod:`presale.ports`.
"""

from __future__ import annotations

from ..answer import AnswerDraft
from ..contracts import ProductQuestion
from ..disposition import HumanDispositionRecord
from ..idempotency import IdempotencyConflictError, IdempotencyRecord
from ..knowledge import EvidenceItem
from ..ports import (
    AnswerDraftRepository,
    DispositionRepository,
    EvidenceRepository,
    IdempotencyRepository,
    NotFoundError,
    ProductQuestionRepository,
    RunTraceRepository,
)
from ..trace import DispositionState, PresaleRunTrace


def _ensure_tenant(entity_tenant: str, tenant_id: str) -> None:
    if entity_tenant != tenant_id:
        raise NotFoundError("entity not found for tenant")


class InMemoryIdempotencyRepository(IdempotencyRepository):
    """In-memory atomic idempotency claims."""

    def __init__(self):
        self._records: dict[tuple[str, str], IdempotencyRecord] = {}

    async def claim(self, record: IdempotencyRecord) -> IdempotencyRecord:
        key = (record.tenant_id, record.idempotency_key)
        existing = self._records.get(key)
        if existing is None:
            self._records[key] = record
            return record
        if existing.business_content_digest != record.business_content_digest:
            raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
        if existing.status == "failed":
            self._records[key] = record
            return record
        return existing

    async def get(self, tenant_id: str, idempotency_key: str) -> IdempotencyRecord | None:
        return self._records.get((tenant_id, idempotency_key))

    async def update_status(
        self, tenant_id: str, idempotency_key: str, status: str
    ) -> IdempotencyRecord:
        key = (tenant_id, idempotency_key)
        existing = self._records.get(key)
        if existing is None:
            raise NotFoundError("not found")
        updated = existing.model_copy(update={"status": status})
        self._records[key] = updated
        return updated


class InMemoryProductQuestionRepository(ProductQuestionRepository):
    """In-memory ProductQuestionRepository."""

    def __init__(self):
        self._questions: dict[str, ProductQuestion] = {}

    async def save(self, question: ProductQuestion) -> None:
        self._questions[question.question_id] = question

    async def get(self, question_id: str, *, tenant_id: str) -> ProductQuestion:
        question = self._questions.get(question_id)
        if question is None:
            raise NotFoundError("not found")
        _ensure_tenant(question.tenant_id, tenant_id)
        return question

    async def find_by_idempotency(
        self, tenant_id: str, idempotency_key: str
    ) -> ProductQuestion | None:
        for question in self._questions.values():
            if question.tenant_id == tenant_id and question.idempotency_key == idempotency_key:
                return question
        return None


class InMemoryEvidenceRepository(EvidenceRepository):
    """In-memory EvidenceRepository."""

    def __init__(self):
        self._evidence: dict[str, list[EvidenceItem]] = {}

    async def save_evidence(self, run_ref: str, items: list[EvidenceItem]) -> None:
        self._evidence[run_ref] = list(items)

    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> list[EvidenceItem]:
        items = self._evidence.get(run_ref)
        if items is None:
            raise NotFoundError("not found")
        for item in items:
            _ensure_tenant(item.tenant_id, tenant_id)
        return items


class InMemoryAnswerDraftRepository(AnswerDraftRepository):
    """In-memory AnswerDraftRepository."""

    def __init__(self):
        self._drafts: dict[tuple[str, str], AnswerDraft] = {}

    async def save(self, draft: AnswerDraft, *, tenant_id: str) -> None:
        self._drafts[(draft.run_ref.id, tenant_id)] = draft

    async def get_by_id(self, answer_id: str, *, tenant_id: str) -> AnswerDraft:
        for (run_ref, stored_tenant), draft in self._drafts.items():
            if stored_tenant == tenant_id and draft.answer_id == answer_id:
                return draft
        raise NotFoundError("not found")

    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> AnswerDraft | None:
        return self._drafts.get((run_ref, tenant_id))


class InMemoryDispositionRepository(DispositionRepository):
    """In-memory DispositionRepository."""

    def __init__(self):
        self._dispositions: dict[tuple[str, str], HumanDispositionRecord] = {}

    async def save(self, record: HumanDispositionRecord, *, tenant_id: str) -> None:
        self._dispositions[(record.original_answer.answer_id, tenant_id)] = record

    async def get_by_answer(
        self, answer_id: str, *, tenant_id: str
    ) -> HumanDispositionRecord | None:
        return self._dispositions.get((answer_id, tenant_id))


class InMemoryRunTraceRepository(RunTraceRepository):
    """In-memory RunTraceRepository."""

    def __init__(self):
        self._traces: dict[str, PresaleRunTrace] = {}

    async def save(self, trace: PresaleRunTrace) -> None:
        self._traces[trace.run_ref] = trace

    async def get(self, run_ref: str, *, tenant_id: str) -> PresaleRunTrace:
        trace = self._traces.get(run_ref)
        if trace is None:
            raise NotFoundError("not found")
        _ensure_tenant(trace.tenant_id, tenant_id)
        return trace

    async def list_by_tenant(self, *, tenant_id: str) -> list[PresaleRunTrace]:
        return [trace for trace in self._traces.values() if trace.tenant_id == tenant_id]

    async def mark_disposition(self, run_ref: str, *, tenant_id: str, state: str) -> None:
        trace = await self.get(run_ref, tenant_id=tenant_id)
        self._traces[run_ref] = trace.model_copy(
            update={"disposition_state": DispositionState(state)}
        )

    async def mark_archived(self, run_ref: str, *, tenant_id: str) -> None:
        trace = await self.get(run_ref, tenant_id=tenant_id)
        self._traces[run_ref] = trace.model_copy(update={"archived": True})


__all__ = [
    "InMemoryIdempotencyRepository",
    "InMemoryProductQuestionRepository",
    "InMemoryEvidenceRepository",
    "InMemoryAnswerDraftRepository",
    "InMemoryDispositionRepository",
    "InMemoryRunTraceRepository",
]
