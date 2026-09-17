"""Presale QA service entry tests (offline, deterministic)."""

import json

import pytest
from fastapi.testclient import TestClient

from presale.api.qa import app, reset_qa_runner


@pytest.fixture(autouse=True)
def _reset_runner():
    reset_qa_runner()
    yield
    reset_qa_runner()


CATALOG = [
    {
        "source_id": "catalog-001",
        "version": "2026.09.01",
        "tenant_id": "tenant-demo",
        "product_id": "product-001",
        "status": "published",
        "fields": {"spec": {"season": "适合夏季使用"}},
    }
]


def write_catalog(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(CATALOG), encoding="utf-8")
    return str(path)


def test_health(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    resp = TestClient(app).get("/api/v1/presale/qa/health")

    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_qa_returns_deterministic_answer_offline(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_RETRIEVAL_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/presale/qa",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "qa-key-000001",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["terminal"] == "finalize"
    assert body["answer_id"]
    assert "根据已发布商品资料" in body.get("answer_text", "")
