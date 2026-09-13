"""V1 presale maintenance FastAPI routes.

Retention archive is a maintenance operation that an external scheduler
(cron/APScheduler/k8s CronJob) triggers over HTTP instead of running inline
in a request path. The endpoint delegates to the shared backend-aware helper
so it stays consistent with the CLI.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from presale.maintenance import archive_expired_sqlite
from presale.trace import TraceError

app = FastAPI(
    title="Presale 维护端点",
    description="供外部调度器触发的后台维护操作；当前为 30 天保留归档。",
    version="0.1.0",
)


@app.get("/api/v1/presale/maintenance/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/api/v1/presale/maintenance/retention/archive")
async def archive_expired(
    tenant_id: str = Query(..., min_length=1, description="要归档的租户 id"),
    database: str = Query("presale.sqlite3", description="SQLite 数据库路径"),
) -> dict:
    try:
        archived = await archive_expired_sqlite(database=database, tenant_id=tenant_id)
    except TraceError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"tenant_id": tenant_id, "archived": archived}
