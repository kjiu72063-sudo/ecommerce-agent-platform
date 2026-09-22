"""Unified evaluation entry (`presale-eval`) for the presale slice.

Orchestrates the existing single-ring evaluators (retrieval_eval /
generation_eval) behind one CLI:

    presale-eval --mode retrieval|generation|end-to-end|all [--compare A B] [--output f.json]

Reuses the existing evaluators and assembly helpers; this module only selects,
runs, compares and reports. No new evaluation metrics are introduced.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .retrieval_eval import evaluate_retriever

MODES = ("retrieval", "generation", "end-to-end", "all")


def build_retriever():
    """Build a hybrid retriever from env, or None when unconfigured."""
    from .hybrid_retrieval import hybrid_retriever_from_env

    return hybrid_retriever_from_env()


def run_retrieval(
    retriever, *, k: tuple[int, ...] | None = None, to_questions=None
) -> dict[str, Any]:
    """Run retrieval evaluation over the golden set and return the report."""
    if k is None:
        return evaluate_retriever(retriever, to_questions=to_questions)
    return evaluate_retriever(retriever, k=k, to_questions=to_questions)


def run_generation(
    retriever,
    *,
    transport,
    base_url: str,
    model: str,
    api_key: str,
    sever_evidence: bool = False,
) -> dict[str, Any]:
    """Run generation faithfulness evaluation and return the report."""
    from .generation_eval import evaluate_generation

    return evaluate_generation(
        retriever,
        transport=transport,
        base_url=base_url,
        model=model,
        api_key=api_key,
        sever_evidence=sever_evidence,
    )


def run_end_to_end(
    retriever,
    *,
    sources: list[Any],
    generator,
    transport,
    base_url: str,
    model: str,
    api_key: str,
    sever_evidence: bool = False,
) -> dict[str, Any]:
    """Run the golden through the real PresaleQaRunner and return the report."""
    from .generation_eval import evaluate_end_to_end

    return evaluate_end_to_end(
        retriever,
        sources=sources,
        generator=generator,
        transport=transport,
        base_url=base_url,
        model=model,
        api_key=api_key,
        sever_evidence=sever_evidence,
    )


def summarize(mode: str, report: dict[str, Any]) -> str:
    """Render a compact text summary of an evaluation report."""
    if mode in ("generation", "end-to-end"):
        return (
            f"{mode}: n={report.get('n')} "
            f"faithfulness={report.get('mean_faithfulness')} "
            f"correctness={report.get('mean_answer_correctness')} "
            f"gold_correctness={report.get('mean_gold_correctness')} "
            f"unsupported={report.get('total_unsupported_claims')}"
        )
    hit = report.get("hit_at_k", {})
    return (
        f"retrieval: hit@1={hit.get('hit@1')} hit@3={hit.get('hit@3')} "
        f"mrr={report.get('mrr')} precision@5={report.get('precision@5')}"
    )


def _llm_config() -> tuple[str | None, str | None, str | None]:
    return (
        os.environ.get("PRESALE_LLM_BASE_URL"),
        os.environ.get("PRESALE_LLM_MODEL"),
        os.environ.get("PRESALE_LLM_API_KEY"),
    )


def _load_catalog() -> list[Any]:
    from ..cli import load_catalog

    return load_catalog(os.environ.get("PRESALE_CATALOG", "src/presale/data/dev_catalog.json"))


def _build_generator():
    """Build OpenAI generator from env, or None when unconfigured."""
    base_url, model, api_key = _llm_config()
    if not (base_url and model and api_key):
        return None
    from .openai_generator import OpenAICompatibleGenerator

    return OpenAICompatibleGenerator(model=model, base_url=base_url, api_key=api_key)


def _run_mode(mode: str, args: argparse.Namespace) -> dict[str, Any]:
    """Run one mode and return its report (plus mode tag)."""
    retriever = build_retriever()
    if retriever is None:
        raise SystemExit("PRESALE_MILVUS_URI (or PRESALE_QDRANT_URL) required for evaluation")

    if mode == "retrieval":
        return {"mode": mode, **run_retrieval(retriever)}

    base_url, model, api_key = _llm_config()
    if not (base_url and model and api_key):
        raise SystemExit(
            f"PRESALE_LLM_BASE_URL/PRESALE_LLM_MODEL/PRESALE_LLM_API_KEY required for mode '{mode}'"
        )
    transport = None
    from .openai_generator import default_transport

    transport = default_transport

    if mode == "generation":
        report = run_generation(
            retriever, transport=transport, base_url=base_url, model=model, api_key=api_key
        )
        return {"mode": mode, **report}

    # end-to-end
    generator = _build_generator()
    if generator is None:
        raise SystemExit("PRESALE_LLM_* required to build generator for end-to-end")
    report = run_end_to_end(
        retriever,
        sources=_load_catalog(),
        generator=generator,
        transport=transport,
        base_url=base_url,
        model=model,
        api_key=api_key,
    )
    return {"mode": mode, **report}


def compare_reports(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Diff two evaluation reports per-query and return regressed/improved lists.

    Both reports must contain a ``per_question`` list; each row must have a
    ``query`` key. Rows may carry ``rank`` (retrieval) or ``error``/metric
    fields (generation/end-to-end).
    """
    aq = {q["query"]: q for q in a.get("per_question", [])}
    bq = {q["query"]: q for q in b.get("per_question", [])}
    regressed: list[dict[str, Any]] = []
    improved: list[dict[str, Any]] = []
    added: list[str] = []
    for key, row_b in bq.items():
        row_a = aq.get(key)
        if row_a is None:
            added.append(key)
            continue
        if "rank" in row_a and "rank" in row_b:
            if row_b["rank"] is None and row_a["rank"] is not None:
                # recall lost: ranked before, now not found
                regressed.append({"query": key, "old": row_a["rank"], "new": None})
            elif row_a["rank"] is None and row_b["rank"] is not None:
                # recall restored: not found before, now ranked
                improved.append({"query": key, "old": None, "new": row_b["rank"]})
            elif row_b["rank"] is not None and row_b["rank"] > row_a["rank"]:
                regressed.append({"query": key, "old": row_a["rank"], "new": row_b["rank"]})
            elif row_b["rank"] is not None and row_b["rank"] < row_a["rank"]:
                improved.append({"query": key, "old": row_a["rank"], "new": row_b["rank"]})
        elif "error" in row_a and "error" not in row_b:
            improved.append({"query": key, "old": "error", "new": "ok"})
        elif "error" not in row_a and "error" in row_b:
            regressed.append({"query": key, "old": "ok", "new": "error"})
    removed = [key for key in aq if key not in bq]
    return {
        "regressed": regressed,
        "improved": improved,
        "added": added,
        "removed": removed,
        "summary": {"regressed": len(regressed), "improved": len(improved)},
    }


def write_report(report: dict[str, Any], path: str) -> None:
    """Persist an evaluation report as JSON, creating parent directories."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="presale-eval",
        description="Run presale QA evaluation (retrieval / generation / end-to-end / all).",
    )
    parser.add_argument(
        "--mode",
        choices=list(MODES),
        default="all",
        help="which evaluation ring to run (default: all)",
    )
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two result JSONs")
    parser.add_argument("--output", metavar="FILE", help="write the report JSON to FILE")
    args = parser.parse_args(argv)

    # --compare is offline: read two result files and diff them.
    if args.compare:
        a_path, b_path = args.compare
        try:
            a = json.loads(Path(a_path).read_text(encoding="utf-8"))
            b = json.loads(Path(b_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot read compare file: {exc}") from exc
        result = compare_reports(a, b)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.mode == "all":
        reports = [_run_mode("retrieval", args)]
        base_url, model, api_key = _llm_config()
        if base_url and model and api_key:
            reports.append(_run_mode("end-to-end", args))
        else:
            print("SKIPPED generation/end-to-end: PRESALE_LLM_* not configured", file=sys.stderr)
        combined = {"modes": reports}
    else:
        combined = _run_mode(args.mode, args)

    if args.output:
        write_report(combined, args.output)
        print(f"wrote report: {args.output}")

    if args.mode == "all":
        for report in reports:
            print(
                json.dumps(
                    {k: v for k, v in report.items() if k != "per_question"}, ensure_ascii=False
                )
            )
            print(summarize(report["mode"], report))
    else:
        printable = {k: v for k, v in combined.items() if k != "per_question"}
        print(json.dumps(printable, ensure_ascii=False))
        print(summarize(args.mode, combined))
    return 0


__all__ = [
    "MODES",
    "build_retriever",
    "compare_reports",
    "main",
    "run_end_to_end",
    "run_generation",
    "run_retrieval",
    "summarize",
    "write_report",
]
