"""V1 presale maintenance FastAPI routes.

Retention archive is a maintenance operation that an external scheduler
(cron/APScheduler/k8s CronJob) triggers over HTTP instead of running inline
in a request path. Routes are sync ``def`` so FastAPI runs them in a thread
pool: the archive drives synchronous sqlite I/O and must not stall the event
loop. The database path is restricted to a configured root directory so an
unauthenticated caller cannot touch arbitrary files.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from presale.maintenance import archive_expired_sqlite_blocking
from presale.trace import TraceError

app = FastAPI(
    title="Presale 维护端点",
    description="供外部调度器触发的后台维护操作；当前为 30 天保留归档。",
    version="0.1.0",
)


def _allowed_database(database: str) -> str:
    """Resolve a database path and require it be under the configured root."""
    if not database:
        raise HTTPException(status_code=400, detail="database path required")
    root = Path(os.environ.get("PRESALE_DB_DIR", ".")).resolve()
    target = Path(database).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"database must reside under PRESALE_DB_DIR ({root})",
        )
    return str(target)


@app.get("/api/v1/presale/maintenance/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/api/v1/presale/maintenance/retention/archive")
def archive_expired(
    tenant_id: str = Query(..., min_length=1, description="要归档的租户 id"),
    database: str = Query("presale.sqlite3", min_length=1, description="SQLite 数据库路径"),
) -> dict:
    db = _allowed_database(database)
    try:
        archived = archive_expired_sqlite_blocking(database=db, tenant_id=tenant_id)
    except (TraceError, sqlite3.Error, ValueError) as exc:
        # ValueError covers corrupt-row JSON/pydantic deserialization errors so a
        # malformed database surfaces as a controlled 4xx, not a 500 with driver
        # internals leaked to an external scheduler.
        raise HTTPException(status_code=400, detail=str(exc))
    return {"tenant_id": tenant_id, "archived": archived}
