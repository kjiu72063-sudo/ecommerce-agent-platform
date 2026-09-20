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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_platform_contracts.models import ActorRef, ActorType

from ..cli import load_catalog
from ..contracts import ProductQuestion
from ..runner import PresaleQaRunner
from .openai_generator import OpenAICompatibleGenerator, default_transport

Transport = Callable[..., dict[str, Any]]


def qa_golden() -> list[dict[str, str]]:
    """A representative subset of golden questions used for generation faithfulness."""
    return [
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-001",
            "query": "这件防晒衣能挡住紫外线吗",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-002",
            "query": "零下很冷的天气穿它够暖和吗",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-004",
            "query": "在地铁上打电话对方听得清吗",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-005",
            "query": "戴着游泳能用来测心率吗",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-006",
            "query": "能自己做拿铁吗，奶泡绵不绵密",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-007",
            "query": "能自己规划路线不撞墙吗",
        },
        {
            "tenant_id": "tenant-demo",
            "product_id": "product-008",
            "query": "一坐就是八个小时对腰有支撑吗",
        },
        {"tenant_id": "tenant-acme", "product_id": "product-101", "query": "能折叠带上地铁通勤吗"},
        {
            "tenant_id": "tenant-acme",
            "product_id": "product-102",
            "query": "新装修的房间除甲醛效果好吗",
        },
        {
            "tenant_id": "tenant-other",
            "product_id": "product-201",
            "query": "出差好几天不在家会自动喂猫吗",
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


def _judge_prompt(query: str, evidence: list[str], answer: str) -> str:
    evidence_text = "\n".join(f"- {item}" for item in evidence) or "(无证据)"
    return (
        "你是质检评审。判断客服助手给出的【答案】是否完全基于给定的【证据】、没有编造（幻觉）内容。\n"
        f"用户问题: {query}\n"
        f"证据:\n{evidence_text}\n"
        f"答案: {answer}\n"
        '请只输出一个 JSON 对象：{"faithfulness": 0到1的小数（忠实度，1=完全基于证据无编造，'
        "0=完全编造、与证据冲突或无关）,"
        ' "answer_correctness": 0到1的小数（是否准确回答了问题）,'
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
        if sever_evidence:
            evidence: list[str] = []
        else:
            retrieval = retriever.retrieve(_question(item["tenant_id"], item["product_id"], query))
            evidence = [e.content for e in (retrieval.evidence_items or [])]
        answer = _chat(_answer_prompt(query, evidence), transport, base_url, model, api_key)
        judge_raw = _chat(
            _judge_prompt(query, evidence, answer), transport, base_url, model, api_key
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
    unsupported = sum(r["unsupported_claims"] for r in rows)
    return {
        "n": n,
        "mean_faithfulness": round(faithfulness, 4),
        "mean_answer_correctness": round(correctness, 4),
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
    for row in report["per_question"]:
        row["withheld"] = classify_response(row["answer"]) == "withheld"
        if not row["withheld"] and row["unsupported_claims"] == 0:
            row["undetected_fabrication"] = True
            undetected += 1
        else:
            row["undetected_fabrication"] = False
    return {
        "n": report["n"],
        "withheld": sum(1 for r in report["per_question"] if r["withheld"]),
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
        q = _question(item["tenant_id"], item["product_id"], query, key=f"e2e-{index:05d}")
        retrieval = retriever.retrieve(q)
        evidence = [e.content for e in (retrieval.evidence_items or [])]
        result = asyncio.run(runner.ask(q))
        answer = result.answer_draft.answer_text
        judge_raw = _chat(
            _judge_prompt(query, evidence, answer), transport, base_url, model, api_key
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
    unsupported = sum(r["unsupported_claims"] for r in rows)
    return {
        "n": n,
        "mean_faithfulness": round(faithfulness, 4),
        "mean_answer_correctness": round(correctness, 4),
        "total_unsupported_claims": unsupported,
        "per_question": rows,
    }


def _key(row: dict[str, Any]) -> str:
    return f"{row['tenant_id']}/{row['product_id']}::{row['query']}"


def main(argv: list[str] | None = None) -> None:
    from .hybrid_retrieval import hybrid_retriever_from_env

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
    args = parser.parse_args(argv)

    base_url, model, api_key = llm_config()
    retriever = hybrid_retriever_from_env()
    if retriever is None:
        raise SystemExit("PRESALE_MILVUS_URI required (or another retriever)")

    if args.e2e:
        generator = OpenAICompatibleGenerator(model=model, base_url=base_url, api_key=api_key)
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
                    {
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
        _key(r): {"faithfulness": r["faithfulness"], "answer_correctness": r["answer_correctness"]}
        for r in report["per_question"]
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
            if row["faithfulness"] < args.floor or drop > args.tolerance:
                regressions.append(
                    {
                        "key": key,
                        "reason": "faithfulness dropped"
                        if drop > args.tolerance
                        else "below floor",
                        "old": old["faithfulness"],
                        "new": row["faithfulness"],
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
