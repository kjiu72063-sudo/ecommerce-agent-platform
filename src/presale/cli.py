"""Minimal observable V1 presale QA command-line entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .contracts import ProductQuestion
from .knowledge import KnowledgeSource
from .maintenance import archive_expired_sqlite
from .runner import PresaleQaResult, PresaleQaRunner, QaRuntimeError
from .trace import PresaleRunTrace, TraceError


def load_catalog(path: str) -> list[KnowledgeSource]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [KnowledgeSource.model_validate(item) for item in data]


def build_runner(
    catalog: list[dict] | list[KnowledgeSource], *, token_budget: int = 1000
) -> PresaleQaRunner:
    sources = [
        item if isinstance(item, KnowledgeSource) else KnowledgeSource.model_validate(item)
        for item in catalog
    ]
    return PresaleQaRunner(sources=sources, context_budget_tokens=token_budget)


def format_result(result: PresaleQaResult) -> dict[str, Any]:
    draft = result.answer_draft
    evidence = [
        f"{item.source_id}@{item.source_version}#{item.locator}" for item in draft.evidence_refs
    ]
    return {
        "run_ref": result.run_ref,
        "question_id": draft.question_id,
        "answer": draft.answer_text,
        "evidence": evidence,
        "confidence": draft.confidence_signal,
        "need_human": draft.need_human,
        "reason_codes": list(draft.reason_codes),
        "context_package_ref": result.trace.context_package_ref,
        "disposition_state": str(result.trace.disposition_state),
    }


def save_trace(path: str, trace: PresaleRunTrace) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    traces = {}
    if Path(path).exists():
        traces = json.loads(Path(path).read_text(encoding="utf-8"))
    traces[trace.run_ref] = trace.model_dump(mode="json")
    Path(path).write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")


def load_trace(path: str, *, run_ref: str, tenant_id: str) -> PresaleRunTrace:
    traces = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = traces.get(run_ref)
    if raw is None:
        raise TraceError("TRACE_NOT_FOUND")
    if raw.get("tenant_id") != tenant_id:
        raise TraceError("OUT_OF_SCOPE")
    return PresaleRunTrace.model_validate(raw)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="presale-qa",
        description="Run a single readonly V1 presale question or query a saved run trace.",
    )
    parser.add_argument("--catalog", help="Path to product knowledge JSON catalog")
    parser.add_argument("--tenant", required=True, help="Tenant id")
    parser.add_argument("--product", help="Product id")
    parser.add_argument("--question", help="Presale question text")
    parser.add_argument("--idempotency-key", help="8+ char idempotency key")
    parser.add_argument("--user-id", default="usr_cli", help="Operator user id")
    parser.add_argument("--question-id", default="question-cli", help="Question id")
    parser.add_argument("--token-budget", type=int, default=1000, help="Context token budget")
    parser.add_argument("--save-trace", help="Path to append the run trace as JSON")
    parser.add_argument("--trace-file", help="Path to a saved trace file to query")
    parser.add_argument("--trace-run-ref", help="run ref to query from --trace-file")
    parser.add_argument("--db", help="SQLite database path for the retention archive")
    parser.add_argument(
        "--archive-expired",
        action="store_true",
        help="Run the 30-day retention archive against --db for --tenant",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    runner_source = load_catalog(args.catalog)
    question = ProductQuestion(
        question_id=args.question_id,
        tenant_id=args.tenant,
        submitted_by={"actor_type": "user", "actor_id": args.user_id},
        product_id=args.product,
        question_text=args.question,
        requested_at=datetime.now(timezone.utc),
        idempotency_key=args.idempotency_key,
    )
    runner = build_runner(runner_source, token_budget=args.token_budget)
    result = await runner.ask(question)
    if args.save_trace:
        save_trace(args.save_trace, result.trace)
    return format_result(result)


def _query(args: argparse.Namespace) -> dict[str, Any]:
    trace = load_trace(args.trace_file, run_ref=args.trace_run_ref, tenant_id=args.tenant)
    return trace.model_dump(mode="json")


async def _retention_archive(args: argparse.Namespace) -> dict[str, Any]:
    if not args.db:
        raise SystemExit("--archive-expired requires --db")
    archived = await archive_expired_sqlite(database=args.db, tenant_id=args.tenant)
    return {"archived": archived}


async def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.archive_expired:
        return await _retention_archive(args)
    if args.db:
        # --db is only meaningful for the retention archive; silently ignoring it
        # in a QA run would mislead an operator into thinking persistence is on.
        raise SystemExit("--db is only used with --archive-expired")
    if args.trace_file:
        return _query(args)
    missing = [
        name
        for name, value in {
            "--catalog": args.catalog,
            "--product": args.product,
            "--question": args.question,
            "--idempotency-key": args.idempotency_key,
        }.items()
        if not value
    ]
    if missing:
        raise SystemExit("missing required run arguments: " + ", ".join(missing))
    return await _run(args)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        output = asyncio.run(_dispatch(args))
    except (ValidationError, TraceError, QaRuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
