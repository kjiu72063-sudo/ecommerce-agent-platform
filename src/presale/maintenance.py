"""Reusable presale maintenance operations (retention archive).

Exposes a single backend-aware entrypoint so the CLI and the HTTP
maintenance endpoint share the same scheduling surface instead of each
duplicating store wiring. The blocking work lives in a sync function so an
async caller can offload it with ``asyncio.to_thread`` and a sync route can
run it in a thread pool without stalling an event loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .adapters.sqlite import SQLitePresaleStore, SQLiteRunTraceRepository
from .retention import RetentionService
from .trace import TraceError

__all__ = ["archive_expired_sqlite", "archive_expired_sqlite_blocking"]


def archive_expired_sqlite_blocking(
    *, database: str, tenant_id: str, now: datetime | None = None
) -> list[str]:
    """Mark expired, completed traces archived in a SQLite store for a tenant.

    Blocking form: drives the async retention service under a fresh event loop
    in the calling thread. Call it from a worker thread / sync route so the
    synchronous sqlite I/O never stalls a shared event loop.
    """
    if not tenant_id:
        raise TraceError("TENANT_ID_REQUIRED")
    store = SQLitePresaleStore(database)
    try:
        service = RetentionService(SQLiteRunTraceRepository(store))
        return asyncio.run(
            service.archive_expired(tenant_id=tenant_id, now=now or datetime.now(timezone.utc))
        )
    finally:
        store.close()


async def archive_expired_sqlite(
    *, database: str, tenant_id: str, now: datetime | None = None
) -> list[str]:
    """Async facade that offloads the blocking sqlite work to a worker thread."""
    return await asyncio.to_thread(
        archive_expired_sqlite_blocking,
        database=database,
        tenant_id=tenant_id,
        now=now,
    )
