"""Generation-faithfulness evaluation (lightweight LLM-as-judge).

Measures whether answers generated from retrieved evidence stay grounded (no
hallucination). Pipeline per golden question: retrieve evidence (hybrid retriever)
-> generate an answer via the real LLM -> ask a judge LLM to rate faithfulness and
correctness. Reuses the OpenAI-compatible transport (``PRESALE_LLM_*`` env), so no
new dependencies. The judge parsing and aggregation are pure and offline-testable.

Regression guard: ``--save <snapshot>`` writes per-question scores; a plain run with
``--snapshot`` compares against it with a tolerance and a floor, exiting non-zero
when a question's faithfulness drops or falls below the floor.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_platform_contracts.models import ActorRef, ActorType

from ..cli import load_catalog
from ..contracts import ProductQuestion
from ..runner import PresaleQaRunner

Transport = Callable[..., dict[str, Any]]


def qa_golden() -> list[dict[str, str]]:
    """Golden QA for generation faithfulness + gold-correctness.

    ``gold`` is the concise reference answer (derived from the catalog facts). It
    lets the judge score ``gold_correctness`` separately from faithfulness, so we can
    catch answers that are grounded in evidence yet factually wrong / off-point.
    """
    return [
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-001",
            "query": "这件防晒衣能挡住紫外线吗",
            "gold": "能。实测紫外线防护系数 UPF50+，可有效阻挡紫外线防晒黑。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-002",
            "query": "零下很冷的天气穿它够暖和吗",
            "gold": "能。零下严寒环境中仍能有效锁温抗寒。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-004",
            "query": "在地铁上打电话对方听得清吗",
            "gold": "能。降噪麦克风拾音清晰，嘈杂环境通话对方仍听得清。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-005",
            "query": "戴着游泳能用来测心率吗",
            "gold": "能。50 米防水可戴着游泳，并支持 24 小时心率监测。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-006",
            "query": "能自己做拿铁吗，奶泡绵不绵密",
            "gold": "能。自动奶泡系统可打出绵密奶泡做拿铁。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-007",
            "query": "能自己规划路线不撞墙吗",
            "gold": "能。激光导航自动规划路线，红外避障不硬撞家具。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-008",
            "query": "一坐就是八个小时对腰有支撑吗",
            "gold": "能。独立腰托可调，久坐有支撑缓解腰酸。",
        },
        {
            "tenant_id": "tenant-acme",
            "product_id": "product-101",
            "query": "能折叠带上地铁通勤吗",
            "gold": "能。一键折叠可带上地铁通勤。",
        },
        {
            "tenant_id": "tenant-acme",
            "product_id": "product-102",
            "query": "新装修的房间除甲醛效果好吗",
            "gold": "能。甲醛净化 CADR 350，对刚装修房间的甲醛与异味有明显净化作用。",
        },
        {
            "tenant_id": "tenant-other",
            "product_id": "product-201",
            "query": "出差好几天不在家会自动喂猫吗",
            "gold": "能。支持定时定量与远程 App 投喂，离家期间可自动供粮。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-009",
            "query": "装的水够不够健身喝，会不会漏",
            "gold": "750ml 大容量够一次健身喝；旋盖加密封圈，倒置也不漏水。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-010",
            "query": "冬天贴身穿够暖吗，能塞羽绒服里当内搭吗",
            "gold": "贴身穿较暖和，靠锁温空气层；修身剪裁可作羽绒服内搭。",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-011",
            "query": "夏天戴的帽子能挡住脸不被晒吗",
            "gold": "能。宽檐设计可遮住脸与脖子不被晒到。",
        },
        {
            "tenant_id": "tenant-acme",
            "product_id": "product-105",
            "query": "彩色衣服用这个洗衣液会掉色吗",
            "gold": "不含荧光增白剂，彩色衣物不掉色。",
        },
        {
            "tenant_id": "tenant-acme",
            "product_id": "product-106",
            "query": "硬水果能打碎吗，榨完能不能直接带走喝",
            "gold": "能。大功率电机可打碎硬果蔬；杯体一体式，榨完拧盖直接带走。",
        },
        {
            "tenant_id": "tenant-acme",
            "product_id": "product-107",
            "query": "睡久了会不会塌，腰不好的人睡合适吗",
            "gold": "软硬适中偏硬不会塌；护腰三分区支撑，适合腰不好的人。",
        },
        {
            "tenant_id": "tenant-other",
            "product_id": "product-203",
            "query": "猫上完厕所会自己清理吗",
            "gold": "能。猫咪使用后会自动清理结块猫砂。",
        },
        {
            "tenant_id": "tenant-other",
            "product_id": "product-204",
            "query": "能直接拎上飞机不托运吗",
            "gold": "能。20 寸可登机，无需托运。",
        },
    ]


# Phrases that indicate the assistant withheld an answer because evidence was
# insufficient, rather than fabricating one.
REFUSAL_MARKERS = (
    "无法确定",
    "无法确认",
    "无法判断",
    "无法回答",
    "不确定",
    "没有相关信息",
    "证据中未",
    "未提供",
    "未提及",
    "未说明",
    "未查到",
    "无法从证据",
    "需要人工",
    "转人工",
    "无法核实",
    "难以确定",
    "不清楚",
    "建议咨询",
    "咨询官方",
    "咨询客服",
    "建议联系",
    "以官方为准",
    "建议以",
)


def classify_response(answer: str) -> str:
    """Classify an answer as a grounded refusal (``withheld``) or ``answered``."""
    return "withheld" if any(marker in answer for marker in REFUSAL_MARKERS) else "answered"


def qa_golden_adversarial() -> list[dict[str, str]]:
    """Questions the catalog cannot answer from evidence (topics absent from chunks).

    Used to verify the pipeline does not hallucinate when evidence is insufficient:
    the assistant must either withhold (grounded refusal) or, if it answers, the
    judge must flag the claims as unsupported.
    """
    return [
        {"tenant_id": "tenant-demo", "product_id": "product-001", "query": "能开发票吗，怎么申请"},
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-002",
            "query": "偏远地区包邮吗，发货多久",
        },
        {
            "tenant_id": "tenant-acme",
            "product_id": "product-102",
            "query": "滤网能不能在官方店单独买",
        },
        {"tenant_id": "tenant-other", "product_id": "product-201", "query": "能不能七天无理由退货"},
    ]


def _judge_prompt(query: str, evidence: list[str], answer: str, gold: str | None = None) -> str:
    evidence_text = "\n".join(f"- {item}" for item in evidence) or "(无证据)"
    gold_text = gold or "(未提供参考)"
    return (
        "你是质检评审。判断客服助手给出的【答案】是否完全基于给定的【证据】、没有编造（幻觉）内容，"
        "并结合【参考正确回答】判断答案是否正确/是否答到点子上（可据此抓出忠实但答错的情况）。\n"
        f"用户问题: {query}\n"
        f"证据:\n{evidence_text}\n"
        f"参考正确回答: {gold_text}\n"
        f"答案: {answer}\n"
        '请只输出一个 JSON 对象：{"faithfulness": 0到1的小数（忠实度，1=完全基于证据无编造，'
        "0=完全编造、与证据冲突或无关）,"
        ' "answer_correctness": 0到1的小数（是否准确回答了问题）,'
        ' "gold_correctness": 0到1的小数（对照参考回答是否正确，1=完全正确答到点上，'
        "0=答错或答非所问，即使措辞忠实）,"
        ' "unsupported_claims": 证据不支持的主张列表（没有则为空数组）}'
    )


def _answer_prompt(query: str, evidence: list[str]) -> str:
    evidence_text = (
        "\n".join(f"- {item}" for item in evidence) or "(无证据——请说明无法确定，需要转人工复核)"
    )
    return (
        "你是电商售前客服助手，请仅依据给定证据回答用户对商品的提问，不要编造证据之外的信息。\n"
        f"用户问题: {query}\n"
        f"证据:\n{evidence_text}\n"
        "请给出简洁、准确、仅基于证据的中文回答。"
    )


def parse_judge(text: str) -> dict[str, Any]:
    """Extract faithfulness / answer_correctness from a judge response (robust)."""

    def _num(pattern: str, default: float) -> float:
        match = re.search(pattern, text)
        if not match:
            return default
        try:
            value = float(match.group(1))
        except ValueError:
            return default
        return max(0.0, min(1.0, value))

    unsupported = 0
    match = re.search(r'"unsupported_claims"\s*:\s*(\[.*?\])', text, re.DOTALL)
    if match:
        try:
            unsupported = len(json.loads(match.group(1)))
        except json.JSONDecodeError:
            unsupported = 0
    return {
        "faithfulness": _num(r'"faithfulness"\s*:\s*(\d+(?:\.\d+)?)', 0.0),
        "answer_correctness": _num(r'"answer_correctness"\s*:\s*(\d+(?:\.\d+)?)', 0.0),
        "gold_correctness": _num(r'"gold_correctness"\s*:\s*(\d+(?:\.\d+)?)', 0.0),
        "unsupported_claims": unsupported,
    }


def llm_config() -> tuple[str, str, str]:
    base_url = os.environ.get("PRESALE_LLM_BASE_URL")
    model = os.environ.get("PRESALE_LLM_MODEL")
    api_key = os.environ.get("PRESALE_LLM_API_KEY")
    if not (base_url and model and api_key):
        raise SystemExit("PRESALE_LLM_BASE_URL / PRESALE_LLM_MODEL / PRESALE_LLM_API_KEY required")
    return base_url, model, api_key


def _chat(prompt: str, transport: Transport, base_url: str, model: str, api_key: str) -> str:
    completion = transport(
        api_key=api_key,
        base_url=base_url,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        timeout_s=float(os.environ.get("PRESALE_GEN_TIMEOUT_S", "60")),
    )
    return completion["choices"][0]["message"]["content"]


def _question(tenant: str, product: str, query: str, key: str = "gen-key-0001") -> ProductQuestion:
    return ProductQuestion(
        question_id="q-gen-0001",
        tenant_id=tenant,
        submitted_by=ActorRef(actor_type=ActorType.USER, actor_id="usr_gen_0001"),
        product_id=product,
        question_text=query,
        requested_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
        idempotency_key=key,
    )


def evaluate_generation(
    retriever: Any,
    *,
    transport: Transport,
    base_url: str,
    model: str,
    api_key: str,
    questions: list[dict[str, str]] | None = None,
    sever_evidence: bool = False,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in questions if questions is not None else qa_golden():
        query = item["query"]
        gold = item.get("gold")
        if sever_evidence:
            evidence: list[str] = []
        else:
            retrieval = retriever.retrieve(_question(item["tenant_id"], item["product_id"], query))
            evidence = [e.content for e in (retrieval.evidence_items or [])]
        answer = _chat(_answer_prompt(query, evidence), transport, base_url, model, api_key)
        judge_raw = _chat(
            _judge_prompt(query, evidence, answer, gold), transport, base_url, model, api_key
        )
        rows.append(
            {
                "tenant_id": item["tenant_id"],
                "product_id": item["product_id"],
                "query": query,
                **parse_judge(judge_raw),
                "answer": answer,
            }
        )
    n = len(rows)
    faithfulness = sum(r["faithfulness"] for r in rows) / n
    correctness = sum(r["answer_correctness"] for r in rows) / n
    gold_correctness = sum(r["gold_correctness"] for r in rows) / n
    unsupported = sum(r["unsupported_claims"] for r in rows)
    return {
        "n": n,
        "mean_faithfulness": round(faithfulness, 4),
        "mean_answer_correctness": round(correctness, 4),
        "mean_gold_correctness": round(gold_correctness, 4),
        "total_unsupported_claims": unsupported,
        "per_question": rows,
    }


def evaluate_adversarial(
    retriever: Any,
    *,
    transport: Transport,
    base_url: str,
    model: str,
    api_key: str,
    sever_evidence: bool = False,
) -> dict[str, Any]:
    """Run the adversarial (evidence-insufficient) golden.

    Each case should be a grounded refusal (``withheld``) OR, if the assistant answers
    anyway, the judge must flag the claim as unsupported. ``undetected_fabrications``
    counts answers that fabricated a claim the judge did NOT flag — an end-to-end
    hallucination failure to guard against.
    """
    report = evaluate_generation(
        retriever,
        transport=transport,
        base_url=base_url,
        model=model,
        api_key=api_key,
        questions=qa_golden_adversarial(),
        sever_evidence=sever_evidence,
    )
    return mark_undetected(report)


class _SeveredRetriever:
    """Wrap a retriever so the runner/evidence see no evidence (retrieval failure)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def retrieve(self, question: ProductQuestion):
        from ..knowledge import RetrievalResult, RetrievalStatus

        return RetrievalResult(
            status=RetrievalStatus.NO_EVIDENCE,
            evidence_items=[],
            reason_codes=["E2E_SEVERED"],
        )


def mark_undetected(report: dict[str, Any]) -> dict[str, Any]:
    """Classify per-question answers as withheld vs undetected fabrication."""
    undetected = 0
    errors = 0
    for row in report["per_question"]:
        if "error" in row:
            row["withheld"] = False
            row["undetected_fabrication"] = False
            errors += 1
            continue
        row["withheld"] = classify_response(row["answer"]) == "withheld"
        if not row["withheld"] and row["unsupported_claims"] == 0:
            row["undetected_fabrication"] = True
            undetected += 1
        else:
            row["undetected_fabrication"] = False
    return {
        "n": report["n"],
        "errors": errors,
        "withheld": sum(1 for r in report["per_question"] if r.get("withheld")),
        "mean_faithfulness": report["mean_faithfulness"],
        "undetected_fabrications": undetected,
        "per_question": report["per_question"],
    }


def evaluate_end_to_end(
    retriever: Any,
    *,
    sources: list[Any],
    generator: Any,
    transport: Transport,
    base_url: str,
    model: str,
    api_key: str,
    questions: list[dict[str, str]] | None = None,
    sever_evidence: bool = False,
) -> dict[str, Any]:
    """Run the QA golden through the real ``PresaleQaRunner.ask`` production path.

    Retrieval + generation go through the actual runner (not the rebuilt pipeline);
    the produced answers are then judged by the same LLM-as-judge. ``sever_evidence``
    wraps the retriever so the runner sees no evidence (total retrieval failure).
    """
    if sever_evidence:
        retriever = _SeveredRetriever(retriever)
    runner = PresaleQaRunner(sources=sources, retriever=retriever, generator=generator)
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(questions if questions is not None else qa_golden()):
        query = item["query"]
        gold = item.get("gold")
        try:
            q = _question(item["tenant_id"], item["product_id"], query, key=f"e2e-{index:05d}")
            retrieval = retriever.retrieve(q)
            evidence = [e.content for e in (retrieval.evidence_items or [])]
            result = asyncio.run(runner.ask(q))
            answer = result.answer_draft.answer_text
            judge_raw = _chat(
                _judge_prompt(query, evidence, answer, gold), transport, base_url, model, api_key
            )
            rows.append(
                {
                    "tenant_id": item["tenant_id"],
                    "product_id": item["product_id"],
                    "query": query,
                    **parse_judge(judge_raw),
                    "answer": answer,
                }
            )
        except Exception as exc:  # noqa: BLE001 - surface the failing question, keep going
            rows.append(
                {
                    "tenant_id": item["tenant_id"],
                    "product_id": item["product_id"],
                    "query": query,
                    "error": str(exc),
                }
            )
    ok = [r for r in rows if "error" not in r]
    n = len(rows)
    n_ok = len(ok)
    faithfulness = sum(r["faithfulness"] for r in ok) / n_ok if n_ok else 0.0
    correctness = sum(r["answer_correctness"] for r in ok) / n_ok if n_ok else 0.0
    gold_correctness = sum(r["gold_correctness"] for r in ok) / n_ok if n_ok else 0.0
    unsupported = sum(r["unsupported_claims"] for r in ok)
    return {
        "n": n,
        "errors": n - n_ok,
        "mean_faithfulness": round(faithfulness, 4),
        "mean_answer_correctness": round(correctness, 4),
        "mean_gold_correctness": round(gold_correctness, 4),
        "total_unsupported_claims": unsupported,
        "per_question": rows,
    }


def evaluate_idempotency_replay(
    retriever: Any,
    *,
    sources: list[Any],
    generator: Any,
    question: dict[str, str] | None = None,
    database: str | Path | None = None,
) -> dict[str, Any]:
    """Run one real-generation question twice through durable SQLite state.

    The second call uses the same idempotency key. A successful replay must
    return the persisted draft and must not invoke the generator again.
    """
    from ..adapters.sqlite import (
        SQLiteAnswerDraftRepository,
        SQLiteDispositionRepository,
        SQLiteEvidenceRepository,
        SQLiteIdempotencyRepository,
        SQLitePresaleStore,
        SQLiteProductQuestionRepository,
        SQLiteRunTraceRepository,
    )
    from ..answer import GeneratorPort

    item = question or qa_golden()[0]
    tmp_dir: tempfile.TemporaryDirectory[str] | None = None
    if database is None:
        tmp_dir = tempfile.TemporaryDirectory()
        db_path = Path(tmp_dir.name) / "replay.sqlite3"
    else:
        db_path = Path(database)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = SQLitePresaleStore(db_path)
    calls = 0

    class CountingGenerator(GeneratorPort):
        def generate(self, question, retrieval, *, run_ref, configuration_refs):
            nonlocal calls
            calls += 1
            return generator.generate(
                question,
                retrieval,
                run_ref=run_ref,
                configuration_refs=configuration_refs,
            )

    runner = PresaleQaRunner(
        sources=sources,
        retriever=retriever,
        generator=CountingGenerator(),
        question_repo=SQLiteProductQuestionRepository(store),
        evidence_repo=SQLiteEvidenceRepository(store),
        answer_repo=SQLiteAnswerDraftRepository(store),
        disposition_repo=SQLiteDispositionRepository(store),
        trace_repo=SQLiteRunTraceRepository(store),
        idempotency_repo=SQLiteIdempotencyRepository(store),
    )
    q = _question(item["tenant_id"], item["product_id"], item["query"], key="e2e-replay-0001")

    def _ask_once():
        # A burst of e2e calls can leave the provider briefly 5xx/slow; absorb
        # up to two transient failures on the first generation without masking
        # a persistent failure. The second call never retries — replay must
        # read the durable draft.
        from ..runner import QaRuntimeError

        delays = (3, 8)
        last_error: QaRuntimeError | None = None
        for attempt in range(len(delays) + 1):
            try:
                return asyncio.run(runner.ask(q))
            except QaRuntimeError as exc:
                last_error = exc
                if attempt == len(delays):
                    raise
                time.sleep(delays[attempt])
        raise last_error if last_error else QaRuntimeError("REPLAY_ASK_FAILED")

    try:
        first = _ask_once()
        calls_after_first = calls
        second = asyncio.run(runner.ask(q))
        return {
            "question": item["query"],
            "first_run_ref": first.run_ref,
            "second_run_ref": second.run_ref,
            "first_answer_id": first.answer_draft.answer_id,
            "second_answer_id": second.answer_draft.answer_id,
            "same_answer": first.answer_draft.model_dump(mode="json")
            == second.answer_draft.model_dump(mode="json"),
            "generator_calls": calls,
            "replayed_without_generation": calls == calls_after_first and calls_after_first >= 1,
        }
    finally:
        store.close()
        if tmp_dir is not None:
            tmp_dir.cleanup()


def _key(row: dict[str, Any]) -> str:
    return f"{row['tenant_id']}/{row['product_id']}::{row['query']}"


def main(argv: list[str] | None = None) -> None:
    from .hybrid_retrieval import hybrid_retriever_from_env
    from .openai_generator import OpenAICompatibleGenerator, default_transport

    parser = argparse.ArgumentParser(description="Generation faithfulness evaluation.")
    parser.add_argument("--snapshot", help="snapshot path for regression compare")
    parser.add_argument("--save", action="store_true", help="write snapshot baseline")
    parser.add_argument("--floor", type=float, default=0.4, help="faithfulness floor (default 0.4)")
    parser.add_argument("--tolerance", type=float, default=0.25, help="delta tolerance vs snapshot")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument(
        "--adversarial",
        action="store_true",
        help="run evidence-insufficient adversarial golden (must not fabricate undetected)",
    )
    parser.add_argument(
        "--sever-evidence",
        action="store_true",
        help="force empty evidence (simulate total retrieval failure) for --adversarial",
    )
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="run through the real PresaleQaRunner.ask (production path)",
    )
    parser.add_argument(
        "--catalog",
        default="src/presale/data/dev_catalog.json",
        help="catalog for e2e runner sources (default dev_catalog.json)",
    )
    parser.add_argument(
        "--idempotency-replay",
        action="store_true",
        help="run one real question twice through durable SQLite state",
    )
    parser.add_argument(
        "--replay-db",
        help="SQLite path for --idempotency-replay (default: temporary database)",
    )
    args = parser.parse_args(argv)

    base_url, model, api_key = llm_config()
    retriever = hybrid_retriever_from_env()
    if retriever is None:
        raise SystemExit("PRESALE_MILVUS_URI required (or another retriever)")

    if args.idempotency_replay:
        generator = OpenAICompatibleGenerator(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout_s=float(os.environ.get("PRESALE_GEN_TIMEOUT_S", "60")),
        )
        report = evaluate_idempotency_replay(
            retriever,
            sources=load_catalog(args.catalog),
            generator=generator,
            database=args.replay_db,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report["replayed_without_generation"] else 1)

    if args.e2e:
        generator = OpenAICompatibleGenerator(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout_s=float(os.environ.get("PRESALE_GEN_TIMEOUT_S", "60")),
        )
        sources = load_catalog(args.catalog)
        if args.adversarial:
            report = mark_undetected(
                evaluate_end_to_end(
                    retriever,
                    sources=sources,
                    generator=generator,
                    transport=default_transport,
                    base_url=base_url,
                    model=model,
                    api_key=api_key,
                    questions=qa_golden_adversarial(),
                    sever_evidence=args.sever_evidence,
                )
            )
        else:
            report = evaluate_end_to_end(
                retriever,
                sources=sources,
                generator=generator,
                transport=default_transport,
                base_url=base_url,
                model=model,
                api_key=api_key,
            )
    elif args.adversarial:
        report = evaluate_adversarial(
            retriever,
            transport=default_transport,
            base_url=base_url,
            model=model,
            api_key=api_key,
            sever_evidence=args.sever_evidence,
        )
    else:
        report = evaluate_generation(
            retriever,
            transport=default_transport,
            base_url=base_url,
            model=model,
            api_key=api_key,
        )

    if args.adversarial:
        print(
            json.dumps(
                {k: v for k, v in report.items() if k != "per_question"},
                ensure_ascii=False,
                indent=2,
            )
        )
        for row in report["per_question"]:
            if "error" in row:
                print(
                    f"[ERROR] {row['tenant_id']}/{row['product_id']} :: {row['query']} "
                    f"{row['error']}"
                )
                continue
            flag = "UNDETECTED-FABRICATION" if row["undetected_fabrication"] else "ok"
            print(
                f"[{flag}] {row['tenant_id']}/{row['product_id']} withheld={row['withheld']} "
                f"faith={row['faithfulness']} unsupported={row['unsupported_claims']} :: "
                f"{row['query']}"
            )
        print(f"undetected_fabrications={report['undetected_fabrications']}")
        raise SystemExit(1 if report["undetected_fabrications"] else 0)

    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "per_question"}, ensure_ascii=False, indent=2
        )
    )
    if args.diagnostics:
        print(
            json.dumps(
                [
                    row
                    if "error" in row
                    else {
                        k: row[k]
                        for k in (
                            "tenant_id",
                            "product_id",
                            "query",
                            "faithfulness",
                            "answer_correctness",
                            "unsupported_claims",
                        )
                    }
                    for row in report["per_question"]
                ],
                ensure_ascii=False,
                indent=2,
            )
        )

    current = {
        _key(r): {
            "faithfulness": r["faithfulness"],
            "answer_correctness": r["answer_correctness"],
            "gold_correctness": r["gold_correctness"],
        }
        for r in report["per_question"]
        if "error" not in r
    }

    if args.save:
        path = Path(args.snapshot or "tests/fixtures/generation_snapshot.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote snapshot: {path}")
        return

    if args.snapshot:
        baseline = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
        regressions: list[dict] = []
        for key, row in current.items():
            old = baseline.get(key)
            if old is None:
                regressions.append({"key": key, "reason": "new question"})
                continue
            drop = old["faithfulness"] - row["faithfulness"]
            gold_drop = old.get("gold_correctness", 1.0) - row["gold_correctness"]
            if (
                row["faithfulness"] < args.floor
                or drop > args.tolerance
                or row["gold_correctness"] < args.floor
                or gold_drop > args.tolerance
            ):
                regressions.append(
                    {
                        "key": key,
                        "reason": "faithfulness dropped"
                        if drop > args.tolerance
                        else (
                            "gold correctness dropped"
                            if gold_drop > args.tolerance
                            else "below floor"
                        ),
                        "old": old["faithfulness"],
                        "new": row["faithfulness"],
                        "old_gold": old.get("gold_correctness"),
                        "new_gold": row["gold_correctness"],
                    }
                )
        for item in regressions:
            print("REGRESSED " + json.dumps(item, ensure_ascii=False))
        print(f"regressions={len(regressions)}")
        raise SystemExit(1 if regressions else 0)


__all__ = [
    "evaluate_end_to_end",
    "evaluate_generation",
    "llm_config",
    "main",
    "mark_undetected",
    "parse_judge",
    "qa_golden",
    "qa_golden_adversarial",
]
