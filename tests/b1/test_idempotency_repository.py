from datetime import datetime, timezone

import pytest

from presale.adapters.in_memory import InMemoryIdempotencyRepository
from presale.adapters.sqlite import SQLiteIdempotencyRepository, SQLitePresaleStore
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


async def barrier_store(store, injected):
    """Return a barrier that inserts `injected` through a second connection."""

    async def _barrier():
        s2 = SQLitePresaleStore(store.database)
        try:
            await SQLiteIdempotencyRepository(s2).claim(injected)
        finally:
            s2.close()

    return _barrier


@pytest.mark.asyncio
async def test_sqlite_claim_integrity_error_recovery(tmp_path):
    # The claim_barrier seam lets us deterministically land a row between the
    # original claim's SELECT and INSERT, driving the IntegrityError rescue.
    store = SQLitePresaleStore(tmp_path / "race.sqlite3")
    injected = record(run_ref="run_injected")
    ours = record(run_ref="run_ours")  # same digest

    repo = SQLiteIdempotencyRepository(store, claim_barrier=await barrier_store(store, injected))
    claimed = await repo.claim(ours)

    assert claimed.run_ref == injected.run_ref  # recovery returned the existing
    store.close()


@pytest.mark.asyncio
async def test_sqlite_claim_integrity_error_conflict(tmp_path):
    store = SQLitePresaleStore(tmp_path / "race2.sqlite3")
    injected = record(run_ref="run_injected", digest="sha256:" + "b" * 64)
    ours = record(run_ref="run_ours", digest="sha256:" + "a" * 64)

    repo = SQLiteIdempotencyRepository(store, claim_barrier=await barrier_store(store, injected))
    with pytest.raises(IdempotencyConflictError, match="IDEMPOTENCY_CONFLICT"):
        await repo.claim(ours)
    store.close()


@pytest.mark.asyncio
async def test_sqlite_claim_integrity_error_failed_recurs_to_replace(tmp_path):
    store = SQLitePresaleStore(tmp_path / "race3.sqlite3")

    injected = record(run_ref="run_injected").model_copy(update={"status": "failed"})
    ours = record(run_ref="run_ours")

    repo = SQLiteIdempotencyRepository(store, claim_barrier=await barrier_store(store, injected))
    claimed = await repo.claim(ours)

    assert claimed.run_ref == ours.run_ref  # recursive recovery replaced the failed row
    store.close()
