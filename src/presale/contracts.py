"""Minimal V1 presale business contracts.

These models define the boundary between the presale application flow and
future knowledge retrieval/context/answer components. They intentionally do
not implement those components.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_platform_contracts.models import ActorRef, ObjectRef, ResourceKind


class ProductQuestion(BaseModel):
    """A single internal, single-product presale question."""

    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=256)
    tenant_id: str = Field(min_length=1, max_length=128)
    submitted_by: ActorRef
    product_id: str = Field(min_length=1, max_length=256)
    question_text: str = Field(min_length=1, max_length=4096)
    requested_at: datetime
    idempotency_key: str = Field(min_length=8, max_length=512)

    @field_validator("question_text")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question_text must not be blank")
        return value

    @model_validator(mode="after")
    def operator_must_belong_to_tenant(self) -> ProductQuestion:
        if self.submitted_by.tenant_id and self.submitted_by.tenant_id != self.tenant_id:
            raise ValueError("submitted_by must belong to tenant_id")
        return self


class EvidenceRef(BaseModel):
    """Field/fragment-level reference to a versioned product knowledge source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=256)
    source_version: str = Field(min_length=1, max_length=128)
    locator: str = Field(min_length=1, max_length=512)
    content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class AnswerDraft(BaseModel):
    """A traceable answer suggestion for internal review."""

    model_config = ConfigDict(extra="forbid")

    answer_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    run_ref: ObjectRef
    answer_text: str = Field(min_length=1, max_length=16384)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence_signal: Literal["supported", "uncertain", "conflicting", "unavailable"]
    need_human: bool
    reason_codes: list[str] = Field(default_factory=list)
    generated_at: datetime

    @field_validator("answer_text")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("answer_text must not be blank")
        return value

    @model_validator(mode="after")
    def validate_evidence_and_human_review(self) -> AnswerDraft:
        if self.run_ref.kind != ResourceKind.AGENT_RUN:
            raise ValueError("run_ref must reference AgentRun")
        if not self.evidence_refs and not self.need_human:
            raise ValueError("answers without evidence must require human review")
        if self.need_human and not self.reason_codes:
            raise ValueError("human review requires at least one reason code")
        return self
