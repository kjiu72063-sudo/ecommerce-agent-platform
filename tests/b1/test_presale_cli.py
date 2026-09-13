import asyncio
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone

import pytest

from presale.adapters.sqlite import SQLitePresaleStore, SQLiteRunTraceRepository
from presale.cli import build_runner, format_result, load_catalog, load_trace, main, save_trace
from presale.contracts import ProductQuestion
from presale.trace import PresaleRunTracer

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


@pytest.mark.asyncio
async def test_format_result_is_deterministic_and_observable():
    runner = build_runner(SAMPLE_CATALOG)
    result = await runner.ask(question())

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
        main(
            [
                "--catalog",
                str(path),
                "--tenant",
                "tenant-demo",
                "--product",
                "product-001",
                "--question",
                "这款商品适合夏季使用吗？",
                "--idempotency-key",
                "cli-key-001",
                "--user-id",
                "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
            ]
        )

    out = buffer.getvalue()
    assert "run_ref" in out
    assert "catalog-001" in out
    assert "supported" in out


def test_main_is_readonly_does_not_invoke_writes(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        main(
            [
                "--catalog",
                str(path),
                "--tenant",
                "tenant-demo",
                "--product",
                "product-001",
                "--question",
                "这款商品适合夏季使用吗？",
                "--idempotency-key",
                "cli-key-002",
                "--user-id",
                "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
            ]
        )

    assert "买" not in buffer.getvalue()
    assert "改价" not in buffer.getvalue()


def test_main_defaults_to_sys_argv(monkeypatch, tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "presale-qa",
            "--catalog",
            str(path),
            "--tenant",
            "tenant-demo",
            "--product",
            "product-001",
            "--question",
            "这款商品适合夏季使用吗？",
            "--idempotency-key",
            "cli-key-003",
            "--user-id",
            "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        ],
    )
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        main()

    assert "run_ref" in buffer.getvalue()


@pytest.mark.asyncio
async def test_save_and_load_trace_roundtrip(tmp_path):
    trace_path = tmp_path / "traces.json"
    runner = build_runner(SAMPLE_CATALOG)
    result = await runner.ask(question())

    save_trace(str(trace_path), result.trace)

    trace = load_trace(str(trace_path), run_ref=result.run_ref, tenant_id="tenant-demo")

    assert trace.run_ref == result.run_ref
    assert trace.tenant_id == "tenant-demo"
    assert trace.question_id == "question-cli"


@pytest.mark.asyncio
async def test_format_result_includes_context_and_disposition(tmp_path):
    runner = build_runner(SAMPLE_CATALOG)
    result = await runner.ask(question())

    formatted = format_result(result)

    assert formatted["context_package_ref"] == result.trace.context_package_ref
    assert formatted["disposition_state"] == "pending"


def test_main_queries_trace_by_run_ref(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    trace_path = tmp_path / "traces.json"

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(
            [
                "--catalog",
                str(path),
                "--tenant",
                "tenant-demo",
                "--product",
                "product-001",
                "--question",
                "这款商品适合夏季使用吗？",
                "--idempotency-key",
                "cli-key-004",
                "--user-id",
                "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
                "--save-trace",
                str(trace_path),
            ]
        )
    run_ref = json.loads(buffer.getvalue())["run_ref"]

    qbuffer = io.StringIO()
    with redirect_stdout(qbuffer):
        main(
            [
                "--trace-file",
                str(trace_path),
                "--trace-run-ref",
                run_ref,
                "--tenant",
                "tenant-demo",
            ]
        )

    loaded = json.loads(qbuffer.getvalue())
    assert loaded["run_ref"] == run_ref
    assert loaded["tenant_id"] == "tenant-demo"


def test_main_prints_budget_error_to_stderr(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    err = io.StringIO()

    with pytest.raises(SystemExit) as exc, redirect_stdout(io.StringIO()):
        with redirect_stderr(err):
            main(
                [
                    "--catalog",
                    str(path),
                    "--tenant",
                    "tenant-demo",
                    "--product",
                    "product-001",
                    "--question",
                    "这款商品适合夏季使用吗？",
                    "--idempotency-key",
                    "cli-key-005",
                    "--user-id",
                    "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
                    "--token-budget",
                    "1",
                ]
            )

    assert exc.value.code != 0
    assert "TOKEN_BUDGET_EXCEEDED" in err.getvalue()


def test_main_archive_expired_wires_retention_to_sqlite(tmp_path):
    db_path = tmp_path / "retention.sqlite3"
    run_ref = "run_01111111-1111-7111-8111-111111111111"

    async def seed():
        repo = SQLiteRunTraceRepository(SQLitePresaleStore(db_path))
        tracer = PresaleRunTracer(trace_repo=repo)
        await tracer.start(
            question=ProductQuestion(
                question_id="question-retention",
                tenant_id="tenant-demo",
                submitted_by={
                    "actor_type": "user",
                    "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
                },
                product_id="product-001",
                question_text="这款商品适合夏季使用吗？",
                requested_at=datetime.now(timezone.utc) - timedelta(days=40),
                idempotency_key="retention-key-001",
            ),
            task_id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
            agent_run_id=run_ref,
            configuration_refs={},
        )
        await tracer.mark_disposition_complete(run_ref, tenant_id="tenant-demo")

    asyncio.run(seed())

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["--db", str(db_path), "--tenant", "tenant-demo", "--archive-expired"])

    out = json.loads(buffer.getvalue())
    assert run_ref in out["archived"]


def test_archive_expired_requires_db_path(tmp_path):
    buffer = io.StringIO()
    with pytest.raises(SystemExit), redirect_stderr(io.StringIO()), redirect_stdout(buffer):
        main(["--tenant", "tenant-demo", "--archive-expired"])


def test_db_without_archive_expired_is_rejected(tmp_path):
    # --db is only meaningful with --archive-expired; silently ignoring it would
    # mislead an operator, so it must be rejected in a normal QA run.
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")
    buffer = io.StringIO()

    with pytest.raises(SystemExit), redirect_stderr(io.StringIO()), redirect_stdout(buffer):
        main(
            [
                "--catalog",
                str(path),
                "--tenant",
                "tenant-demo",
                "--product",
                "product-001",
                "--question",
                "这款商品适合夏季使用吗？",
                "--idempotency-key",
                "cli-key-006",
                "--db",
                str(tmp_path / "x.sqlite3"),
            ]
        )
