"""Offline tests for retrieval-evaluation metric math (no retriever needed)."""

from presale.adapters.retrieval_eval import evaluate, hit_at_k, mrr, precision_at_k


def test_hit_at_k_only_counts_top_k():
    sources = ["a", "b", "c"]
    assert hit_at_k(sources, {"a"}, 1) == 1
    assert hit_at_k(sources, {"b"}, 1) == 0
    assert hit_at_k(sources, {"b"}, 3) == 1
    assert hit_at_k(sources, {"zz"}, 5) == 0


def test_mrr_is_reciprocal_rank():
    assert mrr(["x", "expected", "y"], {"expected"}) == 0.5
    assert mrr(["expected", "x"], {"expected"}) == 1.0
    assert mrr(["a", "b"], {"expected"}) == 0.0


def test_precision_at_k_counts_relevant_over_top_k():
    sources = ["expected", "noise", "expected", "other"]
    assert precision_at_k(sources, {"expected"}, 2) == 0.5
    assert precision_at_k(sources, {"expected"}, 4) == 0.5
    assert precision_at_k(["x", "y"], {"expected"}, 5) == 0.0


def test_evaluate_aggregates_over_queries():
    queries = [
        {"evidence_sources": ["catalog-001", "catalog-002"], "expected": {"catalog-001"}},
        {
            "evidence_sources": ["catalog-002", "catalog-001", "catalog-003"],
            "expected": {"catalog-003"},
        },
    ]
    report = evaluate(queries, k=(1, 3))
    assert report["n"] == 2
    assert report["hit_at_k"]["hit@1"] == 0.5
    assert report["hit_at_k"]["hit@3"] == 1.0
    assert round(report["mrr"], 4) == round((1.0 + 1 / 3) / 2, 4)
    assert report["per_query"][0]["rank"] == 1
    assert report["per_query"][1]["rank"] == 3
