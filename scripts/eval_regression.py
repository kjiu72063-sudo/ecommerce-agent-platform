"""Snapshot-based regression check for retrieval quality.

Runs the golden evaluation under the current config and diffs per-query ranks
against a committed snapshot, so a future change that regresses retrieval (new
recall/misrank failures, or a correct passage ranking lower) fails the check.

    python scripts/eval_regression.py --save          # (re)baseline the snapshot
    python scripts/eval_regression.py                 # compare against snapshot

Exit code 0 = no regression; 1 = one or more regressions. Built from env (same as
`presale-eval-retrieval`), so it needs the live Milvus + the configured models.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from presale.adapters.hybrid_retrieval import hybrid_retriever_from_env
from presale.adapters.retrieval_eval import evaluate_retriever, summarize_failures

SNAPSHOT_DEFAULT = "tests/fixtures/retrieval_golden_snapshot.json"


def _key(q: dict) -> str:
    return f"{q['tenant_id']}/{q['product_id']}::{q['query']}"


def _current(report: dict) -> dict[str, dict]:
    return {_key(q): {"expected": q["expected"], "rank": q["rank"]} for q in report["per_query"]}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Retrieval regression check.")
    parser.add_argument("--snapshot", default=SNAPSHOT_DEFAULT)
    parser.add_argument("--save", action="store_true", help="write current results as the baseline")
    args = parser.parse_args(argv)

    retriever = hybrid_retriever_from_env()
    if retriever is None:
        raise SystemExit("PRESALE_MILVUS_URI (and embedding/reranker models) required")
    report = evaluate_retriever(retriever)
    summary = summarize_failures(report)
    current = _current(report)

    print(
        json.dumps(
            {
                "hit@1": report["hit_at_k"]["hit@1"],
                "hit@3": report["hit_at_k"]["hit@3"],
                "mrr": report["mrr"],
                "recall_failures": summary["recall_failures"],
                "misrank_failures": summary["misrank_failures"],
            },
            ensure_ascii=False,
        )
    )

    snap_path = Path(args.snapshot)
    if args.save:
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote snapshot: {snap_path}")
        return

    if not snap_path.exists():
        raise SystemExit(f"snapshot not found: {snap_path} (run with --save first)")

    baseline = json.loads(snap_path.read_text(encoding="utf-8"))
    regressions: list[dict] = []
    improvements: list[dict] = []
    for key, row in current.items():
        old = baseline.get(key)
        new_rank = row["rank"]
        if old is None:
            regressions.append({"key": key, "reason": "new query", "rank": new_rank})
            continue
        old_rank = old["rank"]
        if old_rank is None and new_rank is not None:
            improvements.append({"key": key, "old": None, "new": new_rank})
        elif old_rank is not None and new_rank is None:
            regressions.append({"key": key, "reason": "recall lost", "old": old_rank, "new": None})
        elif old_rank is not None and new_rank is not None and new_rank > old_rank:
            regressions.append(
                {"key": key, "reason": "rank worse", "old": old_rank, "new": new_rank}
            )
        elif old_rank is not None and new_rank is not None and new_rank < old_rank:
            improvements.append({"key": key, "old": old_rank, "new": new_rank})

    for item in improvements:
        print("IMPROVED " + json.dumps(item, ensure_ascii=False))
    for item in regressions:
        print("REGRESSED " + json.dumps(item, ensure_ascii=False))
    print(f"regressions={len(regressions)} improvements={len(improvements)}")
    raise SystemExit(1 if regressions else 0)


if __name__ == "__main__":
    main()
