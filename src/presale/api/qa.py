"""Synchronous presale QA service entry (FastAPI).

Builds a runner from environment configuration (catalog / optional SQLite
persistence / optional external LLM & retrieval) and serves one question per
request through the Harness, returning an observable AgentOutcome.

Run with ``presale-qa-api`` (uvicorn) or ``python -m presale.api.qa``.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent_platform_contracts.models import ActorRef, ActorType
from agent_runtime.harness import Harness, TerminalDecision, format_outcome

from ..agent import PresaleAgent
from ..cli import load_catalog
from ..contracts import ProductQuestion
from ..knowledge import KnowledgeSource
from ..runner import PresaleQaRunner
from ..runtime import external_retriever_from_env, openai_generator_from_env

logger = logging.getLogger("presale.qa")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEMO_EXAMPLES = Path(__file__).resolve().parent.parent / "data" / "demo_examples.json"

app = FastAPI(
    title="Presale QA 服务",
    description="同步只读售前商品问答；env 配置 LLM/检索/持久化。",
    version="0.1.0",
)

_runner: PresaleQaRunner | None = None
_metrics: dict[str, Any] = {
    "requests": 0,
    "terminal": {decision.value: 0 for decision in TerminalDecision},
    "errors": 0,
    "last_run_seconds": None,
}


class QaRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4096)
    product_id: str = Field(min_length=1, max_length=256)
    tenant_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=512)
    question_id: str | None = None
    user_id: str = "usr_api"


def build_runner() -> PresaleQaRunner:
    catalog = os.environ.get("PRESALE_CATALOG")
    sources: list[KnowledgeSource] = load_catalog(catalog) if catalog else []
    opts: dict = {
        "sources": sources,
        "generator": openai_generator_from_env(),
        "retriever": external_retriever_from_env(),
    }
    pg_dsn = os.environ.get("PRESALE_PG_DSN")
    if pg_dsn:
        from ..adapters.postgres import (
            PostgresAnswerDraftRepository,
            PostgresDispositionRepository,
            PostgresEvidenceRepository,
            PostgresIdempotencyRepository,
            PostgresPresaleStore,
            PostgresProductQuestionRepository,
            PostgresRunTraceRepository,
        )

        store = PostgresPresaleStore(pg_dsn)
        opts.update(
            question_repo=PostgresProductQuestionRepository(store),
            evidence_repo=PostgresEvidenceRepository(store),
            answer_repo=PostgresAnswerDraftRepository(store),
            disposition_repo=PostgresDispositionRepository(store),
            trace_repo=PostgresRunTraceRepository(store),
            idempotency_repo=PostgresIdempotencyRepository(store),
        )
        opts["_pg_store"] = store
    db = os.environ.get("PRESALE_DB")
    if db and not pg_dsn:
        from ..adapters.sqlite import (
            SQLiteAnswerDraftRepository,
            SQLiteDispositionRepository,
            SQLiteEvidenceRepository,
            SQLiteIdempotencyRepository,
            SQLitePresaleStore,
            SQLiteProductQuestionRepository,
            SQLiteRunTraceRepository,
        )

        store = SQLitePresaleStore(db)
        opts.update(
            question_repo=SQLiteProductQuestionRepository(store),
            evidence_repo=SQLiteEvidenceRepository(store),
            answer_repo=SQLiteAnswerDraftRepository(store),
            disposition_repo=SQLiteDispositionRepository(store),
            trace_repo=SQLiteRunTraceRepository(store),
            idempotency_repo=SQLiteIdempotencyRepository(store),
        )
    opts.pop("_pg_store", None)
    return PresaleQaRunner(**{key: value for key, value in opts.items() if value is not None})


def reset_qa_runner() -> None:
    """Drop the cached runner and metrics so the next request rebuilds (tests)."""
    global _runner
    _runner = None
    _metrics["requests"] = 0
    _metrics["terminal"] = {decision.value: 0 for decision in TerminalDecision}
    _metrics["errors"] = 0
    _metrics["last_run_seconds"] = None


def get_runner() -> PresaleQaRunner:
    global _runner
    if _runner is None:
        _runner = build_runner()
    return _runner


@app.get("/api/v1/presale/qa/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/api/v1/presale/qa/ready")
async def ready() -> dict[str, str]:
    """Readiness probe. PostgreSQL is checked only when PRESALE_PG_DSN is set."""
    dsn = os.environ.get("PRESALE_PG_DSN")
    if not dsn:
        return {"status": "ready", "persistence": "default"}
    try:
        import asyncpg  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="asyncpg is not installed") from exc
    try:
        conn = await asyncpg.connect(dsn, timeout=3)
    except Exception as exc:
        logger.warning("postgres readiness failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="postgres unavailable") from exc
    try:
        await conn.execute("SELECT 1")
    finally:
        await conn.close()
    return {"status": "ready", "persistence": "postgres"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Demo single-page UI (static HTML, same origin as the API)."""
    return FileResponse(_STATIC_DIR / "index.html")


@app.get("/api/v1/presale/qa/examples", include_in_schema=False)
def examples() -> dict[str, Any]:
    """Curated demo questions per product (drives the UI's product picker)."""
    try:
        return json.loads(_DEMO_EXAMPLES.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="demo examples unavailable") from exc


@app.get("/api/v1/presale/qa/metrics")
def metrics() -> dict[str, object]:
    return dict(_metrics)


@app.post("/api/v1/presale/qa")
async def qa(req: QaRequest) -> dict:
    question = ProductQuestion(
        question_id=req.question_id or f"q-{req.idempotency_key}",
        tenant_id=req.tenant_id,
        submitted_by=ActorRef(actor_type=ActorType.USER, actor_id=req.user_id),
        product_id=req.product_id,
        question_text=req.question,
        requested_at=datetime.now(timezone.utc),
        idempotency_key=req.idempotency_key,
    )
    start = time.monotonic()
    _metrics["requests"] = int(_metrics["requests"]) + 1
    try:
        outcome = await Harness().execute(question, PresaleAgent(get_runner()))
    except Exception as exc:  # surface cleanly; never leak internals
        _metrics["errors"] = int(_metrics["errors"]) + 1
        _metrics["last_run_seconds"] = time.monotonic() - start
        logger.exception("qa run failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"QA run failed: {type(exc).__name__}")
    terminal = outcome.terminal.value
    _metrics["terminal"][terminal] = int(_metrics["terminal"][terminal]) + 1
    _metrics["last_run_seconds"] = time.monotonic() - start
    logger.info("qa ok run_ref=%s terminal=%s", outcome.run_ref, terminal)
    payload = format_outcome(outcome)
    draft = outcome.answer_draft
    payload["evidence"] = [
        {"locator": ref.locator, "source_id": ref.source_id}
        for ref in (draft.evidence_refs if draft else [])
    ]
    payload["confidence_signal"] = draft.confidence_signal if draft else None
    payload["reason_codes"] = list(draft.reason_codes) if draft else []
    return payload


def main() -> None:
    import uvicorn

    host = os.environ.get("PRESALE_QA_HOST", "127.0.0.1")
    port = int(os.environ.get("PRESALE_QA_PORT", "8000"))
    uvicorn.run("presale.api.qa:app", host=host, port=port)


__all__ = ["app", "build_runner", "get_runner", "main", "reset_qa_runner"]
