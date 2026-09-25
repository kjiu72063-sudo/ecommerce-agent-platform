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


def test_ready_without_postgres(monkeypatch):
    monkeypatch.delenv("PRESALE_PG_DSN", raising=False)
    resp = TestClient(app).get("/api/v1/presale/qa/ready")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "persistence": "default"}


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


def test_qa_records_observability_metrics(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)
    client = TestClient(app)

    r1 = client.post(
        "/api/v1/presale/qa",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "qa-key-000009",
        },
    )
    assert r1.status_code == 200

    m = client.get("/api/v1/presale/qa/metrics").json()
    assert m["requests"] == 1
    assert m["terminal"]["finalize"] == 1
    assert m["errors"] == 0
    assert m["last_run_seconds"] is not None


def test_index_serves_demo_ui():
    resp = TestClient(app).get("/")

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "售前问答演示" in resp.text
    # P1 UI: history sidebar + feedback buttons + config mode badges
    assert "问答历史" in resp.text
    assert "有帮助" in resp.text
    assert "/api/v1/presale/qa/config" in resp.text
    assert "/api/v1/presale/qa/history" in resp.text


def test_examples_endpoint_returns_products_and_questions():
    resp = TestClient(app).get("/api/v1/presale/qa/examples")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tenant_id"] == "tenant-demo"
    assert len(body["products"]) >= 1
    first = body["products"][0]
    assert first["product_id"]
    assert first["name"]
    assert first["questions"]
    assert all(isinstance(q, str) and q for q in first["questions"])


def test_qa_response_exposes_evidence_fields(tmp_path, monkeypatch):
    """演示 UI 依赖 evidence/confidence_signal/reason_codes 三字段。"""
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_RETRIEVAL_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)

    resp = TestClient(app).post(
        "/api/v1/presale/qa",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "qa-key-evidence01",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["evidence"], list)
    assert body["confidence_signal"] in {
        "supported",
        "uncertain",
        "conflicting",
        "unavailable",
    }
    assert isinstance(body["reason_codes"], list)
    if body["evidence"]:
        assert {"locator", "source_id"} <= set(body["evidence"][0])
        # P1: evidence carries field content for the UI's expandable preview
        assert body["evidence"][0]["content"] == "适合夏季使用"


def test_config_reports_template_and_deterministic(monkeypatch):
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_MILVUS_URI", raising=False)
    monkeypatch.delenv("PRESALE_QDRANT_URL", raising=False)
    monkeypatch.delenv("PRESALE_RETRIEVAL_BASE_URL", raising=False)

    body = TestClient(app).get("/api/v1/presale/qa/config").json()

    assert body == {"llm": "template", "model": None, "retrieval": "deterministic"}


def test_config_reports_real_llm_and_hybrid(monkeypatch):
    monkeypatch.setenv("PRESALE_LLM_BASE_URL", "http://llm.local/v1")
    monkeypatch.setenv("PRESALE_LLM_MODEL", "demo-model")
    monkeypatch.setenv("PRESALE_LLM_API_KEY", "demo-key")
    monkeypatch.setenv("PRESALE_MILVUS_URI", "http://127.0.0.1:19530")

    body = TestClient(app).get("/api/v1/presale/qa/config").json()

    assert body["llm"] == "real"
    assert body["model"] == "demo-model"
    assert body["retrieval"] == "hybrid"


def test_history_recorded_after_qa(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/presale/qa",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "qa-key-history01",
        },
    )
    assert resp.status_code == 200

    items = client.get("/api/v1/presale/qa/history").json()["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["question"] == "这款商品适合夏季使用吗？"
    assert entry["product_id"] == "product-001"
    assert entry["terminal"] == resp.json()["terminal"]
    assert entry["evidence_count"] >= 1
    assert entry["response"]["answer_text"]
    assert entry["id"] == resp.json()["run_ref"]
    # limit is honored
    assert len(client.get("/api/v1/presale/qa/history?limit=1").json()["items"]) == 1


def test_feedback_endpoint_records_rating():
    client = TestClient(app)

    ok = client.post(
        "/api/v1/presale/qa/feedback",
        json={"run_ref": "run_fb_1", "rating": "up"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"status": "recorded", "rating": "up"}

    bad = client.post(
        "/api/v1/presale/qa/feedback",
        json={"run_ref": "run_fb_1", "rating": "meh"},
    )
    assert bad.status_code == 422


def test_review_analyze_positive_text():
    resp = TestClient(app).post(
        "/api/v1/review/analyze",
        json={"text": "鞋子收到了，非常满意！防滑效果很好，穿着舒适，值得推荐给朋友。"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sentiment"] == "positive"
    assert {"满意", "推荐"} <= set(body["keywords"])
    assert body["need_human"] is True
    assert "positive" in body["answer_text"]


def test_review_analyze_negative_with_product(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    resp = TestClient(app).post(
        "/api/v1/review/analyze",
        json={
            "text": "太失望了，质量很差，穿了两天就开胶，准备退货退款。",
            "product_id": "product-001",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sentiment"] == "negative"
    assert {"失望", "退货"} <= set(body["keywords"])
    # product knowledge linked via the review agent's retrieve tool
    assert body["evidence_count"] >= 1


def test_review_analyze_rejects_empty_text():
    resp = TestClient(app).post("/api/v1/review/analyze", json={"text": ""})

    assert resp.status_code == 422


def test_index_serves_review_tab():
    body = TestClient(app).get("/").text

    assert "评论分析" in body
    assert "/api/v1/review/analyze" in body
    assert "review_samples" in body
    # P2: streaming endpoint + session follow-up
    assert "/api/v1/presale/qa/stream" in body
    assert "session_id" in body
    # Tab switch relies on [hidden]; .layout's display:grid would otherwise
    # keep the QA panel visible on the review tab.
    assert "[hidden]" in body
    # Platform visibility: run timeline + multi-agent relay
    assert "运行时间线" in body
    assert "多 Agent 接力" in body
    assert "/api/v1/coordinator/run" in body


def test_stream_endpoint_sends_sse_events(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)

    resp = TestClient(app).post(
        "/api/v1/presale/qa/stream",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "stream-key-0001",
        },
    )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    body = resp.text
    assert "event: evidence" in body
    assert "event: token" in body
    assert "event: done" in body
    done_line = next(
        line for line in body.splitlines() if line.startswith("data: ") and "answer_text" in line
    )
    done = json.loads(done_line[len("data: "):])
    assert done["answer_text"]
    assert done["terminal"] in {"finalize", "need_human"}
    assert isinstance(done["evidence"], list)
    assert done["session_id"]


def test_stream_records_history_and_session(tmp_path, monkeypatch):
    from presale.api import qa as qa_module

    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/v1/presale/qa/stream",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "stream-key-0002",
            "session_id": "sess-test-01",
        },
    )
    assert resp.status_code == 200

    items = client.get("/api/v1/presale/qa/history").json()["items"]
    assert len(items) == 1
    assert items[0]["id"].startswith("run_")
    turns = qa_module._sessions["sess-test-01"]["turns"]
    assert len(turns) == 1
    assert turns[0]["question"] == "这款商品适合夏季使用吗？"
    assert turns[0]["answer"]


def test_stream_second_turn_appends_session(tmp_path, monkeypatch):
    from presale.api import qa as qa_module

    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    client = TestClient(app)
    base = {
        "product_id": "product-001",
        "tenant_id": "tenant-demo",
        "session_id": "sess-test-02",
    }
    for index in (1, 2):
        resp = client.post(
            "/api/v1/presale/qa/stream",
            json={
                **base,
                "question": f"这款商品适合夏季使用吗？第{index}轮",
                "idempotency_key": f"stream-key-turn{index}",
            },
        )
        assert resp.status_code == 200

    turns = qa_module._sessions["sess-test-02"]["turns"]
    assert len(turns) == 2
    assert "第1轮" in turns[0]["question"]
    assert "第2轮" in turns[1]["question"]


def test_qa_response_includes_timeline(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)

    resp = TestClient(app).post(
        "/api/v1/presale/qa",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "timeline-key-01",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    stages = [s["stage"] for s in body["timeline"]]
    assert stages == ["submitted", "knowledge_retrieved", "context_built", "answer_generated"]
    assert all(s["occurred_at"] for s in body["timeline"])
    assert body["disposition"] in {"pending", "escalated", "complete"}
    assert isinstance(body["configuration_refs"], dict)


def test_stream_done_includes_timeline(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)

    resp = TestClient(app).post(
        "/api/v1/presale/qa/stream",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "timeline-key-02",
        },
    )

    assert resp.status_code == 200
    done_line = next(
        line for line in resp.text.splitlines()
        if line.startswith("data: ") and "answer_text" in line
    )
    done = json.loads(done_line[len("data: "):])
    stages = [s["stage"] for s in done["timeline"]]
    assert stages == ["submitted", "knowledge_retrieved", "context_built", "answer_generated"]
    assert done["disposition"] == "pending"


def test_coordinator_run_full_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESALE_CATALOG", write_catalog(tmp_path))
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("PRESALE_DB", raising=False)

    resp = TestClient(app).post(
        "/api/v1/coordinator/run",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "relay-key-00001",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["agents"] == ["presale-qa", "review-analyzer"]
    assert len(body["sub_outcomes"]) == 2
    assert body["short_circuited"] is False
    # Presale finalizes on evidence; Review always needs a human.
    assert body["pipeline"][0]["terminal"] == "finalize"
    assert body["pipeline"][1]["terminal"] == "need_human"
    assert body["pipeline"][1]["need_human"] is True
    assert body["overall_terminal"] == "need_human"


def test_coordinator_short_circuits_on_presale_need_human(monkeypatch):
    monkeypatch.delenv("PRESALE_CATALOG", raising=False)
    monkeypatch.delenv("PRESALE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PRESALE_LLM_API_KEY", raising=False)

    resp = TestClient(app).post(
        "/api/v1/coordinator/run",
        json={
            "question": "这款商品适合夏季使用吗？",
            "product_id": "product-001",
            "tenant_id": "tenant-demo",
            "idempotency_key": "relay-key-00002",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    # No catalog → Presale NEED_HUMAN → Review never runs.
    assert len(body["sub_outcomes"]) == 1
    assert body["short_circuited"] is True
    assert body["overall_terminal"] == "need_human"
