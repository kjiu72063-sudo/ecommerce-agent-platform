"""Reusable presale maintenance operations (retention archive).

Exposes a single backend-aware entrypoint so the CLI and the HTTP
maintenance endpoint share the same scheduling surface instead of each
duplicating store wiring.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .adapters.sqlite import SQLitePresaleStore, SQLiteRunTraceRepository
from .retention import RetentionService
from .trace import TraceError

__all__ = ["archive_expired_sqlite"]


async def archive_expired_sqlite(
    *, database: str, tenant_id: str, now: datetime | None = None
) -> list[str]:
    """Mark expired, completed traces archived in a SQLite store for a tenant."""
    if not tenant_id:
        raise TraceError("TENANT_ID_REQUIRED")
    store = SQLitePresaleStore(database)
    try:
        service = RetentionService(SQLiteRunTraceRepository(store))
        return await service.archive_expired(
            tenant_id=tenant_id, now=now or datetime.now(timezone.utc)
        )
    finally:
        store.close()
