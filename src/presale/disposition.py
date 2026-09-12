"""V1 AnswerDraft disposition boundary."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .contracts import AnswerDraft
from .ports import AnswerDraftRepository, DispositionRepository


class DispositionError(ValueError):
    """An AnswerDraft disposition could not be applied."""


class DispositionType(StrEnum):
    ACCEPTED = "accepted"
    EDITED = "edited"
    ESCALATED = "escalated"
    DISCARDED = "discarded"


class HumanDispositionRecord(BaseModel):
    """Auditable result of one internal AnswerDraft disposition."""

    model_config = ConfigDict(frozen=True)

    disposition: DispositionType
    original_answer: AnswerDraft
    edited_answer: AnswerDraft | None = None
    actor_id: str = Field(min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=2048)
    occurred_at: datetime
    tenant_id: str = Field(min_length=1, max_length=128)
    technical_status: str = "unchanged"
    sent_to_consumer: bool = False


class AnswerDispositionService:
    """Apply terminal dispositions, persisting records through a repository.

    Draft identity, "already disposed" detection and edited versions live in
    memory; the terminal HumanDispositionRecord is written to the injected
    DispositionRepository. Methods are async because the repository is async.
    """

    def __init__(
        self,
        disposition_repo: DispositionRepository | None = None,
        answer_repo: AnswerDraftRepository | None = None,
    ):
        if disposition_repo is None or answer_repo is None:
            from .adapters.in_memory import (
                InMemoryAnswerDraftRepository,
                InMemoryDispositionRepository,
            )

            disposition_repo = disposition_repo or InMemoryDispositionRepository()
            answer_repo = answer_repo or InMemoryAnswerDraftRepository()
        self._repo = disposition_repo
        self._answer_repo = answer_repo
        self._drafts: dict[str, AnswerDraft] = {}
        self._records: dict[str, HumanDispositionRecord] = {}
        self._technical_status: dict[str, str] = {}

    def register(self, answer: AnswerDraft, *, technical_status: str = "unchanged") -> None:
        if answer.answer_id in self._drafts:
            return
        self._drafts[answer.answer_id] = deepcopy(answer)
        if technical_status != "unchanged":
            self._technical_status[answer.answer_id] = technical_status

    def get_original(self, answer_id: str) -> AnswerDraft:
        answer = self._drafts.get(answer_id)
        if answer is None:
            raise DispositionError("DRAFT_NOT_FOUND")
        return deepcopy(answer)

    async def accept(
        self, answer_id: str, *, actor_id: str, reason: str, tenant_id: str
    ) -> HumanDispositionRecord:
        return await self._record(
            answer_id,
            DispositionType.ACCEPTED,
            actor_id=actor_id,
            reason=reason,
            tenant_id=tenant_id,
        )

    async def edit(
        self,
        answer_id: str,
        *,
        edited_text: str,
        actor_id: str,
        reason: str,
        tenant_id: str,
    ) -> HumanDispositionRecord:
        if not edited_text.strip():
            raise DispositionError("EMPTY_EDIT")
        original = await self._get_available(answer_id, tenant_id=tenant_id)
        edited = original.model_copy(
            update={
                "answer_id": f"{original.answer_id}:edited",
                "answer_text": edited_text,
                "generated_at": datetime.now(timezone.utc),
            }
        )
        return await self._record(
            answer_id,
            DispositionType.EDITED,
            actor_id=actor_id,
            reason=reason,
            tenant_id=tenant_id,
            edited_answer=edited,
        )

    async def escalate(
        self, answer_id: str, *, actor_id: str, reason: str, tenant_id: str
    ) -> HumanDispositionRecord:
        return await self._record(
            answer_id,
            DispositionType.ESCALATED,
            actor_id=actor_id,
            reason=reason,
            tenant_id=tenant_id,
        )

    async def discard(
        self, answer_id: str, *, actor_id: str, reason: str, tenant_id: str
    ) -> HumanDispositionRecord:
        return await self._record(
            answer_id,
            DispositionType.DISCARDED,
            actor_id=actor_id,
            reason=reason,
            tenant_id=tenant_id,
        )

    async def _get_available(self, answer_id: str, *, tenant_id: str) -> AnswerDraft:
        if answer_id in self._records:
            persisted = await self._repo.get_by_answer(answer_id, tenant_id=tenant_id)
            if persisted is not None:
                raise DispositionError("ALREADY_DISPOSED")
            raise DispositionError("ALREADY_DISPOSED")
        answer = self._drafts.get(answer_id)
        if answer is None:
            try:
                answer = await self._answer_repo.get_by_id(answer_id, tenant_id=tenant_id)
            except LookupError as exc:
                raise DispositionError("DRAFT_NOT_FOUND") from exc
            self._drafts[answer_id] = deepcopy(answer)
        return deepcopy(answer)

    async def _record(
        self,
        answer_id: str,
        disposition: DispositionType,
        *,
        actor_id: str,
        reason: str,
        tenant_id: str,
        edited_answer: AnswerDraft | None = None,
    ) -> HumanDispositionRecord:
        original = await self._get_available(answer_id, tenant_id=tenant_id)
        if not reason.strip():
            raise DispositionError("DISPOSITION_REASON_REQUIRED")
        record = HumanDispositionRecord(
            disposition=disposition,
            original_answer=original,
            edited_answer=edited_answer,
            actor_id=actor_id,
            reason=reason,
            occurred_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            technical_status=self._technical_status.get(answer_id, "unchanged"),
        )
        await self._repo.save(record, tenant_id=tenant_id)
        self._records[answer_id] = record
        return record
