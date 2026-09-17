"""Synchronous presale QA service entry (FastAPI).

Builds a runner from environment configuration (catalog / optional SQLite
persistence / optional external LLM & retrieval) and serves one question per
request through the Harness, returning an observable AgentOutcome.

Run with ``presale-qa-api`` (uvicorn) or ``python -m presale.api.qa``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent_platform_contracts.models import ActorRef, ActorType
from agent_runtime.harness import Harness, format_outcome

from ..agent import PresaleAgent
from ..cli import load_catalog
from ..contracts import ProductQuestion
from ..knowledge import KnowledgeSource
from ..runner import PresaleQaRunner
from ..runtime import external_retriever_from_env, openai_generator_from_env

app = FastAPI(
    title="Presale QA 服务",
    description="同步只读售前商品问答；env 配置 LLM/检索/持久化。",
    version="0.1.0",
)

_runner: PresaleQaRunner | None = None


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
    db = os.environ.get("PRESALE_DB")
    if db:
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
    return PresaleQaRunner(**{key: value for key, value in opts.items() if value is not None})


def reset_qa_runner() -> None:
    """Drop the cached runner so the next request rebuilds it (used by tests)."""
    global _runner
    _runner = None


def get_runner() -> PresaleQaRunner:
    global _runner
    if _runner is None:
        _runner = build_runner()
    return _runner


@app.get("/api/v1/presale/qa/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


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
    try:
        outcome = await Harness().execute(question, PresaleAgent(get_runner()))
    except Exception as exc:  # surface cleanly; never leak internals
        raise HTTPException(status_code=502, detail=f"QA run failed: {type(exc).__name__}")
    return format_outcome(outcome)


def main() -> None:
    import uvicorn

    host = os.environ.get("PRESALE_QA_HOST", "127.0.0.1")
    port = int(os.environ.get("PRESALE_QA_PORT", "8000"))
    uvicorn.run("presale.api.qa:app", host=host, port=port)


__all__ = ["app", "build_runner", "get_runner", "main", "reset_qa_runner"]
