from datetime import datetime, timezone

import pytest

from presale.adapters.sqlite import SQLitePresaleStore
from presale.adapters.sqlite import SQLiteIdempotencyRepository
from presale.adapters.in_memory import InMemoryIdempotencyRepository
from presale.idempotency import IdempotencyConflictError, IdempotencyRecord


def record(digest="sha256:" + "a" * 64, run_ref="run_01111111-1111-7111-8111-111111111111"):
    return IdempotencyRecord(
        tenant_id="tenant-demo",
        idempotency_key="idempotency-key-001",
        business_content_digest=digest,
        run_ref=run_ref,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
async def test_claim_is_atomic_and_detects_conflicts(backend, tmp_path):
    store = SQLitePresaleStore(tmp_path / "idempotency.sqlite3") if backend == "sqlite" else None
    repo = SQLiteIdempotencyRepository(store) if store else InMemoryIdempotencyRepository()

    first = await repo.claim(record())
    same = await repo.claim(record(run_ref="run_02222222-2222-7222-8222-222222222222"))

    assert same.run_ref == first.run_ref
    with pytest.raises(IdempotencyConflictError, match="IDEMPOTENCY_CONFLICT"):
        await repo.claim(record(digest="sha256:" + "b" * 64))
    if store:
        store.close()


@pytest.mark.asyncio
async def test_sqlite_claim_survives_new_repository_instance(tmp_path):
    store = SQLitePresaleStore(tmp_path / "idempotency.sqlite3")
    first = SQLiteIdempotencyRepository(store)
    claimed = await first.claim(record())

    restarted = SQLiteIdempotencyRepository(store)
    found = await restarted.get("tenant-demo", "idempotency-key-001")

    assert found is not None
    assert found.run_ref == claimed.run_ref
    store.close()
