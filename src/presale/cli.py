"""Minimal observable V1 presale QA command-line entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import ProductQuestion
from .knowledge import KnowledgeSource
from .runner import PresaleQaResult, PresaleQaRunner


def load_catalog(path: str) -> list[KnowledgeSource]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [KnowledgeSource.model_validate(item) for item in data]


def build_runner(catalog: list[dict] | list[KnowledgeSource]) -> PresaleQaRunner:
    sources = [
        item if isinstance(item, KnowledgeSource) else KnowledgeSource.model_validate(item)
        for item in catalog
    ]
    return PresaleQaRunner(sources=sources)


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
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="presale-qa",
        description="Run a single readonly V1 presale question and print a traceable result.",
    )
    parser.add_argument("--catalog", required=True, help="Path to product knowledge JSON catalog")
    parser.add_argument("--tenant", required=True, help="Tenant id")
    parser.add_argument("--product", required=True, help="Product id")
    parser.add_argument("--question", required=True, help="Presale question text")
    parser.add_argument("--idempotency-key", required=True, help="8+ char idempotency key")
    parser.add_argument("--user-id", default="usr_cli", help="Operator user id")
    parser.add_argument("--question-id", default="question-cli", help="Question id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
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
    runner = build_runner(runner_source)
    result = runner.ask(question)
    formatted = format_result(result)
    print(json.dumps(formatted, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
