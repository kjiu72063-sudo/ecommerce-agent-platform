"""Presale persistence adapters.

Each port in :mod:`presale.ports` has an in-memory and a SQLite adapter,
which together prove the seam is real: behaviour visible through the port
interface is identical across backends.
"""

from __future__ import annotations

from .in_memory import (
    InMemoryAnswerDraftRepository,
    InMemoryDispositionRepository,
    InMemoryEvidenceRepository,
    InMemoryIdempotencyRepository,
    InMemoryProductQuestionRepository,
    InMemoryRunTraceRepository,
)

__all__ = [
    "InMemoryAnswerDraftRepository",
    "InMemoryIdempotencyRepository",
    "InMemoryDispositionRepository",
    "InMemoryEvidenceRepository",
    "InMemoryProductQuestionRepository",
    "InMemoryRunTraceRepository",
]
