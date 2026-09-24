"""F-01: presale-eval framework offline contract tests.

Tests the unified evaluation entry (`eval_framework`) with injected
fake retriever/transport — no real Milvus or LLM required.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from presale.adapters.eval_framework import (
    MODES,
    build_retriever,
    golden_meta,
    render_markdown,
    run_end_to_end,
    run_generation,
    run_multi_agent,
    run_retrieval,
    run_review,
    summarize,
    write_report,
)
from presale.adapters.eval_framework import (
    main as eval_main,
)
from presale.adapters.generation_eval import evaluate_idempotency_replay
from presale.answer import PresaleAnswerGenerator
from presale.knowledge import EvidenceItem, KnowledgeSource


def _mini_golden():
    """A tiny golden set for offline retrieval tests."""
    return [
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-001",
            "query": "大热天会晒黑吗",
            "expected": {"spec_upf"},
            "evidence_sources": [],
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-001",
            "query": "水洗还能防晒吗",
            "expected": {"wash_stability"},
            "evidence_sources": [],
        },
    ]


class FakeRetriever:
    """Deterministic retriever that returns expected locators from the golden set."""

    def __init__(self, *, matched=True):
        self._matched = matched
        self._locator_by_query = {
            "大热天会晒黑吗": "spec_upf",
            "水洗还能防晒吗": "wash_stability",
        }

    def retrieve(self, question):
        from presale.knowledge import RetrievalResult, RetrievalStatus

        if not self._matched:
            return RetrievalResult(status=RetrievalStatus.NO_EVIDENCE, evidence_items=[])
        locator = self._locator_by_query.get(question.question_text, "spec_unknown")
        item = EvidenceItem(
            source_id="catalog-001",
            source_version="2026.09.01",
            locator=locator,
            content_digest="sha256:" + "a" * 64,
            tenant_id=question.tenant_id,
            product_id=question.product_id,
            content="适合夏季使用，纯棉材质",
        )
        return RetrievalResult(
            status=RetrievalStatus.MATCHED,
            evidence_items=[item],
        )


class FakeTransport:
    """Fixed LLM-as-judge/answer transport: always '1' faithfulness, plausible answer."""

    def __call__(self, *, api_key, base_url, model, messages, timeout_s):
        last = messages[-1]["content"] if messages else ""
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if "质检评审" in last or "judge" in last:
            judge = (
                '{"faithfulness": 1, "answer_correctness": 1, '
                '"gold_correctness": 1, "unsupported_claims": 0}'
            )
            return {"choices": [{"message": {"content": judge}}], "usage": usage}
        return {"choices": [{"message": {"content": "根据资料，适合夏季使用。"}}], "usage": usage}


def _sources():
    return [
        KnowledgeSource(
            source_id="catalog-001",
            version="2026.09.01",
            tenant_id="tenant-demo",
            product_id="product-001",
            status="published",
            fields={"spec": {"season": "适合夏季使用"}},
        )
    ]


def _mini_golden_questions():
    """One golden-shaped question for focused e2e latency/cost tests."""
    return [
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-001",
            "query": "这件防晒衣能挡住紫外线吗",
            "gold": "能。UPF50+。",
        }
    ]


def test_run_retrieval_returns_report():
    """F-01: run_retrieval returns dict with hit_at_k and mrr."""
    report = run_retrieval(FakeRetriever(), to_questions=_mini_golden)
    assert "hit_at_k" in report
    assert "mrr" in report
    assert report["mrr"] == 1.0  # FakeRetriever always matches expected locator


def test_run_retrieval_no_evidence():
    """F-01: retriever with no evidence still returns a report."""
    report = run_retrieval(FakeRetriever(matched=False), to_questions=_mini_golden)
    assert report["mrr"] == 0.0


def test_run_generation_returns_report():
    """F-01: run_generation returns dict with mean_faithfulness."""
    report = run_generation(
        FakeRetriever(),
        transport=FakeTransport(),
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key="test-key",
    )
    assert "mean_faithfulness" in report
    assert report["mean_faithfulness"] == 1.0


def test_run_end_to_end_returns_report():
    """F-01: run_end_to_end returns dict with mean_faithfulness."""
    report = run_end_to_end(
        FakeRetriever(),
        sources=_sources(),
        generator=None,
        transport=FakeTransport(),
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key="test-key",
    )
    assert "mean_faithfulness" in report
    assert report["n"] >= 1


def test_e2e_report_includes_latency_and_tokens():
    """方向8: e2e report carries latency, per-question timings, and token usage."""
    report = run_end_to_end(
        FakeRetriever(),
        sources=_sources(),
        generator=None,
        transport=FakeTransport(),
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key="test-key",
        questions=_mini_golden_questions(),
    )
    assert "latency" in report
    assert report["latency"]["wall_s"] >= 0
    assert report["latency"]["mean_ask_ms"] is None or report["latency"]["mean_ask_ms"] >= 0
    assert "tokens" in report
    # judge transport ran once per question and reported usage
    assert report["tokens"]["judge_prompt"] == 10 * len(report["per_question"])
    assert report["tokens"]["judge_completion"] == 5 * len(report["per_question"])
    ok_rows = [r for r in report["per_question"] if "error" not in r]
    assert all("judge_latency_ms" in r for r in ok_rows)
    assert all(r["judge_latency_ms"] >= 0 for r in ok_rows)


def test_e2e_cost_null_without_prices(monkeypatch):
    """方向8: cost stays unpriced when env prices are absent."""
    monkeypatch.delenv("PRESALE_LLM_INPUT_PRICE_PER_M", raising=False)
    monkeypatch.delenv("PRESALE_LLM_OUTPUT_PRICE_PER_M", raising=False)
    report = run_end_to_end(
        FakeRetriever(),
        sources=_sources(),
        generator=None,
        transport=FakeTransport(),
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key="test-key",
        questions=_mini_golden_questions(),
    )
    assert report["cost"]["priced"] is False
    assert report["cost"]["estimated_usd"] is None


def test_e2e_cost_estimated_with_prices(monkeypatch):
    """方向8: USD cost = prompt/1M*in + completion/1M*out when prices set."""
    monkeypatch.setenv("PRESALE_LLM_INPUT_PRICE_PER_M", "2.5")
    monkeypatch.setenv("PRESALE_LLM_OUTPUT_PRICE_PER_M", "10")
    questions = _mini_golden_questions()
    report = run_end_to_end(
        FakeRetriever(),
        sources=_sources(),
        generator=None,
        transport=FakeTransport(),
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key="test-key",
        questions=questions,
    )
    n = len(questions)
    # judge-only: n * (10 prompt + 5 completion) — generator is PresaleAnswerGenerator (no LLM)
    expected = (n * 10) / 1_000_000 * 2.5 + (n * 5) / 1_000_000 * 10
    assert report["cost"]["priced"] is True
    assert report["cost"]["estimated_usd"] == round(expected, 6)
    assert summarize("end-to-end", report).find("cost_usd=") >= 0


def test_idempotency_replay_uses_persisted_answer(tmp_path):
    """方向7: replay returns the durable answer without a second generation."""
    report = evaluate_idempotency_replay(
        FakeRetriever(),
        sources=_sources(),
        generator=PresaleAnswerGenerator(),
        database=tmp_path / "replay.sqlite3",
        question=_mini_golden()[0],
    )

    assert report["same_answer"] is True
    assert report["generator_calls"] >= 1
    assert report["replayed_without_generation"] is True


def test_idempotency_replay_retries_transient_first_failure(tmp_path, monkeypatch):
    """方向7: transient failures on the first generation are retried."""
    from presale.answer import AnswerGenerationError

    class FlakyGenerator(PresaleAnswerGenerator):
        def __init__(self):
            self.attempts = 0

        def generate(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts <= 2:
                raise AnswerGenerationError("LLM_CALL_FAILED")
            return super().generate(*args, **kwargs)

    flaky = FlakyGenerator()
    monkeypatch.setattr("presale.adapters.generation_eval.time.sleep", lambda _s: None)
    report = evaluate_idempotency_replay(
        FakeRetriever(),
        sources=_sources(),
        generator=flaky,
        database=tmp_path / "replay-retry.sqlite3",
        question=_mini_golden()[0],
    )

    assert report["same_answer"] is True
    assert report["replayed_without_generation"] is True
    assert flaky.attempts == 3  # two failures, one success, replay did not call


def test_build_retriever_none_when_unconfigured(monkeypatch):
    """F-01: build_retriever returns None without Milvus/Qdrant env."""
    monkeypatch.delenv("PRESALE_MILVUS_URI", raising=False)
    monkeypatch.delenv("PRESALE_QDRANT_URL", raising=False)
    monkeypatch.delenv("PRESALE_RETRIEVAL_BASE_URL", raising=False)
    assert build_retriever() is None


def test_summarize_retrieval():
    """F-01: summarize renders a readable text summary."""
    report = run_retrieval(FakeRetriever(), to_questions=_mini_golden)
    text = summarize("retrieval", report)
    assert "hit@1" in text or "mrr" in text
    assert "1.0" in text


def test_summarize_generation():
    """F-01: summarize renders generation report."""
    report = run_generation(
        FakeRetriever(),
        transport=FakeTransport(),
        base_url="https://example.test/v1",
        model="gpt-test",
        api_key="test-key",
    )
    text = summarize("generation", report)
    assert "faithfulness" in text


# --- 方向2: --fail-on-regression ---


def _write_tmp_report(tmp: str, report: dict, name: str) -> str:
    p = Path(tmp) / name
    p.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _report_with_rank(rank) -> dict:
    return {
        "mode": "retrieval",
        "n": 1,
        "per_question": [
            {
                "query": "大热天会晒黑吗",
                "tenant_id": "tenant-demo",
                "product_id": "product-001",
                "expected": ["spec_upf"],
                "rank": rank,
                "recalled": rank is not None,
            }
        ],
    }


def test_compare_fail_on_regression_exit_1():
    """方向2: --compare with regression + --fail-on-regression exits 1."""
    with tempfile.TemporaryDirectory() as tmp:
        a = _write_tmp_report(tmp, _report_with_rank(1), "a.json")
        b = _write_tmp_report(tmp, _report_with_rank(3), "b.json")
        with pytest.raises(SystemExit) as exc:
            eval_main(["--compare", a, b, "--fail-on-regression"])
        assert exc.value.code == 1


def test_compare_no_regression_exit_0():
    """方向2: --compare without regression exits 0 even with --fail-on-regression."""
    with tempfile.TemporaryDirectory() as tmp:
        a = _write_tmp_report(tmp, _report_with_rank(1), "a.json")
        b = _write_tmp_report(tmp, _report_with_rank(1), "b.json")
        rc = eval_main(["--compare", a, b, "--fail-on-regression"])
        assert rc == 0


def test_compare_improved_exit_0():
    """方向2: only improvements do not fail the gate."""
    with tempfile.TemporaryDirectory() as tmp:
        a = _write_tmp_report(tmp, _report_with_rank(3), "a.json")
        b = _write_tmp_report(tmp, _report_with_rank(1), "b.json")
        rc = eval_main(["--compare", a, b, "--fail-on-regression"])
        assert rc == 0


def test_compare_accepts_flat_snapshot_format():
    """方向2: compare_reports accepts eval_regression flat snapshot (key -> {expected, rank})."""
    from presale.adapters.eval_framework import compare_reports

    flat = {
        "tenant-demo/product-001::大热天会晒黑吗": {"expected": ["spec_upf"], "rank": 1},
    }
    report = {
        "mode": "retrieval",
        "n": 1,
        "per_question": [
            {
                "query": "tenant-demo/product-001::大热天会晒黑吗",
                "rank": 3,
            }
        ],
    }
    result = compare_reports(flat, report)
    assert result["summary"]["regressed"] == 1
    assert result["regressed"][0]["old"] == 1
    assert result["regressed"][0]["new"] == 3


# --- 方向8余量: review / multi-agent modes ---


def test_modes_include_review_and_multi_agent():
    """方向8: CLI exposes review and multi-agent modes."""
    assert "review" in MODES
    assert "multi-agent" in MODES


def test_run_review_sentiment_accuracy():
    """方向8: review golden scores perfect sentiment accuracy offline."""
    report = run_review()
    assert report["n"] >= 6
    assert report["errors"] == 0
    assert report["sentiment_accuracy"] == 1.0
    assert report["need_human_rate"] == 1.0
    assert report["mean_keyword_recall"] is not None
    assert report["mean_keyword_recall"] >= 0.6
    text = summarize("review", report)
    assert "sentiment_accuracy=1.0" in text


def test_run_multi_agent_presale_to_review():
    """方向8: multi-agent pipeline runs offline and short-circuits on review need_human."""
    sources = _sources()
    # product-001 has evidence in _sources → presale finalizes → review runs
    # → review always need_human → overall need_human, both agents executed.
    report = run_multi_agent(
        sources=sources,
        questions=[
            {
                "tenant_id": "tenant-demo",
                "product_id": "product-001",
                "query": "这款商品适合夏季使用吗？",
                "gold": "适合夏季。",
            }
        ],
    )
    assert report["n"] == 1
    assert report["errors"] == 0
    assert report["terminals"]["need_human"] == 1
    assert report["mean_sub_agents"] == 2.0
    assert report["short_circuit_rate"] == 0.0
    assert report["final_need_human_rate"] == 1.0
    row = report["per_question"][0]
    assert row["sub_agent_count"] == 2
    assert row["sub_terminals"] == ["finalize", "need_human"]
    assert "short_circuit_rate=" in summarize("multi-agent", report)


def test_run_multi_agent_short_circuits_without_evidence():
    """方向8: presale need_human (no evidence) stops before review runs."""
    report = run_multi_agent(
        sources=[],  # no evidence anywhere
        questions=[
            {
                "tenant_id": "tenant-demo",
                "product_id": "product-001",
                "query": "有证据吗？",
                "gold": "无。",
            }
        ],
    )
    assert report["n"] == 1
    assert report["errors"] == 0
    assert report["short_circuit_rate"] == 1.0
    assert report["mean_sub_agents"] == 1.0
    row = report["per_question"][0]
    assert row["sub_agent_count"] == 1
    assert row["sub_terminals"] == ["need_human"]


# --- 方向8剩余: Markdown 报告 + golden 版本化 ---


def test_golden_meta_reports_versions_and_catalog_fingerprint():
    """方向8: golden_meta stamps version constants and a catalog sha256 prefix."""
    meta = golden_meta("review")
    assert meta["mode"] == "review"
    assert meta["generation_golden_version"]
    assert meta["generation_golden_size"] >= 18
    assert meta["review_golden_version"]
    assert meta["review_golden_size"] >= 6
    assert meta["catalog_sha256"] is None or len(meta["catalog_sha256"]) == 16
    assert meta["saved_at"]


def test_render_markdown_single_mode_report():
    """方向8: render_markdown emits a title, mode section, and metric table."""
    report = {
        "mode": "review",
        "golden": golden_meta("review"),
        "n": 6,
        "errors": 0,
        "sentiment_accuracy": 1.0,
        "need_human_rate": 1.0,
        "per_question": [
            {"index": 0, "sentiment_correct": True, "text": "非常好用"},
        ],
    }
    md = render_markdown(report)
    assert md.startswith("# Presale evaluation report")
    assert "## review" in md
    assert "| sentiment_accuracy | 1 |" in md
    assert "### Per-question" in md
    assert "golden.review_golden_version" in md


def test_render_markdown_combined_modes():
    """方向8: --mode all style {modes: [...]} renders one section per mode."""
    md = render_markdown(
        {
            "modes": [
                {"mode": "retrieval", "n": 2, "mrr": 1.0},
                {"mode": "review", "n": 6, "sentiment_accuracy": 1.0},
            ]
        }
    )
    assert "## retrieval" in md
    assert "## review" in md
    assert "| mrr | 1 |" in md


def test_write_report_markdown_by_extension(tmp_path):
    """方向8: --output path ending in .md writes Markdown, not JSON."""
    target = tmp_path / "report.md"
    write_report({"mode": "review", "n": 1, "sentiment_accuracy": 1.0}, str(target))
    text = target.read_text(encoding="utf-8")
    assert text.startswith("# Presale evaluation report")
    assert "## review" in text


def test_write_report_json_default(tmp_path):
    """方向8: non-.md path still writes JSON."""
    target = tmp_path / "report.json"
    write_report({"mode": "review", "n": 1}, str(target))
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["mode"] == "review"


# --- 批量评估 + 汇总 CSV + compare-batch ---


def test_load_golden_file_array(tmp_path):
    """批量: load_golden_file reads a JSON array of objects."""
    from presale.adapters.eval_framework import load_golden_file

    path = tmp_path / "golden.json"
    path.write_text(
        json.dumps([{"text": "很好", "expected_sentiment": "positive"}]),
        encoding="utf-8",
    )
    items = load_golden_file(path)
    assert items == [{"text": "很好", "expected_sentiment": "positive"}]


def test_load_golden_file_rejects_non_array(tmp_path):
    """批量: non-array golden file is rejected."""
    from presale.adapters.eval_framework import load_golden_file

    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"text": "not-a-list"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        load_golden_file(path)


def test_report_csv_row_and_write_summary_csv(tmp_path):
    """批量: report_csv_row flattens metrics; write_summary_csv unions columns."""
    from presale.adapters.eval_framework import report_csv_row, write_summary_csv

    report = {
        "mode": "review",
        "n": 6,
        "errors": 0,
        "sentiment_accuracy": 1.0,
        "need_human_rate": 1.0,
        "golden": {"review_golden_version": "1.0.0"},
    }
    row = report_csv_row(report, source="a.json")
    assert row["mode"] == "review"
    assert row["source"] == "a.json"
    assert row["sentiment_accuracy"] == 1.0
    assert row["golden_review_golden_version"] == "1.0.0"

    out = tmp_path / "summary.csv"
    write_summary_csv([row, {"mode": "live-clipper", "source": "b.json", "n": 3}], str(out))
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("mode,")
    assert "source" in lines[0]
    assert len(lines) == 3  # header + 2 rows


def test_compare_batch_multiple_pairs(tmp_path):
    """批量 golden 回归: 多对 baseline:current，任一对回退则 fail-on-regression=1."""
    from presale.adapters.eval_framework import compare_batch

    def _write(name, rank):
        p = tmp_path / name
        p.write_text(
            json.dumps(
                {
                    "mode": "retrieval",
                    "n": 1,
                    "per_question": [{"query": "q1", "rank": rank}],
                }
            ),
            encoding="utf-8",
        )
        return str(p)

    a1, b1 = _write("a1.json", 1), _write("b1.json", 1)  # no change
    a2, b2 = _write("a2.json", 1), _write("b2.json", 3)  # regressed

    rows, code0 = compare_batch([f"{a1}::{b1}"], fail_on_regression=True)
    assert code0 == 0
    assert rows[0]["regressed"] == 0

    rows, code1 = compare_batch([f"{a1}::{b1}", f"{a2}::{b2}"], fail_on_regression=True)
    assert code1 == 1
    assert len(rows) == 2
    assert rows[1]["regressed"] == 1

    with pytest.raises(SystemExit):
        compare_batch(["missing-separator"])


def test_cli_inputs_batch_writes_csv(tmp_path):
    """批量: --mode review --inputs 多文件 → 每文件一行 CSV."""
    g1 = tmp_path / "g1.json"
    g1.write_text(
        json.dumps(
            [
                {
                    "text": "非常好用，推荐！",
                    "expected_sentiment": "positive",
                    "expected_keywords": ["好", "推荐"],
                }
            ]
        ),
        encoding="utf-8",
    )
    g2 = tmp_path / "g2.json"
    g2.write_text(
        json.dumps(
            [
                {
                    "text": "太差了准备退货。",
                    "expected_sentiment": "negative",
                    "expected_keywords": ["差", "退货"],
                }
            ]
        ),
        encoding="utf-8",
    )
    csv_path = tmp_path / "out.csv"
    rc = eval_main(
        [
            "--mode",
            "review",
            "--inputs",
            str(g1),
            str(g2),
            "--csv",
            str(csv_path),
        ]
    )
    assert rc == 0
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2 input files
    assert str(g1) in lines[1]
    assert str(g2) in lines[2]
    assert "sentiment_accuracy" in lines[0]


def test_cli_compare_batch_fail_on_regression(tmp_path):
    """批量 golden 回归 CLI: 有回退 + --fail-on-regression → exit 1."""

    def _rank(name, rank):
        p = tmp_path / name
        p.write_text(
            json.dumps(
                {
                    "mode": "retrieval",
                    "n": 1,
                    "per_question": [{"query": "q", "rank": rank}],
                }
            ),
            encoding="utf-8",
        )
        return str(p)

    base = _rank("base.json", 1)
    good = _rank("good.json", 1)
    bad = _rank("bad.json", 5)
    csv_path = tmp_path / "cmp.csv"
    with pytest.raises(SystemExit) as exc:
        eval_main(
            [
                "--compare-batch",
                f"{base}::{good}",
                f"{base}::{bad}",
                "--fail-on-regression",
                "--csv",
                str(csv_path),
            ]
        )
    assert exc.value.code == 1
    assert csv_path.exists()
    assert "regressed" in csv_path.read_text(encoding="utf-8")
