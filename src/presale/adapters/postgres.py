"""PostgreSQL adapters for the presale persistence ports.

Each adapter stores its entity as a JSONB column (the Pydantic model
serialized with ``model_dump(mode="json")``) plus tenant/run/answer columns
for lookup, mirroring the SQLite adapter pattern.

Requires ``asyncpg`` (``uv sync --extra postgres``) and a running PostgreSQL
instance (``docker compose up -d postgres``).
"""

from __future__ import annotations

import json

import asyncpg  # pyright: ignore[reportMissingImports]

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS presale_questions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    content JSONB NOT NULL,
    UNIQUE(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS presale_idempotency (
    tenant_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    content JSONB NOT NULL,
    PRIMARY KEY(tenant_id, idempotency_key)
);
CREATE TABLE IF NOT EXISTS presale_evidence (
    id SERIAL PRIMARY KEY,
    run_ref TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    content JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS presale_answers (
    run_ref TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    content JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS presale_dispositions (
    answer_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    content JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS presale_traces (
    run_ref TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    content JSONB NOT NULL
);
"""


class PostgresPresaleStore:
    """Shared asyncpg connection pool and schema for all presale PostgreSQL adapters."""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self.pool: asyncpg.Pool | None = None
        self._initialized = False

    async def _ensure_init(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
        if not self._initialized:
            async with self.pool.acquire() as conn:
                await conn.execute(_SCHEMA)
            self._initialized = True
        return self.pool

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None


def _json_dumps(obj) -> str:
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(mode="json"), ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False)


def _parse_jsonb(raw) -> dict:
    """Parse JSONB content returned by asyncpg (may be str or dict)."""
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


class PostgresProductQuestionRepository(ProductQuestionRepository):
    def __init__(self, store: PostgresPresaleStore):
        self._store = store

    async def save(self, question: ProductQuestion) -> None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO presale_questions (id, tenant_id, idempotency_key, content) "
                "VALUES ($1, $2, $3, $4::jsonb) "
                "ON CONFLICT (tenant_id, idempotency_key) DO UPDATE SET content = EXCLUDED.content",
                question.question_id,
                question.tenant_id,
                question.idempotency_key,
                _json_dumps(question),
            )

    async def get(self, question_id: str, *, tenant_id: str) -> ProductQuestion:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM presale_questions WHERE id = $1 AND tenant_id = $2",
                question_id,
                tenant_id,
            )
        if row is None:
            raise NotFoundError("not found")
        return ProductQuestion.model_validate(_parse_jsonb(row["content"]))

    async def find_by_idempotency(
        self, tenant_id: str, idempotency_key: str
    ) -> ProductQuestion | None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                (
                    "SELECT content FROM presale_questions"
                    " WHERE tenant_id = $1 AND idempotency_key = $2"
                ),
                tenant_id,
                idempotency_key,
            )
        return ProductQuestion.model_validate(_parse_jsonb(row["content"])) if row else None


class PostgresEvidenceRepository(EvidenceRepository):
    def __init__(self, store: PostgresPresaleStore):
        self._store = store

    async def save_evidence(self, run_ref: str, items: list[EvidenceItem]) -> None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM presale_evidence WHERE run_ref = $1", run_ref)
            for item in items:
                await conn.execute(
                    (
                        "INSERT INTO presale_evidence"
                        " (run_ref, tenant_id, content) VALUES ($1, $2, $3::jsonb)"
                    ),
                    run_ref,
                    item.tenant_id,
                    _json_dumps(item),
                )

    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> list[EvidenceItem]:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT content FROM presale_evidence WHERE run_ref = $1 AND tenant_id = $2",
                run_ref,
                tenant_id,
            )
        if not rows:
            raise NotFoundError("not found")
        return [EvidenceItem.model_validate(_parse_jsonb(row["content"])) for row in rows]


class PostgresAnswerDraftRepository(AnswerDraftRepository):
    def __init__(self, store: PostgresPresaleStore):
        self._store = store

    async def save(self, draft: AnswerDraft, *, tenant_id: str) -> None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            await conn.execute(
                (
                    "INSERT INTO presale_answers"
                    " (run_ref, tenant_id, content) VALUES ($1, $2, $3::jsonb)"
                    " ON CONFLICT (run_ref) DO UPDATE SET content = EXCLUDED.content"
                ),
                draft.run_ref.id,
                tenant_id,
                _json_dumps(draft),
            )

    async def get_by_id(self, answer_id: str, *, tenant_id: str) -> AnswerDraft:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT content FROM presale_answers WHERE tenant_id = $1", tenant_id
            )
        for row in rows:
            draft = AnswerDraft.model_validate(_parse_jsonb(row["content"]))
            if draft.answer_id == answer_id:
                return draft
        raise NotFoundError("not found")

    async def get_by_run(self, run_ref: str, *, tenant_id: str) -> AnswerDraft | None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM presale_answers WHERE run_ref = $1 AND tenant_id = $2",
                run_ref,
                tenant_id,
            )
        return AnswerDraft.model_validate(_parse_jsonb(row["content"])) if row else None


class PostgresDispositionRepository(DispositionRepository):
    def __init__(self, store: PostgresPresaleStore):
        self._store = store

    async def save(self, record: HumanDispositionRecord, *, tenant_id: str) -> None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO presale_dispositions (answer_id, tenant_id, content) "
                "VALUES ($1, $2, $3::jsonb) "
                "ON CONFLICT (answer_id) DO UPDATE SET content = EXCLUDED.content",
                record.original_answer.answer_id,
                tenant_id,
                _json_dumps(record),
            )

    async def get_by_answer(
        self, answer_id: str, *, tenant_id: str
    ) -> HumanDispositionRecord | None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM presale_dispositions WHERE answer_id = $1 AND tenant_id = $2",
                answer_id,
                tenant_id,
            )
        return HumanDispositionRecord.model_validate(_parse_jsonb(row["content"])) if row else None


class PostgresIdempotencyRepository(IdempotencyRepository):
    def __init__(self, store: PostgresPresaleStore, *, claim_barrier=None):
        self._store = store
        self._claim_barrier = claim_barrier

    async def claim(self, record: IdempotencyRecord) -> IdempotencyRecord:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                (
                    "SELECT content FROM presale_idempotency"
                    " WHERE tenant_id = $1 AND idempotency_key = $2"
                ),
                record.tenant_id,
                record.idempotency_key,
            )
            if row is not None:
                existing = IdempotencyRecord.model_validate(_parse_jsonb(row["content"]))
                if existing.business_content_digest != record.business_content_digest:
                    raise IdempotencyConflictError("IDEMPOTENCY_CONFLICT")
                if existing.status == "failed":
                    await conn.execute(
                        "UPDATE presale_idempotency SET content = $1::jsonb "
                        "WHERE tenant_id = $2 AND idempotency_key = $3",
                        _json_dumps(record),
                        record.tenant_id,
                        record.idempotency_key,
                    )
                    return record
                return existing

            if self._claim_barrier is not None:
                await self._claim_barrier()

            try:
                await conn.execute(
                    "INSERT INTO presale_idempotency (tenant_id, idempotency_key, content) "
                    "VALUES ($1, $2, $3::jsonb)",
                    record.tenant_id,
                    record.idempotency_key,
                    _json_dumps(record),
                )
            except asyncpg.UniqueViolationError:
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
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                (
                    "SELECT content FROM presale_idempotency"
                    " WHERE tenant_id = $1 AND idempotency_key = $2"
                ),
                tenant_id,
                idempotency_key,
            )
        return IdempotencyRecord.model_validate(_parse_jsonb(row["content"])) if row else None

    async def update_status(
        self, tenant_id: str, idempotency_key: str, status: str
    ) -> IdempotencyRecord:
        existing = await self.get(tenant_id, idempotency_key)
        if existing is None:
            raise NotFoundError("not found")
        updated = existing.model_copy(update={"status": status})
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE presale_idempotency SET content = $1::jsonb "
                "WHERE tenant_id = $2 AND idempotency_key = $3",
                _json_dumps(updated),
                tenant_id,
                idempotency_key,
            )
        return updated


class PostgresRunTraceRepository(RunTraceRepository):
    def __init__(self, store: PostgresPresaleStore):
        self._store = store

    async def save(self, trace: PresaleRunTrace) -> None:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            await conn.execute(
                (
                    "INSERT INTO presale_traces"
                    " (run_ref, tenant_id, content) VALUES ($1, $2, $3::jsonb)"
                    " ON CONFLICT (run_ref) DO UPDATE SET content = EXCLUDED.content"
                ),
                trace.run_ref,
                trace.tenant_id,
                _json_dumps(trace),
            )

    async def get(self, run_ref: str, *, tenant_id: str) -> PresaleRunTrace:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM presale_traces WHERE run_ref = $1 AND tenant_id = $2",
                run_ref,
                tenant_id,
            )
        if row is None:
            raise NotFoundError("not found")
        return self._deserialize(row["content"])

    async def list_by_tenant(self, *, tenant_id: str) -> list[PresaleRunTrace]:
        pool = await self._store._ensure_init()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT content FROM presale_traces WHERE tenant_id = $1", tenant_id
            )
        return [self._deserialize(row["content"]) for row in rows]

    async def mark_disposition(self, run_ref: str, *, tenant_id: str, state: str) -> None:
        trace = await self.get(run_ref, tenant_id=tenant_id)
        updated = trace.model_copy(update={"disposition_state": DispositionState(state)})
        await self.save(updated)

    async def mark_archived(self, run_ref: str, *, tenant_id: str) -> None:
        trace = await self.get(run_ref, tenant_id=tenant_id)
        await self.save(trace.model_copy(update={"archived": True}))

    @staticmethod
    def _deserialize(raw) -> PresaleRunTrace:
        data = raw if isinstance(raw, dict) else json.loads(raw)
        data["stages"] = [StageRecord.model_validate(item) for item in data.get("stages", [])]
        return PresaleRunTrace.model_validate(data)


__all__ = [
    "PostgresPresaleStore",
    "PostgresProductQuestionRepository",
    "PostgresEvidenceRepository",
    "PostgresAnswerDraftRepository",
    "PostgresDispositionRepository",
    "PostgresIdempotencyRepository",
    "PostgresRunTraceRepository",
]
