"""Maintenance (retention archive) HTTP endpoint tests."""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from presale.adapters.sqlite import SQLitePresaleStore, SQLiteRunTraceRepository
from presale.api.main import app
from presale.contracts import ProductQuestion
from presale.trace import PresaleRunTracer

RUN_REF = "run_01111111-1111-7111-8111-111111111111"


def question(*, age_days=0):
    return ProductQuestion(
        question_id="question-retention",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        idempotency_key="retention-key-001",
    )


def seed(db_path):
    async def _seed():
        repo = SQLiteRunTraceRepository(SQLitePresaleStore(db_path))
        tracer = PresaleRunTracer(trace_repo=repo)
        await tracer.start(
            question=question(age_days=40),
            task_id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
            agent_run_id=RUN_REF,
            configuration_refs={},
        )
        await tracer.mark_disposition_complete(RUN_REF, tenant_id="tenant-demo")

    asyncio.run(_seed())


def test_health():
    resp = TestClient(app).get("/api/v1/presale/maintenance/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_archive_expired_marks_old_complete_trace(tmp_path, monkeypatch):
    db_path = tmp_path / "retention.sqlite3"
    seed(str(db_path))
    monkeypatch.setenv("PRESALE_DB_DIR", str(tmp_path))
    client = TestClient(app)

    resp = client.post(
        "/api/v1/presale/maintenance/retention/archive",
        params={"tenant_id": "tenant-demo", "database": str(db_path)},
    )

    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "tenant-demo"
    assert RUN_REF in resp.json()["archived"]


def test_archive_requires_tenant_id(tmp_path):
    client = TestClient(app)

    resp = client.post(
        "/api/v1/presale/maintenance/retention/archive",
        params={"database": str(tmp_path / "x.sqlite3")},
    )

    assert resp.status_code == 422  # missing required tenant_id query is rejected


def test_archive_rejects_database_outside_allowed_dir(tmp_path):
    # PRESALE_DB_DIR is unset -> default is cwd; tmp_path is outside it.
    client = TestClient(app)

    resp = client.post(
        "/api/v1/presale/maintenance/retention/archive",
        params={"tenant_id": "tenant-demo", "database": str(tmp_path / "x.sqlite3")},
    )

    assert resp.status_code == 400
    assert "PRESALE_DB_DIR" in resp.json()["detail"]
