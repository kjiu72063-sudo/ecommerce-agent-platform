"""Retrieval evaluation over a golden set: hit@k, precision@k and MRR.

Pure metric functions are offline-testable; ``evaluate_retriever`` drives them
against a live :class:`presale.adapters.external_retrieval.ExternalRetrieval`
(built from env, e.g. real Milvus + real or deterministic embeddings). The golden
set targets ``src/presale/data/dev_catalog.json`` so retrieval quality is
quantifiable and comparable across embedding/retriever changes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable

from agent_platform_contracts.models import ActorRef, ActorType

from ..contracts import ProductQuestion

# (tenant, product, query, expected locators) golden queries for dev_catalog.
# Retrieval here is product-scoped, so the discriminator is **passage (locator)
# ranking**: each query paraphrases the target fact using different words (so BM25
# exact/char match alone is weak), and we check whether the relevant fact chunk ranks
# in top-k. `top_k` for hybrid retrieval is 5, much smaller than each product's ~10
# chunks, so the numbers are meaningful and separate real semantic embeddings from
# meaningless pseudo-vectors.
GOLDEN: list[tuple[str, str, str, set[str]]] = [
    ("tenant-demo", "product-001", "大热天在太阳底下曝晒一整天会不会晒黑", {"spec_upf"}),
    ("tenant-demo", "product-001", "这件衣服经常水洗还能一直防晒吗", {"wash_stability"}),
    ("tenant-demo", "product-001", "被雨打湿了再穿还有防护吗", {"after_rain"}),
    ("tenant-demo", "product-002", "在户外冻很久会抵抗得住吗", {"extreme_cold"}),
    ("tenant-demo", "product-002", "这东西能扔进机器里搅洗吗", {"care"}),
    ("tenant-demo", "product-002", "下点小雪花它能挡一挡吗", {"spec_waterproof"}),
    ("tenant-demo", "product-003", "刚下过雨的石板坡上走会不会滑", {"wet_grip"}),
    ("tenant-demo", "product-003", "鞋底够不够厚，踩石子路硌脚吗", {"rough_ground"}),
    ("tenant-demo", "product-004", "车厢里很吵，打电话对方听得清吗", {"call_quality"}),
    ("tenant-demo", "product-004", "充满一次能连续撑上大半天吗", {"spec_battery"}),
    ("tenant-demo", "product-004", "打游戏的话会不会声音和画面对不上", {"gaming_latency"}),
    ("tenant-demo", "product-005", "戴着跳进水里一圈会进水吗", {"spec_waterproof"}),
    ("tenant-demo", "product-005", "想随时知道自己的心跳快慢", {"heartbeat"}),
    ("tenant-acme", "product-101", "折起来能不能带进地铁通勤", {"transit"}),
    ("tenant-acme", "product-101", "用慢速骑是不是能多撑一段路", {"range"}),
    ("tenant-acme", "product-101", "充一次电大约要几个小时", {"spec_battery"}),
    ("tenant-acme", "product-102", "刚装修完屋里气味重能去掉吗", {"newhome"}),
    ("tenant-acme", "product-102", "夜里睡觉开着它会有动静吗", {"night_use"}),
    ("tenant-acme", "product-102", "里头的耗材隔多久要换掉", {"spec_care"}),
    ("tenant-other", "product-201", "离家好多天会不会把猫饿着", {"travel"}),
    ("tenant-other", "product-201", "每次投放的量能随食量调吗", {"portion"}),
    ("tenant-other", "product-201", "突然断电会影响每天的安排吗", {"power_resume"}),
    ("tenant-demo", "product-001", "这衣服是什么料子做的", {"spec_material"}),
    ("tenant-demo", "product-002", "下雨天穿着淋湿了会变差吗", {"spec_waterproof"}),
    ("tenant-demo", "product-004", "出汗多的时候戴着会进水吗", {"spec_waterproof"}),
    ("tenant-acme", "product-101", "遇上有坡的路段能爬上去吗", {"spec_speed"}),
    ("tenant-demo", "product-006", "早上想喝杯现磨的，豆子要自己磨吗", {"spec_grind"}),
    ("tenant-demo", "product-006", "奶泡能不能打得绵密，做拿铁行吗", {"spec_milk"}),
    ("tenant-demo", "product-006", "用久了机器里面会不会结垢，怎么处理", {"care"}),
    ("tenant-demo", "product-007", "地板上的头发丝能吸得动吗", {"spec_suction"}),
    ("tenant-demo", "product-007", "它会一头撞上家里的家具吗", {"spec_obstacle"}),
    ("tenant-demo", "product-007", "扫到一半没电了它能自己回去充吗", {"spec_battery"}),
    ("tenant-demo", "product-008", "一坐就是八个小时，腰会不会酸", {"spec_lumbar"}),
    ("tenant-demo", "product-008", "想往后躺着休息一下可以吗", {"spec_recline"}),
    ("tenant-acme", "product-103", "赶上大暴雨，待在里头会淋湿吗", {"spec_waterproof"}),
    ("tenant-acme", "product-103", "两个人搭起来要多久", {"setup_time"}),
    ("tenant-acme", "product-104", "大白天不拉窗帘，画面看得清吗", {"spec_brightness"}),
    ("tenant-acme", "product-104", "能连手机无线投屏上去吗", {"spec_connect"}),
    ("tenant-other", "product-202", "我是刚开始练的，阻力会不会太难", {"spec_resistance"}),
    ("tenant-other", "product-202", "想边骑边看心率，表盘上能看到吗", {"spec_display"}),
]

K_DEFAULT = (1, 3, 5)
PRECISION_K = 5


def _rank_of_expected(evidence_sources: list[str], expected: set[str]) -> int | None:
    for idx, source_id in enumerate(evidence_sources):
        if source_id in expected:
            return idx + 1
    return None


def hit_at_k(evidence_sources: list[str], expected: set[str], k: int) -> int:
    """1 if any expected source is within the first ``k`` hits, else 0."""
    rank = _rank_of_expected(evidence_sources, expected)
    return 1 if rank is not None and rank <= k else 0


def mrr(evidence_sources: list[str], expected: set[str]) -> float:
    """Reciprocal rank of the first expected source (0 if absent)."""
    rank = _rank_of_expected(evidence_sources, expected)
    return 1.0 / rank if rank is not None else 0.0


def precision_at_k(evidence_sources: list[str], expected: set[str], k: int) -> float:
    """Fraction of the top-``k`` hits that are expected sources."""
    top = evidence_sources[:k]
    if not top:
        return 0.0
    return sum(1 for src in top if src in expected) / len(top)


def evaluate(queries: list[dict[str, Any]], k: tuple[int, ...] = K_DEFAULT) -> dict[str, Any]:
    """Aggregate hit@k / MRR / precision@k over golden queries.

    Each ``query`` dict: ``{"evidence_sources": [...], "expected": set[str]}``.
    """
    n = len(queries)
    assert n > 0, "golden set is empty"
    hit: dict[int, float] = {k_: 0.0 for k_ in k}
    mrr_sum = 0.0
    prec_sum = 0.0
    per_query: list[dict[str, Any]] = []
    for q in queries:
        srcs = q["evidence_sources"]
        exp = q["expected"]
        per_query.append(
            {
                "query": q.get("query", ""),
                "tenant_id": q.get("tenant_id", ""),
                "product_id": q.get("product_id", ""),
                "rank": _rank_of_expected(srcs, exp),
                "top_sources": srcs[:PRECISION_K],
            }
        )
        for k_ in k:
            hit[k_] += hit_at_k(srcs, exp, k_)
        mrr_sum += mrr(srcs, exp)
        prec_sum += precision_at_k(srcs, exp, PRECISION_K)
    return {
        "n": n,
        "hit_at_k": {f"hit@{k_}": round(hit[k_] / n, 4) for k_ in k},
        "mrr": round(mrr_sum / n, 4),
        f"precision@{PRECISION_K}": round(prec_sum / n, 4),
        "per_query": per_query,
    }


def golden_questions() -> list[dict[str, Any]]:
    """Golden set as question dicts, ready for ``evaluate``."""
    return [
        {
            "tenant_id": tenant,
            "product_id": product,
            "query": query,
            "expected": expected,
            "evidence_sources": [],
        }
        for tenant, product, query, expected in GOLDEN
    ]


def _question(tenant: str, product: str, query: str) -> ProductQuestion:
    actor = ActorRef(actor_type=ActorType.USER, actor_id="usr_ret_eval_0001")
    return ProductQuestion(
        question_id="q-ret-eval-0001",
        tenant_id=tenant,
        submitted_by=actor,
        product_id=product,
        question_text=query,
        requested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        idempotency_key="ret-eval-0001",
    )


def evaluate_retriever(
    retriever: Any,
    *,
    k: tuple[int, ...] = K_DEFAULT,
    to_questions: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Run ``evaluate`` against a live retriever, filling in evidence sources."""
    base = (to_questions or golden_questions)()
    queries: list[dict[str, Any]] = []
    for item in base:
        result = retriever.retrieve(_question(item["tenant_id"], item["product_id"], item["query"]))
        item["evidence_sources"] = [e.locator for e in (result.evidence_items or [])]
        queries.append(item)
    return evaluate(queries, k=k)


def main(argv: list[str] | None = None) -> None:
    """Run retrieval evaluation against a live retriever built from env."""
    import argparse

    from .hybrid_retrieval import hybrid_retriever_from_env

    parser = argparse.ArgumentParser(
        prog="presale-eval-retrieval",
        description="Evaluate hybrid retrieval quality on the dev_catalog golden set.",
    )
    parser.add_argument(
        "--catalog",
        default=os.environ.get("PRESALE_CATALOG", "src/presale/data/dev_catalog.json"),
        help="Catalog to index (default dev_catalog.json)",
    )
    parser.add_argument("--top-k", type=int, help="Hybrid top_k (env PRESALE_HYBRID_TOP_K)")
    parser.add_argument("--pool", type=int, help="Hybrid candidate pool (env PRESALE_HYBRID_POOL)")
    parser.add_argument("--rrf-k", type=int, help="RRF fusion k (env PRESALE_HYBRID_RRF_K)")
    parser.add_argument("--dense-k", type=int, help="Dense candidates (env PRESALE_HYBRID_DENSE_K)")
    parser.add_argument("--bm25-k", type=int, help="BM25 candidates (env PRESALE_HYBRID_BM25_K)")
    parser.add_argument(
        "--bm25-weight", type=float, help="BM25 RRF weight (env PRESALE_HYBRID_BM25_WEIGHT)"
    )
    parser.add_argument("--reranker-model", help="Reranker model path (env PRESALE_RERANKER_MODEL)")
    args = parser.parse_args(argv)
    os.environ.setdefault("PRESALE_CATALOG", args.catalog)
    for env_name, value in (
        ("PRESALE_HYBRID_TOP_K", args.top_k),
        ("PRESALE_HYBRID_POOL", args.pool),
        ("PRESALE_HYBRID_RRF_K", args.rrf_k),
        ("PRESALE_HYBRID_DENSE_K", args.dense_k),
        ("PRESALE_HYBRID_BM25_K", args.bm25_k),
        ("PRESALE_HYBRID_BM25_WEIGHT", args.bm25_weight),
        ("PRESALE_RERANKER_MODEL", args.reranker_model),
    ):
        if value is not None:
            os.environ[env_name] = str(value)
    retriever = hybrid_retriever_from_env()
    if retriever is None:
        raise SystemExit("PRESALE_MILVUS_URI required (or PRESALE_QDRANT_URL)")
    report = evaluate_retriever(retriever)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "per_query"}, ensure_ascii=False, indent=2
        )
    )


__all__ = [
    "GOLDEN",
    "evaluate",
    "evaluate_retriever",
    "golden_questions",
    "hit_at_k",
    "main",
    "mrr",
    "precision_at_k",
]
