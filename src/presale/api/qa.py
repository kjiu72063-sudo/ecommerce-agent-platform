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
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent_platform_contracts.models import ActorRef, ActorType, ObjectRef, ResourceKind
from agent_runtime.harness import Harness, TerminalDecision, format_outcome

from ..adapters.openai_generator import build_stream_prompt, stream_completion
from ..agent import PresaleAgent
from ..answer import PresaleAnswerGenerator
from ..cli import load_catalog
from ..contracts import AnswerDraft, EvidenceRef, ProductQuestion
from ..knowledge import KnowledgeSource, RetrievalStatus
from ..runner import PresaleQaRunner
from ..runtime import external_retriever_from_env, openai_generator_from_env

logger = logging.getLogger("presale.qa")

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_DEMO_EXAMPLES = Path(__file__).resolve().parent.parent / "data" / "demo_examples.json"
_DEMO_CURATED = Path(__file__).resolve().parent.parent / "data" / "demo_curated.json"
_HISTORY_LIMIT = 50

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
# Demo-scoped in-memory state (cleared with reset_qa_runner; not persisted).
_history: deque[dict[str, Any]] = deque(maxlen=_HISTORY_LIMIT)
_feedback: dict[str, dict[str, Any]] = {}
# session_id -> {"turns": [{"question", "answer"}, ...]} for multi-turn prompts.
_sessions: dict[str, dict[str, Any]] = {}
_SESSION_LIMIT = 100
_SESSION_TURNS = 3


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
    _history.clear()
    _feedback.clear()
    _sessions.clear()


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


@app.get("/api/v1/presale/qa/config", include_in_schema=False)
def config() -> dict[str, Any]:
    """Effective demo mode (real LLM vs template; retrieval backend)."""
    llm_ready = all(
        os.environ.get(key)
        for key in ("PRESALE_LLM_BASE_URL", "PRESALE_LLM_MODEL", "PRESALE_LLM_API_KEY")
    )
    if os.environ.get("PRESALE_MILVUS_URI"):
        retrieval = "hybrid"
    elif os.environ.get("PRESALE_QDRANT_URL"):
        retrieval = "qdrant"
    elif os.environ.get("PRESALE_RETRIEVAL_BASE_URL"):
        retrieval = "external"
    else:
        retrieval = "deterministic"
    return {
        "llm": "real" if llm_ready else "template",
        "model": os.environ.get("PRESALE_LLM_MODEL") if llm_ready else None,
        "retrieval": retrieval,
    }


@app.get("/api/v1/presale/qa/history", include_in_schema=False)
def history(limit: int = 20) -> dict[str, Any]:
    """Recent QA runs (newest first, in-memory demo state)."""
    bounded = max(1, min(limit, _HISTORY_LIMIT))
    return {"items": list(_history)[:bounded]}


class FeedbackRequest(BaseModel):
    run_ref: str = Field(min_length=1, max_length=256)
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1024)


@app.post("/api/v1/presale/qa/feedback", include_in_schema=False)
def feedback(req: FeedbackRequest) -> dict[str, Any]:
    """Record a thumbs up/down for a run (in-memory demo state)."""
    _feedback[req.run_ref] = {
        "run_ref": req.run_ref,
        "rating": req.rating,
        "comment": req.comment,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"status": "recorded", "rating": req.rating}


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
    elapsed = time.monotonic() - start
    _metrics["last_run_seconds"] = elapsed
    logger.info("qa ok run_ref=%s terminal=%s", outcome.run_ref, terminal)
    payload = format_outcome(outcome)
    draft = outcome.answer_draft
    retrieve_call = next(
        (
            call
            for step in outcome.steps
            for call in step.tool_calls
            if isinstance(call, dict) and call.get("tool") == "retrieve"
        ),
        None,
    )
    tool_evidence = retrieve_call.get("evidence") if retrieve_call else None
    if tool_evidence is not None:
        payload["evidence"] = tool_evidence
    else:
        payload["evidence"] = [
            {"locator": ref.locator, "source_id": ref.source_id, "content": None}
            for ref in (draft.evidence_refs if draft else [])
        ]
    payload["confidence_signal"] = draft.confidence_signal if draft else None
    payload["reason_codes"] = list(draft.reason_codes) if draft else []
    trace = getattr(outcome, "trace", None)
    payload["timeline"] = [
        {
            "stage": record.stage.value,
            "detail": record.detail,
            "occurred_at": record.occurred_at.isoformat(),
        }
        for record in (trace.stages if trace else [])
    ]
    payload["disposition"] = trace.disposition_state.value if trace else None
    payload["configuration_refs"] = dict(trace.configuration_refs) if trace else {}
    _record_history(req.question, req.product_id, payload, elapsed)
    return payload


def _record_history(
    question: str, product_id: str, payload: dict[str, Any], elapsed: float
) -> None:
    run_ref = payload.get("run_ref")
    run_id = run_ref if isinstance(run_ref, str) else str(run_ref)
    _history.appendleft(
        {
            "id": run_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "product_id": product_id,
            "terminal": payload.get("terminal"),
            "need_human": payload.get("need_human"),
            "evidence_count": len(payload.get("evidence") or []),
            "seconds": round(elapsed, 3),
            "answer_preview": (payload.get("answer_text") or "")[:160],
            "response": payload,
        }
    )


class StreamRequest(QaRequest):
    session_id: str | None = Field(default=None, max_length=64)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _new_run_id() -> str:
    """UUIDv7-shaped run id matching the ObjectRef contract pattern."""
    import uuid

    value = uuid.uuid4().int
    value = (value & ~(0xF << 76)) | (0x7 << 76)
    value = (value & ~(0x3 << 62)) | (0x2 << 62)
    return f"run_{uuid.UUID(int=value)}"


def _curated_answer(question_text: str, product_id: str) -> str | None:
    """Pre-approved demo answer for a curated question (exact trimmed match)."""
    try:
        data = json.loads(_DEMO_CURATED.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    wanted = question_text.strip()
    for item in data.get("items", []):
        if item.get("question", "").strip() == wanted and item.get("product_id") == product_id:
            answer = item.get("answer_text")
            if answer:
                return str(answer)
    return None


def _sentence_chunks(text: str):
    """Split text into sentence-sized token chunks for the typewriter effect."""
    buf = ""
    for ch in text:
        buf += ch
        if ch in "。！？\n":
            yield buf
            buf = ""
    if buf:
        yield buf


def _stream_draft(question: ProductQuestion, retrieval, run_id: str, text: str) -> AnswerDraft:
    """Assemble an AnswerDraft from streamed LLM text (mirrors generator rules)."""
    evidence_refs = [
        EvidenceRef(
            source_id=item.source_id,
            source_version=item.source_version,
            locator=item.locator,
            content_digest=item.content_digest,
        )
        for item in retrieval.evidence_items
    ]
    if retrieval.status is RetrievalStatus.NO_EVIDENCE:
        need_human, confidence, reason = True, "unavailable", ["NO_EVIDENCE"]
    elif retrieval.status is RetrievalStatus.CONFLICT:
        need_human, confidence, reason = True, "conflicting", ["CONFLICTING_EVIDENCE"]
    else:
        need_human, confidence, reason = False, "supported", []
    return AnswerDraft(
        answer_id=f"answer-{run_id}",
        question_id=question.question_id,
        run_ref=ObjectRef(kind=ResourceKind.AGENT_RUN, id=run_id),
        answer_text=text,
        evidence_refs=evidence_refs,
        confidence_signal=confidence,
        need_human=need_human,
        reason_codes=reason,
        configuration_refs={},
        generated_at=datetime.now(timezone.utc),
    )


@app.post("/api/v1/presale/qa/stream", include_in_schema=False)
def qa_stream(req: StreamRequest) -> StreamingResponse:
    """SSE answer stream: evidence event → token deltas → done payload.

    Uses the shared runner retriever; streams real LLM deltas when
    ``PRESALE_LLM_*`` is configured, otherwise falls back to the
    deterministic generator split into sentence-sized tokens. Carries the
    last ``session_id`` turns into the prompt for follow-up questions.
    """
    question = ProductQuestion(
        question_id=req.question_id or f"q-{req.idempotency_key}",
        tenant_id=req.tenant_id,
        submitted_by=ActorRef(actor_type=ActorType.USER, actor_id=req.user_id),
        product_id=req.product_id,
        question_text=req.question,
        requested_at=datetime.now(timezone.utc),
        idempotency_key=req.idempotency_key,
    )
    session_id = req.session_id or f"sess-{time.monotonic_ns()}"
    history_turns = list(_sessions.get(session_id, {}).get("turns", []))[-_SESSION_TURNS:]
    start = time.monotonic()
    _metrics["requests"] = int(_metrics["requests"]) + 1

    def generate():
        runner = get_runner()
        try:
            retrieval = runner.retriever.retrieve(question)
        except Exception as exc:
            _metrics["errors"] = int(_metrics["errors"]) + 1
            logger.exception("stream retrieval failed: %s", type(exc).__name__)
            yield _sse("error", {"detail": f"retrieval failed: {type(exc).__name__}"})
            return
        evidence = [
            {
                "locator": item.locator,
                "source_id": item.source_id,
                "content": item.content[:120],
            }
            for item in retrieval.evidence_items
        ]
        yield _sse(
            "evidence",
            {"retrieval_status": retrieval.status.value, "evidence": evidence},
        )

        run_id = _new_run_id()
        run_ref = {"kind": "AgentRun", "id": run_id}
        timeline: list[dict[str, Any]] = [
            {
                "stage": "submitted",
                "detail": question.question_id,
                "occurred_at": question.requested_at.isoformat(),
            },
            {
                "stage": "knowledge_retrieved",
                "detail": retrieval.status.value,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "stage": "context_built",
                "detail": f"{len(evidence)} evidence items (stream pipeline)",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        full_text = ""
        curated_text = _curated_answer(question.question_text, question.product_id)
        if curated_text:
            # Demo curation: stream the pre-approved archive answer (retrieval
            # above is still live, so evidence and timeline stay real).
            full_text = curated_text
            for piece in _sentence_chunks(full_text):
                yield _sse("token", {"text": piece})
        generator = None if curated_text else openai_generator_from_env()
        if generator is not None:
            import os as _os

            prompt = build_stream_prompt(question, retrieval, {}, history=history_turns)
            parts: list[str] = []
            try:
                for delta in stream_completion(
                    api_key=_os.environ.get("PRESALE_LLM_API_KEY", ""),
                    base_url=_os.environ.get("PRESALE_LLM_BASE_URL", ""),
                    model=_os.environ.get("PRESALE_LLM_MODEL", ""),
                    messages=[{"role": "user", "content": prompt}],
                    timeout_s=90.0,
                ):
                    parts.append(delta)
                    yield _sse("token", {"text": delta})
                full_text = "".join(parts).strip()
            except Exception as exc:
                logger.warning("stream LLM failed, degrading: %s", type(exc).__name__)
                full_text = ""
        if not full_text:
            draft = PresaleAnswerGenerator().generate(
                question, retrieval, run_ref=run_ref, configuration_refs={}
            )
            full_text = draft.answer_text
            for piece in _sentence_chunks(full_text):
                yield _sse("token", {"text": piece})

        draft = _stream_draft(question, retrieval, run_id, full_text)
        escalate, reason = PresaleQaRunner._escalation(retrieval, 1)
        if escalate and not draft.need_human:
            draft = draft.model_copy(
                update={
                    "need_human": True,
                    "reason_codes": [*draft.reason_codes, reason],
                }
            )
        need_human = draft.need_human
        timeline.append(
            {
                "stage": "answer_generated",
                "detail": draft.answer_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        payload: dict[str, Any] = {
            "run_ref": run_id,
            "terminal": "need_human" if need_human else "finalize",
            "answer_text": full_text,
            "answer_id": draft.answer_id,
            "need_human": need_human,
            "evidence": evidence,
            "confidence_signal": draft.confidence_signal,
            "reason_codes": list(draft.reason_codes),
            "curated": bool(curated_text),
            "timeline": timeline,
            "disposition": "pending",
            "configuration_refs": {},
            "steps": [
                {
                    "index": 0,
                    "need_human": need_human,
                    "tool_calls": [
                        {
                            "tool": "retrieve",
                            "tenant_id": question.tenant_id,
                            "product_id": question.product_id,
                            "status": retrieval.status.value,
                            "evidence_count": len(evidence),
                            "reason_codes": list(retrieval.reason_codes),
                            "evidence": evidence,
                        }
                    ],
                }
            ],
            "session_id": session_id,
        }
        elapsed = time.monotonic() - start
        _metrics["last_run_seconds"] = elapsed
        terminal = payload["terminal"]
        _metrics["terminal"][terminal] = int(_metrics["terminal"].get(terminal, 0)) + 1
        _record_history(req.question, req.product_id, payload, elapsed)
        turns = [*history_turns, {"question": req.question, "answer": full_text}][-_SESSION_TURNS:]
        if session_id in _sessions:
            del _sessions[session_id]
        _sessions[session_id] = {"turns": turns}
        while len(_sessions) > _SESSION_LIMIT:
            del _sessions[next(iter(_sessions))]
        yield _sse("done", payload)

    return StreamingResponse(generate(), media_type="text/event-stream")


class ReviewRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)
    product_id: str | None = Field(default=None, max_length=256)


@app.post("/api/v1/review/analyze", include_in_schema=False)
async def review_analyze(req: ReviewRequest) -> dict[str, Any]:
    """Second business agent: deterministic review sentiment + keywords."""
    from review_agent.agent import ReviewAnalyzerAgent

    catalog = os.environ.get("PRESALE_CATALOG")
    sources = load_catalog(catalog) if catalog else []
    agent = ReviewAnalyzerAgent(sources=sources)
    try:
        if req.product_id:
            question = ProductQuestion(
                question_id=f"q-review-{time.monotonic_ns()}",
                tenant_id="tenant-demo",
                submitted_by=ActorRef(actor_type=ActorType.USER, actor_id="usr_review"),
                product_id=req.product_id,
                question_text=req.text,
                requested_at=datetime.now(timezone.utc),
                idempotency_key=f"review-{time.monotonic_ns()}",
            )
            outcome = await Harness().execute(question, agent)
        else:
            outcome = await Harness().execute(req.text, agent)
    except Exception as exc:
        logger.exception("review analyze failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail=f"Review run failed: {type(exc).__name__}"
        ) from exc
    payload = format_outcome(outcome)
    analyze_call = next(
        (
            call
            for step in outcome.steps
            for call in step.tool_calls
            if isinstance(call, dict) and call.get("tool") == "analyze_review"
        ),
        None,
    )
    payload["sentiment"] = analyze_call.get("sentiment") if analyze_call else None
    payload["keywords"] = list(analyze_call.get("keywords") or []) if analyze_call else []
    retrieve_call = next(
        (
            call
            for step in outcome.steps
            for call in step.tool_calls
            if isinstance(call, dict) and call.get("tool") == "retrieve_knowledge"
        ),
        None,
    )
    payload["evidence_count"] = int(retrieve_call.get("evidence_count", 0)) if retrieve_call else 0
    return payload


class CoordinatorRequest(QaRequest):
    pass


@app.post("/api/v1/coordinator/run", include_in_schema=False)
async def coordinator_run(req: CoordinatorRequest) -> dict[str, Any]:
    """Multi-agent pipeline demo: Presale QA → ReviewAnalyzer via AgentCoordinator.

    Sequential hand-off (previous answer becomes the next agent's input);
    the first NEED_HUMAN short-circuits the rest — Review always ends in
    human review per the AnswerDraft evidence contract.
    """
    from agent_runtime.coordinator import AgentCoordinator, format_coordinator_outcome
    from review_agent.agent import ReviewAnalyzerAgent

    question = ProductQuestion(
        question_id=req.question_id or f"q-{req.idempotency_key}",
        tenant_id=req.tenant_id,
        submitted_by=ActorRef(actor_type=ActorType.USER, actor_id=req.user_id),
        product_id=req.product_id,
        question_text=req.question,
        requested_at=datetime.now(timezone.utc),
        idempotency_key=req.idempotency_key,
    )
    catalog = os.environ.get("PRESALE_CATALOG")
    sources = load_catalog(catalog) if catalog else []
    start = time.monotonic()
    try:
        outcome = await AgentCoordinator(
            [PresaleAgent(get_runner()), ReviewAnalyzerAgent(sources=sources)]
        ).execute(question)
    except Exception as exc:
        _metrics["errors"] = int(_metrics["errors"]) + 1
        logger.exception("coordinator run failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502, detail=f"Coordinator run failed: {type(exc).__name__}"
        ) from exc
    payload = format_coordinator_outcome(outcome)
    payload["agents"] = ["presale-qa", "review-analyzer"]
    payload["pipeline"] = [
        {
            "agent": name,
            "terminal": sub.terminal.value,
            "need_human": bool(sub.answer_draft and sub.answer_draft.need_human),
            "answer_preview": ((sub.answer_draft.answer_text if sub.answer_draft else "") or "")[
                :160
            ],
        }
        for name, sub in zip(payload["agents"], outcome.sub_outcomes, strict=False)
    ]
    payload["short_circuited"] = len(outcome.sub_outcomes) < 2
    payload["seconds"] = round(time.monotonic() - start, 3)
    return payload


def main() -> None:
    import uvicorn

    host = os.environ.get("PRESALE_QA_HOST", "127.0.0.1")
    port = int(os.environ.get("PRESALE_QA_PORT", "8000"))
    uvicorn.run("presale.api.qa:app", host=host, port=port)


__all__ = ["app", "build_runner", "get_runner", "main", "reset_qa_runner"]
