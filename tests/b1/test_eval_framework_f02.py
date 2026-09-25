"""F-02: presale-eval --output persistence + --compare A/B diff contract tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from presale.adapters.eval_framework import compare_reports, write_report


def _retrieval_report(query: str, rank) -> dict:
    return {
        "mode": "retrieval",
        "n": 1,
        "hit_at_k": {"hit@1": 1 if rank == 1 else 0},
        "mrr": 1.0 if rank == 1 else 0.0,
        "per_question": [
            {
                "query": query,
                "tenant_id": "tenant-demo",
                "product_id": "product-001",
                "expected": ["spec_upf"],
                "rank": rank,
                "recalled": rank is not None,
                "top_sources": ["spec_upf"] if rank == 1 else [],
            }
        ],
    }


# --- write_report ---


def test_write_report_writes_json_file():
    """F-02: write_report persists the report to a JSON file."""
    report = _retrieval_report("大热天会晒黑吗", 1)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "report.json"
        write_report(report, str(path))
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["mode"] == "retrieval"
        assert loaded["mrr"] == 1.0


def test_write_report_creates_parent_dirs():
    """F-02: write_report creates missing parent directories."""
    report = _retrieval_report("大热天会晒黑吗", 1)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nested" / "deep" / "report.json"
        write_report(report, str(path))
        assert path.exists()


# --- compare_reports ---


def test_compare_identical_reports_no_diffs():
    """F-02: identical reports produce no regressions/improvements."""
    a = _retrieval_report("大热天会晒黑吗", 1)
    b = _retrieval_report("大热天会晒黑吗", 1)
    result = compare_reports(a, b)
    assert result["regressed"] == []
    assert result["improved"] == []
    assert result["summary"]["regressed"] == 0
    assert result["summary"]["improved"] == 0
    assert result["summary"]["floor_violations"] == 0


def test_compare_rank_regressed():
    """F-02: rank worsening is flagged as regressed."""
    a = _retrieval_report("大热天会晒黑吗", 1)
    b = _retrieval_report("大热天会晒黑吗", 3)
    result = compare_reports(a, b)
    assert len(result["regressed"]) == 1
    assert result["regressed"][0]["old"] == 1
    assert result["regressed"][0]["new"] == 3


def test_compare_rank_improved():
    """F-02: rank improvement is flagged as improved."""
    a = _retrieval_report("大热天会晒黑吗", 3)
    b = _retrieval_report("大热天会晒黑吗", 1)
    result = compare_reports(a, b)
    assert len(result["improved"]) == 1
    assert result["improved"][0]["old"] == 3
    assert result["improved"][0]["new"] == 1


def test_compare_recall_lost_regressed():
    """F-02: losing recall (rank None) is flagged as regressed."""
    a = _retrieval_report("大热天会晒黑吗", 1)
    b = _retrieval_report("大热天会晒黑吗", None)
    result = compare_reports(a, b)
    assert len(result["regressed"]) == 1
    assert result["regressed"][0]["new"] is None


def test_compare_new_query_added():
    """F-02: query present in B but absent in A is listed as added (composite key)."""
    a = _retrieval_report("旧查询", 1)
    b = _retrieval_report("新查询", 1)
    result = compare_reports(a, b)
    assert result["added"] == ["tenant-demo/product-001::新查询"]


def test_compare_error_to_ok_improved():
    """F-02: a question that errored in A but succeeded in B is improved."""
    a = {
        "mode": "end-to-end",
        "n": 1,
        "per_question": [{"query": "q1", "error": "boom"}],
    }
    b = {
        "mode": "end-to-end",
        "n": 1,
        "per_question": [{"query": "q1", "faithfulness": 1}],
    }
    result = compare_reports(a, b)
    assert len(result["improved"]) == 1
    assert result["improved"][0]["old"] == "error"


def test_compare_ok_to_error_regressed():
    """F-02: a question that succeeded in A but errored in B is regressed."""
    a = {
        "mode": "end-to-end",
        "n": 1,
        "per_question": [{"query": "q1", "faithfulness": 1}],
    }
    b = {
        "mode": "end-to-end",
        "n": 1,
        "per_question": [{"query": "q1", "error": "boom"}],
    }
    result = compare_reports(a, b)
    assert len(result["regressed"]) == 1
    assert result["regressed"][0]["new"] == "error"
