import io
import json
from datetime import datetime, timezone
from contextlib import redirect_stdout

from presale.cli import build_runner, format_result, load_catalog, main
from presale.contracts import ProductQuestion

SAMPLE_CATALOG = [
    {
        "source_id": "catalog-001",
        "version": "2026.09.01",
        "tenant_id": "tenant-demo",
        "product_id": "product-001",
        "status": "published",
        "fields": {"spec": {"season": "适合夏季使用", "material": "轻量透气面料"}},
    }
]


def question():
    return ProductQuestion(
        question_id="question-cli",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        idempotency_key="cli-key-001",
    )


def test_load_catalog_roundtrips_knowledge_sources(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")

    sources = load_catalog(str(path))

    assert len(sources) == 1
    assert sources[0].source_id == "catalog-001"
    assert sources[0].tenant_id == "tenant-demo"
    assert sources[0].product_id == "product-001"


def test_format_result_is_deterministic_and_observable():
    runner = build_runner(SAMPLE_CATALOG)
    result = runner.ask(question())

    formatted = format_result(result)

    assert formatted["run_ref"] == result.run_ref
    assert formatted["question_id"] == "question-cli"
    assert formatted["need_human"] is False
    assert formatted["confidence"] == "supported"
    assert formatted["evidence"]  # 非空证据
    assert "catalog-001" in formatted["evidence"][0]


def test_main_outputs_question_evidence_and_run_ref(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        main([
            "--catalog", str(path),
            "--tenant", "tenant-demo",
            "--product", "product-001",
            "--question", "这款商品适合夏季使用吗？",
            "--idempotency-key", "cli-key-001",
            "--user-id", "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        ])

    out = buffer.getvalue()
    assert "run_ref" in out
    assert "catalog-001" in out
    assert "supported" in out


def test_main_is_readonly_does_not_invoke_writes(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        main([
            "--catalog", str(path),
            "--tenant", "tenant-demo",
            "--product", "product-001",
            "--question", "这款商品适合夏季使用吗？",
            "--idempotency-key", "cli-key-002",
            "--user-id", "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        ])

    assert "买" not in buffer.getvalue()
    assert "改价" not in buffer.getvalue()


def test_main_defaults_to_sys_argv(monkeypatch, tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "presale-qa",
            "--catalog", str(path),
            "--tenant", "tenant-demo",
            "--product", "product-001",
            "--question", "这款商品适合夏季使用吗？",
            "--idempotency-key", "cli-key-003",
            "--user-id", "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        ],
    )
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        main()

    assert "run_ref" in buffer.getvalue()