"""SQLite adapters for the presale persistence ports.

Each adapter stores its entity as a single JSON column (the Pydantic model
serialized with ``model_dump(mode="json")``) plus tenant/run/answer columns
for lookup, mirroring the B1/B2 SQLite style.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

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
from ..trace import DispositionState, PresaleRunTrace, StageRecord


class SQLitePresaleStore:
    """Shared SQLite connection and schema for all presale adapters."""

    def __init__(self, database: str | Path = "presale.sqlite3"):
        self.database = str(database)
        self.db = sqlite3.connect(self.database)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS presale_questions (
                id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL, content TEXT NOT NULL,
                UNIQUE(tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS presale_idempotency (
                tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                content TEXT NOT NULL,
                PRIMARY KEY(tenant_id, idempotency_key)
            );
            CREATE TABLE IF NOT EXISTS presale_evidence (
                run_ref TEXT NOT NULL, tenant_id TEXT NOT NULL, content TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS presale_answers (
                run_ref TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, content TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS presale_dispositions (
                answer_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, content TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS presale_traces (
                run_ref TEXT PRIMARY KEY, tenant_id TEXT NOT NULL, content TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()


class SQLiteIdempotencyRepository(IdempotencyRepository):
    """SQLite-backed atomic idempotency claims."""

    def __init__(self, store: SQLitePresaleStore, *, claim_barrier=None):
        self._db = store.db
        # Test seam: awaited between this claim's existence check and its INSERT,
        # letting a test land a conflicting row through another connection to
        # drive the IntegrityError recovery deterministically. No-op in production.
        self._claim_barrier = claim_barrier

    async def claim(self, record: IdempotencyRecord) -> IdempotencyRecord:
        row = self._db.execute(
            "SELECT content FROM presale_idempotency WHERE tenant_id = ? AND idempotency_key = ?",
            (record.tenant_id, record.idempotency_key),
        ).fetchone()
        if row is not None:
            existing = IdempotencyRecord.model_validate_json(row["content"])
            if existing.business_content_digest != record.business_content_digest:
                raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
            if existing.status == "failed":
                self._db.execute(
                    (
                        "UPDATE presale_idempotency SET content = ? "
                        "WHERE tenant_id = ? AND idempotency_key = ?"
                    ),
                    (record.model_dump_json(), record.tenant_id, record.idempotency_key),
                )
                self._db.commit()
                return record
            return existing
        if self._claim_barrier is not None:
            await self._claim_barrier()
        try:
            self._db.execute(
                (
                    "INSERT INTO presale_idempotency "
                    "(tenant_id, idempotency_key, content) VALUES (?, ?, ?)"
                ),
                (record.tenant_id, record.idempotency_key, record.model_dump_json()),
            )
            self._db.commit()
        except sqlite3.IntegrityError:
            existing = await self.get(record.tenant_id, record.idempotency_key)
            if existing is None:
                raise
            if existing.business_content_digest != record.business_content_digest:
                raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
            if existing.status == "failed":
                return await self.claim(record)
            return existing
        return record

    async def get(self, tenant_id: str, idempotency_key: str) -> IdempotencyRecord | None:
        row = self._db.execute(
            "SELECT content FROM presale_idempotency WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, idempotency_key),
        ).fetchone()
        return IdempotencyRecord.model_validate_json(row["content"]) if row else None

    async def update_status(
        self, tenant_id: str, idempotency_key: str, status: str
    ) -> IdempotencyRecord:
        existing = await self.get(tenant_id, idempotency_key)
        if existing is None:
            raise NotFoundError("not found")
        updated = existing.model_copy(update={"status": status})
        self._db.execute(
            (
                "UPDATE presale_idempotency SET content = ? "
                "WHERE tenant_id = ? AND idempotency_key = ?"
            ),
            (updated.model_dump_json(), tenant_id, idempotency_key),
        )
        self._db.commit()
        return updated


class SQLiteProductQuestionRepository(ProductQuestionRepository):
    """SQLite-backed ProductQuestionRepository."""

    def __init__(self, store: SQLitePresaleStore):
        self._store = store
        self._db = store.db

    async def save(self, question: ProductQuestion) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO presale_questions (id, tenant_id, idempotency_key, content) "
            "VALUES (?, ?, ?, ?)",
            (
                question.question_id,
                question.tenant_id,
                question.idempotency_key,
                question.model_dump_json(),
            ),
        )
        self._db.commit()

    async def get(self, question_id: str, *, tenant_id: str) -> ProductQuestion:
        row = self._db.execute(
            "SELECT content FROM presale_questions WHERE id = ? AND tenant_id = ?",
            (question_id, tenant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("not found")
        return ProductQuestion.model_validate_json(row["content"])

    async def find_by_idempotency(
        self, tenant_id: str, idempotency_key: str
    ) -> ProductQuestion | None:
        row = self._db.execute(
            "SELECT content FROM presale_questions WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, idempotency_key),
        ).fetchone()
        return ProductQuestion.model_validate_json(row["content"]) if row else None


class SQLiteEvidenceRepository(EvidenceRepository):
    """SQLite-backed EvidenceRepository."""

    def __init__(self, store: SQLitePresaleStore):
        self._db = store.db

    async def save_evidence(self, run_ref: str, items: list[EvidenceItem]) -> None:
        self._db.execute("DELETE FROM presale_evidence WHERE run_ref = ?", (run_ref,))
        for item in items:
            self._db.execute(
                "INSERT INTO presale_evidence (run_ref, tenant_id, content) VALUES (?, ?, ?)",
                (run_ref, item.tenant_id, item.model_dump_json()),
            )
        self._db.commit()

    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> list[EvidenceItem]:
        rows = self._db.execute(
            "SELECT content FROM presale_evidence WHERE run_ref = ? AND tenant_id = ?",
            (run_ref, tenant_id),
        ).fetchall()
        if not rows:
            raise NotFoundError("not found")
        return [EvidenceItem.model_validate_json(row["content"]) for row in rows]


class SQLiteAnswerDraftRepository(AnswerDraftRepository):
    """SQLite-backed AnswerDraftRepository."""

    def __init__(self, store: SQLitePresaleStore):
        self._db = store.db

    async def save(self, draft: AnswerDraft, *, tenant_id: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO presale_answers (run_ref, tenant_id, content) VALUES (?, ?, ?)",
            (draft.run_ref.id, tenant_id, draft.model_dump_json()),
        )
        self._db.commit()

    async def get_by_id(self, answer_id: str, *, tenant_id: str) -> AnswerDraft:
        rows = self._db.execute(
            "SELECT content FROM presale_answers WHERE tenant_id = ?", (tenant_id,)
        ).fetchall()
        for row in rows:
            draft = AnswerDraft.model_validate_json(row["content"])
            if draft.answer_id == answer_id:
                return draft
        raise NotFoundError("not found")

    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> AnswerDraft | None:
        row = self._db.execute(
            "SELECT content FROM presale_answers WHERE run_ref = ? AND tenant_id = ?",
            (run_ref, tenant_id),
        ).fetchone()
        return AnswerDraft.model_validate_json(row["content"]) if row else None


class SQLiteDispositionRepository(DispositionRepository):
    """SQLite-backed DispositionRepository."""

    def __init__(self, store: SQLitePresaleStore):
        self._db = store.db

    async def save(self, record: HumanDispositionRecord, *, tenant_id: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO presale_dispositions (answer_id, tenant_id, content) "
            "VALUES (?, ?, ?)",
            (record.original_answer.answer_id, tenant_id, record.model_dump_json()),
        )
        self._db.commit()

    async def get_by_answer(
        self, answer_id: str, *, tenant_id: str
    ) -> HumanDispositionRecord | None:
        row = self._db.execute(
            "SELECT content FROM presale_dispositions WHERE answer_id = ? AND tenant_id = ?",
            (answer_id, tenant_id),
        ).fetchone()
        return HumanDispositionRecord.model_validate_json(row["content"]) if row else None


class SQLiteRunTraceRepository(RunTraceRepository):
    """SQLite-backed RunTraceRepository."""

    def __init__(self, store: SQLitePresaleStore):
        self._db = store.db

    async def save(self, trace: PresaleRunTrace) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO presale_traces (run_ref, tenant_id, content) VALUES (?, ?, ?)",
            (trace.run_ref, trace.tenant_id, self._serialize(trace)),
        )
        self._db.commit()

    async def get(self, run_ref: str, *, tenant_id: str) -> PresaleRunTrace:
        row = self._db.execute(
            "SELECT content FROM presale_traces WHERE run_ref = ? AND tenant_id = ?",
            (run_ref, tenant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("not found")
        return self._deserialize(row["content"])

    async def list_by_tenant(self, *, tenant_id: str) -> list[PresaleRunTrace]:
        rows = self._db.execute(
            "SELECT content FROM presale_traces WHERE tenant_id = ?", (tenant_id,)
        ).fetchall()
        return [self._deserialize(row["content"]) for row in rows]

    async def mark_disposition(self, run_ref: str, *, tenant_id: str, state: str) -> None:
        trace = await self.get(run_ref, tenant_id=tenant_id)
        updated = trace.model_copy(update={"disposition_state": DispositionState(state)})
        await self.save(updated)

    async def mark_archived(self, run_ref: str, *, tenant_id: str) -> None:
        trace = await self.get(run_ref, tenant_id=tenant_id)
        await self.save(trace.model_copy(update={"archived": True}))

    @staticmethod
    def _serialize(trace: PresaleRunTrace) -> str:
        data = trace.model_dump(mode="json")
        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _deserialize(raw: str) -> PresaleRunTrace:
        data = json.loads(raw)
        data["stages"] = [StageRecord.model_validate(item) for item in data["stages"]]
        return PresaleRunTrace.model_validate(data)


__all__ = [
    "SQLitePresaleStore",
    "SQLiteProductQuestionRepository",
    "SQLiteEvidenceRepository",
    "SQLiteAnswerDraftRepository",
    "SQLiteDispositionRepository",
    "SQLiteRunTraceRepository",
]
