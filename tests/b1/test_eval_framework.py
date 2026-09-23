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
    build_retriever,
    run_end_to_end,
    run_generation,
    run_retrieval,
    summarize,
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
        if "质检评审" in last or "judge" in last:
            judge = (
                '{"faithfulness": 1, "answer_correctness": 1, '
                '"gold_correctness": 1, "unsupported_claims": 0}'
            )
            return {"choices": [{"message": {"content": judge}}]}
        return {"choices": [{"message": {"content": "根据资料，适合夏季使用。"}}]}


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
    """方向7: one transient failure on the first generation is retried."""
    from presale.answer import AnswerGenerationError

    class FlakyGenerator(PresaleAnswerGenerator):
        def __init__(self):
            self.attempts = 0

        def generate(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == 1:
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
    assert flaky.attempts == 2  # first failed, retry succeeded, replay did not call


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
