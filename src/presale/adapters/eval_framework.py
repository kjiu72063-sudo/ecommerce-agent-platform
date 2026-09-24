"""Unified evaluation entry (`presale-eval`) for the presale slice.

Orchestrates the existing single-ring evaluators (retrieval_eval /
generation_eval) behind one CLI:

    presale-eval --mode retrieval|generation|end-to-end|review|multi-agent \
        |live-clipper|content-creator|all [--compare A B] [--output f.json|.md] \
        [--inputs g1.json g2.json ...] [--csv summary.csv] \
        [--compare-batch base:curr ...]

Reuses the existing evaluators and assembly helpers; this module only selects,
runs, compares and reports. Review, multi-agent, live-clipper and content-creator
modes are fully offline (deterministic agents — no Milvus / LLM / real ASR /
image API required). ``--inputs`` batches one mode over multiple golden JSON
files and writes a one-row-per-file summary CSV; ``--compare-batch`` runs
golden regression over multiple baseline:current pairs.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_platform_contracts.models import ActorRef, ActorType

from .retrieval_eval import evaluate_retriever

MODES = (
    "retrieval",
    "generation",
    "end-to-end",
    "review",
    "multi-agent",
    "live-clipper",
    "content-creator",
    "all",
)

# Bump when a golden set's items or expected labels change (catalog-driven updates).
GENERATION_GOLDEN_VERSION = "1.0.0"
REVIEW_GOLDEN_VERSION = "1.0.0"


def _file_sha256_prefix(path: Path, length: int = 16) -> str | None:
    if not path.is_file():
        return None
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()[:length]


def golden_meta(mode: str | None = None) -> dict[str, Any]:
    """Version + catalog fingerprint stamped into evaluation reports and snapshots.

    When the catalog or golden items change, bump the matching version constant
    and regenerate affected snapshots so regressions compare like-for-like.
    """
    from .generation_eval import qa_golden

    catalog = Path(os.environ.get("PRESALE_CATALOG", "src/presale/data/dev_catalog.json"))
    meta: dict[str, Any] = {
        "generation_golden_version": GENERATION_GOLDEN_VERSION,
        "generation_golden_size": len(qa_golden()),
        "review_golden_version": REVIEW_GOLDEN_VERSION,
        "review_golden_size": len(review_golden()),
        "catalog_path": str(catalog),
        "catalog_sha256": _file_sha256_prefix(catalog),
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if mode is not None:
        meta["mode"] = mode
    return meta


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
    questions: list[dict[str, str]] | None = None,
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
        questions=questions,
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
    questions: list[dict[str, str]] | None = None,
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
        questions=questions,
        sever_evidence=sever_evidence,
    )


def review_golden() -> list[dict[str, Any]]:
    """Deterministic golden set for ReviewAnalyzerAgent sentiment + keywords."""
    return [
        {
            "text": "这个产品非常好用，质量很棒，推荐购买！",
            "expected_sentiment": "positive",
            "expected_keywords": ["好", "棒", "推荐"],
        },
        {
            "text": "太差了，准备退货，非常失望。",
            "expected_sentiment": "negative",
            "expected_keywords": ["差", "退货", "失望"],
        },
        {
            "text": "已收到货，还没开始用，一般般。",
            "expected_sentiment": "neutral",
            "expected_keywords": ["收到", "一般"],
        },
        {
            "text": "性价比超值，物流快捷，值得回购。",
            "expected_sentiment": "positive",
            "expected_keywords": ["超值", "快捷", "值得"],
        },
        {
            "text": "产品有缺陷，客服不处理，准备投诉差评。",
            "expected_sentiment": "negative",
            "expected_keywords": ["缺陷", "投诉", "差评"],
        },
        {
            "text": "正常收到，暂无使用感受。",
            "expected_sentiment": "neutral",
            "expected_keywords": ["正常", "暂无"],
        },
    ]


def run_review(
    *,
    reviews: list[dict[str, Any]] | None = None,
    sources: list[Any] | None = None,
) -> dict[str, Any]:
    """Evaluate ReviewAnalyzerAgent on a deterministic review golden set.

    Offline: each review text is a bare string fed through Harness. Reports
    sentiment accuracy, keyword recall, and the always-need-human contract.
    """
    from agent_runtime.harness import Harness
    from review_agent.agent import ReviewAnalyzerAgent

    agent = ReviewAnalyzerAgent(sources=sources or [])
    rows: list[dict[str, Any]] = []
    items = reviews if reviews is not None else review_golden()
    for index, item in enumerate(items):
        text = item["text"]
        expected = item["expected_sentiment"]
        expected_keywords = list(item.get("expected_keywords") or [])
        try:
            outcome = asyncio.run(Harness().execute(text, agent))
            sentiment: str | None = None
            keywords: list[str] = []
            if outcome.steps:
                for call in outcome.steps[-1].tool_calls:
                    if call.get("tool") == "analyze_review":
                        sentiment = call.get("sentiment")
                        keywords = list(call.get("keywords") or [])
            keyword_hits = len(set(expected_keywords) & set(keywords))
            keyword_recall = (
                round(keyword_hits / len(expected_keywords), 4) if expected_keywords else None
            )
            rows.append(
                {
                    "index": index,
                    "text": text,
                    "expected_sentiment": expected,
                    "predicted_sentiment": sentiment,
                    "sentiment_correct": sentiment == expected,
                    "keywords": keywords,
                    "keyword_recall": keyword_recall,
                    "need_human": bool(outcome.answer_draft and outcome.answer_draft.need_human),
                    "terminal": outcome.terminal.value,
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface the failing review, keep going
            rows.append(
                {
                    "index": index,
                    "text": text,
                    "expected_sentiment": expected,
                    "error": str(exc),
                }
            )
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    n_ok = len(ok)
    correct = sum(1 for r in ok if r["sentiment_correct"])
    need_human = sum(1 for r in ok if r["need_human"])
    recalls = [r["keyword_recall"] for r in ok if r["keyword_recall"] is not None]
    return {
        "n": n,
        "errors": n - n_ok,
        "sentiment_accuracy": round(correct / n_ok, 4) if n_ok else 0.0,
        "mean_keyword_recall": round(sum(recalls) / len(recalls), 4) if recalls else None,
        "need_human_rate": round(need_human / n_ok, 4) if n_ok else 0.0,
        "per_question": rows,
    }


def run_multi_agent(
    *,
    sources: list[Any],
    questions: list[dict[str, str]] | None = None,
    generator: Any = None,
) -> dict[str, Any]:
    """Evaluate Presale → Review orchestration via AgentCoordinator.

    Offline by default (deterministic runner + ReviewAnalyzerAgent). Metrics:
    terminal distribution, short-circuit rate (review never ran), mean agents
    executed, and the final need-human rate. ``generator`` may be injected to
    use a real LLM for the presale leg.
    """
    from agent_runtime.coordinator import AgentCoordinator, format_coordinator_outcome
    from agent_runtime.harness import TerminalDecision
    from review_agent.agent import ReviewAnalyzerAgent

    from ..agent import PresaleAgent
    from ..cli import load_catalog
    from ..contracts import ProductQuestion
    from ..runner import PresaleQaRunner
    from .generation_eval import qa_golden

    items = questions if questions is not None else qa_golden()
    if not sources:
        sources = load_catalog(
            os.environ.get("PRESALE_CATALOG", "src/presale/data/dev_catalog.json")
        )
    rows: list[dict[str, Any]] = []
    terminals: dict[str, int] = {t.value: 0 for t in TerminalDecision}
    short_circuits = 0
    sub_agent_totals = 0
    final_need_human = 0
    for index, item in enumerate(items):
        query = item["query"]
        try:
            question = ProductQuestion(
                question_id=f"q-ma-{index:05d}",
                tenant_id=item["tenant_id"],
                submitted_by=ActorRef(actor_type=ActorType.USER, actor_id="usr_ma_eval"),
                product_id=item["product_id"],
                question_text=query,
                requested_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
                idempotency_key=f"ma-eval-{index:05d}",
            )
            runner = PresaleQaRunner(sources=sources, generator=generator)
            coordinator = AgentCoordinator(
                [
                    PresaleAgent(runner),
                    ReviewAnalyzerAgent(sources=sources),
                ]
            )
            outcome = asyncio.run(coordinator.execute(question))
            rendered = format_coordinator_outcome(outcome)
            sub_count = len(outcome.sub_outcomes)
            short = sub_count < 2
            if short:
                short_circuits += 1
            sub_agent_totals += sub_count
            terminals[outcome.overall_terminal.value] += 1
            need_human = outcome.overall_terminal is TerminalDecision.NEED_HUMAN
            if need_human:
                final_need_human += 1
            rows.append(
                {
                    "tenant_id": item["tenant_id"],
                    "product_id": item["product_id"],
                    "query": query,
                    "overall_terminal": outcome.overall_terminal.value,
                    "sub_agent_count": sub_count,
                    "short_circuited": short,
                    "final_need_human": need_human,
                    "final_answer_id": rendered.get("overall_answer_id"),
                    "sub_terminals": [s.get("terminal") for s in rendered.get("sub_outcomes", [])],
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface the failing question, keep going
            rows.append(
                {
                    "tenant_id": item.get("tenant_id"),
                    "product_id": item.get("product_id"),
                    "query": query,
                    "error": str(exc),
                }
            )
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    n_ok = len(ok)
    return {
        "n": n,
        "errors": n - n_ok,
        "terminals": terminals,
        "short_circuit_rate": round(short_circuits / n_ok, 4) if n_ok else 0.0,
        "mean_sub_agents": round(sub_agent_totals / n_ok, 4) if n_ok else 0.0,
        "final_need_human_rate": round(final_need_human / n_ok, 4) if n_ok else 0.0,
        "per_question": rows,
    }


def run_live_clipper(
    *,
    goldens: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate LiveClipperAgent on a deterministic replay golden (mock ASR/ffmpeg)."""
    from agent_runtime.harness import Harness
    from live_clipper.agent import LiveClipperAgent
    from live_clipper.golden import live_clipper_golden

    agent = LiveClipperAgent()
    rows: list[dict[str, Any]] = []
    items = goldens if goldens is not None else live_clipper_golden()
    for index, item in enumerate(items):
        query = item["query"]
        expected_min = int(item.get("expected_min_clips", 0))
        try:
            outcome = asyncio.run(Harness().execute(query, agent))
            clip_count = 0
            for step in outcome.steps:
                for call in step.tool_calls:
                    if call.get("tool") == "video_cut":
                        clip_count = int(call.get("clip_count") or 0)
            rows.append(
                {
                    "index": index,
                    "query": query,
                    "audio_ref": item.get("audio_ref"),
                    "clip_count": clip_count,
                    "expected_min_clips": expected_min,
                    "clips_ok": clip_count >= expected_min,
                    "need_human": bool(outcome.answer_draft and outcome.answer_draft.need_human),
                    "terminal": outcome.terminal.value,
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface the failing case, keep going
            rows.append(
                {
                    "index": index,
                    "query": query,
                    "audio_ref": item.get("audio_ref"),
                    "error": str(exc),
                }
            )
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    n_ok = len(ok)
    clips_ok = sum(1 for r in ok if r["clips_ok"])
    need_human = sum(1 for r in ok if r["need_human"])
    total_clips = sum(r["clip_count"] for r in ok)
    return {
        "n": n,
        "errors": n - n_ok,
        "clips_expectation_rate": round(clips_ok / n_ok, 4) if n_ok else 0.0,
        "need_human_rate": round(need_human / n_ok, 4) if n_ok else 0.0,
        "total_clips": total_clips,
        "per_question": rows,
    }


def run_content_creator(
    *,
    goldens: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate ContentCreatorAgent on brief goldens (mock copy/image ports)."""
    from agent_runtime.harness import Harness
    from content_creator.agent import ContentCreatorAgent
    from content_creator.golden import content_creator_golden

    from ..contracts import ProductQuestion

    agent = ContentCreatorAgent()
    rows: list[dict[str, Any]] = []
    items = goldens if goldens is not None else content_creator_golden()
    for index, item in enumerate(items):
        query = item["query"]
        expected_platform = item.get("expected_platform")
        expected_images = int(item.get("expected_images", 0))
        try:
            question = ProductQuestion(
                question_id=f"q-cc-{index:05d}",
                tenant_id="tenant-demo",
                submitted_by=ActorRef(actor_type=ActorType.USER, actor_id="usr_cc_eval"),
                product_id=item.get("product_id") or "product-001",
                question_text=query,
                requested_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
                idempotency_key=f"cc-eval-{index:05d}",
            )
            outcome = asyncio.run(Harness().execute(question, agent))
            platform: str | None = None
            image_count = 0
            copy_ok = False
            for step in outcome.steps:
                for call in step.tool_calls:
                    if call.get("tool") == "generate_copy":
                        platform = call.get("platform")
                        copy_ok = call.get("status") == "matched"
                    elif call.get("tool") == "generate_image":
                        image_count = int(call.get("image_count") or 0)
            platform_ok = expected_platform is None or platform == expected_platform
            images_ok = image_count == expected_images
            rows.append(
                {
                    "index": index,
                    "query": query,
                    "product_id": item.get("product_id"),
                    "platform": platform,
                    "expected_platform": expected_platform,
                    "image_count": image_count,
                    "expected_images": expected_images,
                    "copy_ok": copy_ok and platform_ok,
                    "images_ok": images_ok,
                    "need_human": bool(outcome.answer_draft and outcome.answer_draft.need_human),
                    "terminal": outcome.terminal.value,
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface the failing case, keep going
            rows.append(
                {
                    "index": index,
                    "query": query,
                    "product_id": item.get("product_id"),
                    "error": str(exc),
                }
            )
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    n_ok = len(ok)
    copy_pass = sum(1 for r in ok if r["copy_ok"])
    images_pass = sum(1 for r in ok if r["images_ok"])
    need_human = sum(1 for r in ok if r["need_human"])
    return {
        "n": n,
        "errors": n - n_ok,
        "copy_pass_rate": round(copy_pass / n_ok, 4) if n_ok else 0.0,
        "images_pass_rate": round(images_pass / n_ok, 4) if n_ok else 0.0,
        "need_human_rate": round(need_human / n_ok, 4) if n_ok else 0.0,
        "total_images": sum(r["image_count"] for r in ok),
        "per_question": rows,
    }


def summarize(mode: str, report: dict[str, Any]) -> str:
    """Render a compact text summary of an evaluation report."""
    if mode == "review":
        return (
            f"review: n={report.get('n')} "
            f"sentiment_accuracy={report.get('sentiment_accuracy')} "
            f"keyword_recall={report.get('mean_keyword_recall')} "
            f"need_human_rate={report.get('need_human_rate')} "
            f"errors={report.get('errors')}"
        )
    if mode == "multi-agent":
        terminals = report.get("terminals") or {}
        return (
            f"multi-agent: n={report.get('n')} "
            f"terminals={terminals} "
            f"short_circuit_rate={report.get('short_circuit_rate')} "
            f"mean_sub_agents={report.get('mean_sub_agents')} "
            f"final_need_human_rate={report.get('final_need_human_rate')} "
            f"errors={report.get('errors')}"
        )
    if mode == "live-clipper":
        return (
            f"live-clipper: n={report.get('n')} "
            f"clips_expectation_rate={report.get('clips_expectation_rate')} "
            f"total_clips={report.get('total_clips')} "
            f"need_human_rate={report.get('need_human_rate')} "
            f"errors={report.get('errors')}"
        )
    if mode == "content-creator":
        return (
            f"content-creator: n={report.get('n')} "
            f"copy_pass_rate={report.get('copy_pass_rate')} "
            f"images_pass_rate={report.get('images_pass_rate')} "
            f"total_images={report.get('total_images')} "
            f"need_human_rate={report.get('need_human_rate')} "
            f"errors={report.get('errors')}"
        )
    if mode in ("generation", "end-to-end"):
        text = (
            f"{mode}: n={report.get('n')} "
            f"faithfulness={report.get('mean_faithfulness')} "
            f"correctness={report.get('mean_answer_correctness')} "
            f"gold_correctness={report.get('mean_gold_correctness')} "
            f"unsupported={report.get('total_unsupported_claims')}"
        )
        latency = report.get("latency") or {}
        tokens = report.get("tokens") or {}
        cost = report.get("cost") or {}
        if latency or tokens:
            text += (
                f" | wall_s={latency.get('wall_s')}"
                f" mean_ask_ms={latency.get('mean_ask_ms')}"
                f" mean_judge_ms={latency.get('mean_judge_ms')}"
                f" tokens={tokens.get('prompt')}+{tokens.get('completion')}"
            )
            if cost.get("estimated_usd") is not None:
                text += f" cost_usd={cost.get('estimated_usd')}"
        return text
    hit = report.get("hit_at_k", {})
    return (
        f"retrieval: hit@1={hit.get('hit@1')} hit@3={hit.get('hit@3')} "
        f"mrr={hit.get('mrr') if 'mrr' in hit else report.get('mrr')} "
        f"precision@5={report.get('precision@5')}"
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


def _run_mode(
    mode: str,
    args: argparse.Namespace,
    *,
    golden_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one mode and return its report (plus mode tag).

    ``golden_items`` overrides the built-in golden set when provided via
    ``--inputs`` (batch mode).
    """
    # Offline deterministic modes: no Milvus / LLM required.
    if mode == "review":
        return {
            "mode": mode,
            "golden": golden_meta(mode),
            **run_review(reviews=golden_items),
        }
    if mode == "multi-agent":
        return {
            "mode": mode,
            "golden": golden_meta(mode),
            **run_multi_agent(sources=_load_catalog(), questions=golden_items),
        }
    if mode == "live-clipper":
        return {
            "mode": mode,
            "golden": golden_meta(mode),
            **run_live_clipper(goldens=golden_items),
        }
    if mode == "content-creator":
        return {
            "mode": mode,
            "golden": golden_meta(mode),
            **run_content_creator(goldens=golden_items),
        }

    retriever = build_retriever()
    if retriever is None:
        raise SystemExit("PRESALE_MILVUS_URI (or PRESALE_QDRANT_URL) required for evaluation")

    if mode == "retrieval":
        return {
            "mode": mode,
            "golden": golden_meta(mode),
            **run_retrieval(
                retriever, to_questions=(lambda: golden_items) if golden_items else None
            ),
        }

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
            retriever,
            transport=transport,
            base_url=base_url,
            model=model,
            api_key=api_key,
            questions=golden_items,
        )
        return {"mode": mode, "golden": golden_meta(mode), **report}

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
        questions=golden_items,
    )
    return {"mode": mode, "golden": golden_meta(mode), **report}


def _as_per_question(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalize a report to {query: row} for comparison.

    Accepts either the full report shape (``{"per_question": [...]}``) or the
    legacy eval_regression flat snapshot shape (``{"key": {"expected": [...],
    "rank": ...}}``), where each key is the ``tenant/product::query`` string.
    """
    rows = data.get("per_question")
    if rows is not None:
        return {q["query"]: q for q in rows}
    # Flat snapshot: key is tenant/product::query.
    return {
        key: {"query": key, "rank": row.get("rank") if isinstance(row, dict) else None}
        for key, row in data.items()
        if isinstance(row, dict)
    }


def compare_reports(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Diff two evaluation reports per-query and return regressed/improved lists.

    Accepts either the full report shape (``per_question`` list) or the legacy
    election flat snapshot shape (``{"key": {"expected", "rank"}}``).
    Rows may carry ``rank`` (retrieval) or ``error``/metric fields.
    """
    aq = _as_per_question(a)
    bq = _as_per_question(b)
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


def _md_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (dict, list)):
        return "`" + json.dumps(value, ensure_ascii=False) + "`"
    return str(value).replace("|", "\\|")


def _md_metric_rows(report: dict[str, Any]) -> list[tuple[str, Any]]:
    """Flatten well-known scalar metrics for the summary table (stable order)."""
    preferred = (
        "n",
        "errors",
        "mrr",
        "mean_faithfulness",
        "mean_answer_correctness",
        "mean_gold_correctness",
        "total_unsupported_claims",
        "sentiment_accuracy",
        "mean_keyword_recall",
        "need_human_rate",
        "short_circuit_rate",
        "mean_sub_agents",
        "final_need_human_rate",
        "terminals",
    )
    rows: list[tuple[str, Any]] = []
    for key in preferred:
        if key in report:
            rows.append((key, report[key]))
    hit = report.get("hit_at_k")
    if isinstance(hit, dict):
        for key in ("hit@1", "hit@3", "mrr"):
            if key in hit and key != "mrr":
                rows.append((key, hit[key]))
    latency = report.get("latency")
    if isinstance(latency, dict):
        for key in ("wall_s", "mean_ask_ms", "mean_judge_ms"):
            if key in latency:
                rows.append((f"latency.{key}", latency[key]))
    tokens = report.get("tokens")
    if isinstance(tokens, dict):
        for key in ("prompt", "completion"):
            if key in tokens:
                rows.append((f"tokens.{key}", tokens[key]))
    cost = report.get("cost")
    if isinstance(cost, dict) and cost.get("estimated_usd") is not None:
        rows.append(("cost.estimated_usd", cost["estimated_usd"]))
    golden = report.get("golden")
    if isinstance(golden, dict):
        for key in (
            "generation_golden_version",
            "generation_golden_size",
            "review_golden_version",
            "catalog_sha256",
        ):
            if key in golden:
                rows.append((f"golden.{key}", golden[key]))
    return rows


def _append_mode_markdown(lines: list[str], report: dict[str, Any]) -> None:
    mode = report.get("mode", "report")
    lines.append(f"## {mode}")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    for key, value in _md_metric_rows(report):
        lines.append(f"| {key} | {_md_value(value)} |")
    lines.append("")
    per_question = report.get("per_question")
    if isinstance(per_question, list) and per_question:
        lines.append(f"### Per-question ({len(per_question)} rows, first 20)")
        lines.append("")
        sample = per_question[:20]
        headers: list[str] = []
        for row in sample:
            for key in row:
                if key not in headers:
                    headers.append(key)
        # Cap columns for readability.
        headers = headers[:8]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "---|" * len(headers))
        for row in sample:
            lines.append("| " + " | ".join(_md_value(row.get(h)) for h in headers) + " |")
        lines.append("")


def render_markdown(report: dict[str, Any]) -> str:
    """Render an evaluation report as a Markdown document.

    Handles a single-mode report (``{"mode": ...}``) or ``{"modes": [...]}``
    from ``--mode all``.
    """
    lines = ["# Presale evaluation report", ""]
    if isinstance(report.get("modes"), list):
        for item in report["modes"]:
            _append_mode_markdown(lines, item)
    else:
        _append_mode_markdown(lines, report)
    while lines and lines[-1] == "":
        lines.pop()
    lines.append("")
    return "\n".join(lines)


def load_golden_file(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON golden file (must be a list of objects)."""
    target = Path(path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read golden file {path}: {exc}") from exc
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise SystemExit(f"golden file {path} must be a JSON array of objects")
    return data


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def report_csv_row(report: dict[str, Any], *, source: str = "default") -> dict[str, Any]:
    """Flatten a single-mode report into one summary CSV row (stable columns)."""
    row: dict[str, Any] = {
        "mode": report.get("mode", ""),
        "source": source,
        "n": report.get("n", ""),
        "errors": report.get("errors", ""),
    }
    scalar_keys = (
        "mrr",
        "mean_faithfulness",
        "mean_answer_correctness",
        "mean_gold_correctness",
        "total_unsupported_claims",
        "sentiment_accuracy",
        "mean_keyword_recall",
        "need_human_rate",
        "short_circuit_rate",
        "mean_sub_agents",
        "final_need_human_rate",
        "clips_expectation_rate",
        "total_clips",
        "copy_pass_rate",
        "images_pass_rate",
        "total_images",
    )
    for key in scalar_keys:
        if key in report:
            row[key] = _csv_cell(report[key])
    hit = report.get("hit_at_k")
    if isinstance(hit, dict):
        row["hit_at_1"] = _csv_cell(hit.get("hit@1"))
        row["hit_at_3"] = _csv_cell(hit.get("hit@3"))
        if "mrr" in hit and "mrr" not in row:
            row["mrr"] = _csv_cell(hit["mrr"])
    latency = report.get("latency")
    if isinstance(latency, dict):
        for key in ("wall_s", "mean_ask_ms", "mean_judge_ms"):
            if key in latency:
                row[f"latency_{key}"] = _csv_cell(latency[key])
    tokens = report.get("tokens")
    if isinstance(tokens, dict):
        for key in ("prompt", "completion"):
            if key in tokens:
                row[f"tokens_{key}"] = _csv_cell(tokens[key])
    cost = report.get("cost")
    if isinstance(cost, dict):
        row["cost_usd"] = _csv_cell(cost.get("estimated_usd"))
    golden = report.get("golden")
    if isinstance(golden, dict):
        for key in ("generation_golden_version", "review_golden_version", "catalog_sha256"):
            if key in golden:
                row[f"golden_{key}"] = _csv_cell(golden[key])
    return row


def write_summary_csv(rows: list[dict[str, Any]], path: str) -> None:
    """Write a list of summary rows as CSV; union of keys, first-seen order."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        target.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def compare_batch(
    specs: list[str],
    *,
    fail_on_regression: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Run golden regression over multiple ``baseline::current`` path pairs.

    Returns (csv_rows, exit_code). Each row is one pair's compare summary.
    ``::`` is the separator (safe on Windows drive-letter paths).
    """
    rows: list[dict[str, Any]] = []
    total_regressed = 0
    for spec in specs:
        if "::" not in spec:
            raise SystemExit(f"compare-batch spec must be BASELINE::CURRENT, got: {spec}")
        base_s, cur_s = spec.split("::", 1)
        try:
            baseline = json.loads(Path(base_s).read_text(encoding="utf-8"))
            current = json.loads(Path(cur_s).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"cannot read compare pair {spec}: {exc}") from exc
        result = compare_reports(baseline, current)
        summary = result["summary"]
        total_regressed += int(summary["regressed"])
        rows.append(
            {
                "baseline": base_s,
                "current": cur_s,
                "regressed": summary["regressed"],
                "improved": summary["improved"],
                "added": len(result["added"]),
                "removed": len(result["removed"]),
            }
        )
    exit_code = 1 if (fail_on_regression and total_regressed) else 0
    return rows, exit_code


def write_report(report: dict[str, Any], path: str) -> None:
    """Persist an evaluation report as JSON, or Markdown when the path ends in .md."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() in {".md", ".markdown"}:
        target.write_text(render_markdown(report), encoding="utf-8")
    else:
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="presale-eval",
        description=(
            "Run presale QA evaluation "
            "(retrieval / generation / end-to-end / review / multi-agent / "
            "live-clipper / content-creator / all)."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=list(MODES),
        default="all",
        help="which evaluation ring to run (default: all)",
    )
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two result JSONs")
    parser.add_argument(
        "--compare-batch",
        nargs="+",
        metavar="BASELINE::CURRENT",
        help="golden regression over multiple baseline::current JSON pairs",
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        metavar="FILE",
        help="JSON golden files; run --mode once per file (batch)",
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        help="write the report to FILE (.md → Markdown, otherwise JSON)",
    )
    parser.add_argument(
        "--csv",
        metavar="FILE",
        help="write a summary CSV (one row per input file, or one row for a single run)",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="exit non-zero when --compare/--compare-batch finds regressions (CI gate)",
    )
    args = parser.parse_args(argv)

    # --compare-batch is offline: multiple golden regression pairs (BASELINE::CURRENT).
    if args.compare_batch:
        rows, code = compare_batch(args.compare_batch, fail_on_regression=args.fail_on_regression)
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
        if args.csv:
            write_summary_csv(rows, args.csv)
            print(f"wrote csv: {args.csv}")
        if code:
            raise SystemExit(code)
        return 0

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
        if args.fail_on_regression and result["summary"]["regressed"]:
            raise SystemExit(1)
        return 0

    csv_rows: list[dict[str, Any]] = []

    if args.inputs:
        if args.mode == "all":
            raise SystemExit("--inputs requires a single --mode (not 'all')")
        reports = []
        for input_path in args.inputs:
            golden_items = load_golden_file(input_path)
            report = _run_mode(args.mode, args, golden_items=golden_items)
            report["source"] = str(input_path)
            reports.append(report)
            csv_rows.append(report_csv_row(report, source=str(input_path)))
            print(summarize(args.mode, report))
        combined = {"mode": args.mode, "runs": reports}
        if args.output:
            write_report(combined, args.output)
            print(f"wrote report: {args.output}")
        if args.csv:
            write_summary_csv(csv_rows, args.csv)
            print(f"wrote csv: {args.csv}")
        return 0

    if args.mode == "all":
        reports = [_run_mode("retrieval", args)]
        base_url, model, api_key = _llm_config()
        if base_url and model and api_key:
            reports.append(_run_mode("end-to-end", args))
        else:
            print("SKIPPED generation/end-to-end: PRESALE_LLM_* not configured", file=sys.stderr)
        combined = {"modes": reports}
        if args.csv:
            csv_rows = [report_csv_row(r) for r in reports]
    else:
        combined = _run_mode(args.mode, args)
        if args.csv:
            csv_rows = [report_csv_row(combined)]

    if args.output:
        write_report(combined, args.output)
        print(f"wrote report: {args.output}")

    if args.csv:
        write_summary_csv(csv_rows, args.csv)
        print(f"wrote csv: {args.csv}")

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
    "compare_batch",
    "compare_reports",
    "golden_meta",
    "load_golden_file",
    "main",
    "render_markdown",
    "report_csv_row",
    "review_golden",
    "run_content_creator",
    "run_end_to_end",
    "run_generation",
    "run_live_clipper",
    "run_multi_agent",
    "run_retrieval",
    "run_review",
    "summarize",
    "write_report",
    "write_summary_csv",
]
