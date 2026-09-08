"""V1 AnswerDraft disposition boundary."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .contracts import AnswerDraft


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
    technical_status: str = "unchanged"
    sent_to_consumer: bool = False


class AnswerDispositionService:
    """Apply one terminal internal disposition to each registered draft."""

    def __init__(self):
        self._drafts: dict[str, AnswerDraft] = {}
        self._records: dict[str, HumanDispositionRecord] = {}
        self._technical_status: dict[str, str] = {}

    def register(self, answer: AnswerDraft, *, technical_status: str = "unchanged") -> None:
        if answer.answer_id in self._drafts:
            raise DispositionError("DRAFT_ALREADY_REGISTERED")
        self._drafts[answer.answer_id] = deepcopy(answer)
        if technical_status != "unchanged":
            self._technical_status[answer.answer_id] = technical_status

    def get_original(self, answer_id: str) -> AnswerDraft:
        answer = self._drafts.get(answer_id)
        if answer is None:
            raise DispositionError("DRAFT_NOT_FOUND")
        return deepcopy(answer)

    def accept(self, answer_id: str, *, actor_id: str, reason: str) -> HumanDispositionRecord:
        return self._record(answer_id, DispositionType.ACCEPTED, actor_id=actor_id, reason=reason)

    def edit(
        self,
        answer_id: str,
        *,
        edited_text: str,
        actor_id: str,
        reason: str,
    ) -> HumanDispositionRecord:
        if not edited_text.strip():
            raise DispositionError("EMPTY_EDIT")
        original = self._get_available(answer_id)
        edited = original.model_copy(
            update={
                "answer_id": f"{original.answer_id}:edited",
                "answer_text": edited_text,
                "generated_at": datetime.now(timezone.utc),
            }
        )
        return self._record(
            answer_id,
            DispositionType.EDITED,
            actor_id=actor_id,
            reason=reason,
            edited_answer=edited,
        )

    def escalate(self, answer_id: str, *, actor_id: str, reason: str) -> HumanDispositionRecord:
        return self._record(answer_id, DispositionType.ESCALATED, actor_id=actor_id, reason=reason)

    def discard(self, answer_id: str, *, actor_id: str, reason: str) -> HumanDispositionRecord:
        return self._record(answer_id, DispositionType.DISCARDED, actor_id=actor_id, reason=reason)

    def _get_available(self, answer_id: str) -> AnswerDraft:
        if answer_id not in self._drafts:
            raise DispositionError("DRAFT_NOT_FOUND")
        if answer_id in self._records:
            raise DispositionError("ALREADY_DISPOSED")
        return self.get_original(answer_id)

    def _record(
        self,
        answer_id: str,
        disposition: DispositionType,
        *,
        actor_id: str,
        reason: str,
        edited_answer: AnswerDraft | None = None,
    ) -> HumanDispositionRecord:
        original = self._get_available(answer_id)
        if not reason.strip():
            raise DispositionError("DISPOSITION_REASON_REQUIRED")
        record = HumanDispositionRecord(
            disposition=disposition,
            original_answer=original,
            edited_answer=edited_answer,
            actor_id=actor_id,
            reason=reason,
            occurred_at=datetime.now(timezone.utc),
            technical_status=self._technical_status.get(answer_id, "unchanged"),
        )
        self._records[answer_id] = record
        return record
