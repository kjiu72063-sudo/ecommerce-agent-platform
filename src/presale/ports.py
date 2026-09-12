"""V1 presale persistence ports and data objects.

These are the **ports** the business layer depends on, replacing the hidden
in-memory dicts. The business objects themselves are existing Pydantic models
(ProductQuestion, EvidenceItem, AnswerDraft, HumanDispositionRecord,
PresaleRunTrace); the ports declare how they are persisted.

Rules every adapter must honour:
- Every operation is tenant-scoped: an entity's ``tenant_id`` must match the
  ``tenant_id`` passed to the operation, otherwise the adapter must fail.
- Lookups that find nothing must raise :class:`NotFoundError` (or return None
  only where the interface documents it); adapters must not silently return
  fabricated data.
- These are async ports, matching the B2 runtime direction. The presale
  application seam will be converted to async in the adapter/wiring step.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .answer import AnswerDraft
    from .contracts import ProductQuestion
    from .disposition import HumanDispositionRecord
    from .idempotency import IdempotencyRecord
    from .knowledge import EvidenceItem
    from .trace import PresaleRunTrace


class NotFoundError(LookupError):
    """A requested entity does not exist for the given tenant."""


class ProductQuestionRepository(ABC):
    """Persist ProductQuestion requests keyed by id and idempotency key."""

    @abstractmethod
    async def save(self, question: ProductQuestion) -> None:
        """Persist the question. Adapter must reject cross-tenant writes."""

    @abstractmethod
    async def get(self, question_id: str, *, tenant_id: str) -> ProductQuestion:
        """Return a question by id within a tenant. Raise NotFoundError if absent."""

    @abstractmethod
    async def find_by_idempotency(
        self, tenant_id: str, idempotency_key: str
    ) -> ProductQuestion | None:
        """Return the question for a tenant+key, or None when absent."""


class IdempotencyRepository(ABC):
    """Atomically claim a tenant-scoped idempotency key."""

    @abstractmethod
    async def claim(self, record: IdempotencyRecord) -> IdempotencyRecord:
        """Return the existing record or persist the new claim atomically."""

    @abstractmethod
    async def get(self, tenant_id: str, idempotency_key: str) -> IdempotencyRecord | None:
        """Return a tenant/key record, or None when no claim exists."""

    @abstractmethod
    async def update_status(
        self, tenant_id: str, idempotency_key: str, status: str
    ) -> IdempotencyRecord:
        """Transition a claim to succeeded or failed; raise NotFoundError if absent."""


class EvidenceRepository(ABC):
    """Persist EvidenceItems selected during a run."""

    @abstractmethod
    async def save_evidence(self, run_ref: str, items: list[EvidenceItem]) -> None:
        """Persist evidence for a run. Adapter must reject cross-tenant writes."""

    @abstractmethod
    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> list[EvidenceItem]:
        """Return evidence for a run within a tenant. Raise NotFoundError if absent."""


class AnswerDraftRepository(ABC):
    """Persist generated AnswerDrafts."""

    @abstractmethod
    async def save(self, draft: AnswerDraft, *, tenant_id: str) -> None:
        """Persist a draft within a tenant. Adapter must reject cross-tenant writes."""

    @abstractmethod
    async def get_by_id(self, answer_id: str, *, tenant_id: str) -> AnswerDraft:
        """Return a draft by answer id within a tenant; raise NotFoundError if absent."""

    @abstractmethod
    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> AnswerDraft | None:
        """Return the draft for a run within a tenant, or None when absent."""


class DispositionRepository(ABC):
    """Persist human dispositions of AnswerDrafts."""

    @abstractmethod
    async def save(self, record: HumanDispositionRecord, *, tenant_id: str) -> None:
        """Persist a disposition record within a tenant. Adapter must reject cross-tenant writes."""

    @abstractmethod
    async def get_by_answer(
        self, answer_id: str, *, tenant_id: str
    ) -> HumanDispositionRecord | None:
        """Return the disposition for an answer within a tenant, or None when absent."""


class RunTraceRepository(ABC):
    """Persist run traces and their lifecycle markers."""

    @abstractmethod
    async def save(self, trace: PresaleRunTrace) -> None:
        """Persist a trace. Adapter must reject cross-tenant writes."""

    @abstractmethod
    async def get(self, run_ref: str, *, tenant_id: str) -> PresaleRunTrace:
        """Return a trace within a tenant. Raise NotFoundError if absent."""

    @abstractmethod
    async def list_by_tenant(self, *, tenant_id: str) -> list[PresaleRunTrace]:
        """List all traces for a tenant for retention evaluation."""

    @abstractmethod
    async def mark_disposition(self, run_ref: str, *, tenant_id: str, state: str) -> None:
        """Record the terminal disposition state (complete/escalated)."""

    @abstractmethod
    async def mark_archived(self, run_ref: str, *, tenant_id: str) -> None:
        """Mark a trace archived while keeping its history intact."""
