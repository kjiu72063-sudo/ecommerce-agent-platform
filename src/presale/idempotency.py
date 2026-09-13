"""Durable idempotency records for presale submissions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IdempotencyConflictError(ValueError):
    """A tenant/key pair was reused for different business content."""


class IdempotencyRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=512)
    business_content_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    run_ref: str = Field(min_length=1, max_length=256)
    created_at: datetime
    status: Literal["in_progress", "succeeded", "failed"] = "in_progress"


__all__ = ["IdempotencyConflictError", "IdempotencyRecord"]
