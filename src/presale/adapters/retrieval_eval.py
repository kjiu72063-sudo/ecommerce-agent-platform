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
    ("tenant-demo", "product-003", "刚下过雨的石板坡上走会不会滑", {"spec_sole", "wet_grip"}),
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
    ("tenant-acme", "product-102", "夜里睡觉开着它会有动静吗", {"spec_noise"}),
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
    ("tenant-demo", "product-009", "装的水够不够一次健身喝的", {"spec_capacity"}),
    ("tenant-demo", "product-009", "放包里倒过来会不会漏水", {"spec_leakproof"}),
    ("tenant-demo", "product-009", "杯子是什么材料，装水安全吗", {"spec_material"}),
    ("tenant-demo", "product-010", "冬天贴身穿这一件够不够暖和", {"spec_warm"}),
    ("tenant-demo", "product-010", "能塞在羽绒服里当内搭吗", {"spec_fit"}),
    ("tenant-demo", "product-010", "经常洗会不会缩水变形", {"care"}),
    ("tenant-demo", "product-011", "帽檐够不够宽，能挡住脸不被晒吗", {"spec_brim"}),
    ("tenant-demo", "product-011", "大热天戴着会闷吗", {"spec_vent"}),
    ("tenant-demo", "product-011", "风大一点会不会被吹跑", {"wind_resist"}),
    ("tenant-acme", "product-105", "一瓶能洗多少件衣服", {"spec_capacity"}),
    ("tenant-acme", "product-105", "彩色和深色的衣服会掉色吗", {"color_safe"}),
    ("tenant-acme", "product-105", "洗一次要倒多少", {"spec_dosage"}),
    ("tenant-acme", "product-106", "胡萝卜这种硬的水果能打碎吗", {"spec_power"}),
    ("tenant-acme", "product-106", "榨完能不能拧上盖直接带走", {"spec_cup"}),
    ("tenant-acme", "product-106", "充一次电能打几杯", {"spec_battery"}),
    ("tenant-acme", "product-107", "睡久了中间会不会塌陷", {"spec_firmness"}),
    ("tenant-acme", "product-107", "腰不好的人睡这款合适吗", {"spec_zone"}),
    ("tenant-acme", "product-107", "夏天睡会不会闷得慌", {"spec_breathable"}),
    ("tenant-other", "product-203", "猫上完厕所会自己清吗", {"spec_auto"}),
    ("tenant-other", "product-203", "家里两只猫，一盆够用吗", {"spec_capacity"}),
    ("tenant-other", "product-203", "异味会不会很大", {"spec_odor"}),
    ("tenant-other", "product-204", "能直接拎上飞机不托运吗", {"spec_size"}),
    ("tenant-other", "product-204", "装满东西会不会很重不好搬", {"spec_weight"}),
    ("tenant-other", "product-204", "拉起来轮子顺不顺滑", {"spec_wheels"}),
    ("tenant-demo", "product-005", "太阳很刺眼的时候表盘看得清吗", {"spec_screen"}),
    ("tenant-demo", "product-006", "水箱加满一次能做几杯", {"spec_water"}),
    ("tenant-acme", "product-102", "拦住 PM2.5 靠的是哪一层", {"spec_filter"}),
    ("tenant-acme", "product-103", "睡两个人会不会挤", {"spec_capacity"}),
    ("tenant-demo", "product-001", "这大夏天的穿它，身上会不会跟蒸笼似的啊？", {"spec_season"}),
    (
        "tenant-demo",
        "product-001",
        "这衣服穿身上会不会很闷？料子薄不薄？有弹性不？",
        {"spec_material"},
    ),
    ("tenant-demo", "product-002", "这羽绒服冬天穿抗冻不？里头塞的啥绒啊，厚实不？", {"spec_fill"}),
    (
        "tenant-demo",
        "product-002",
        "这玩意儿扛得住东北大冬天不？会不会冻成冰棍啊？",
        {"spec_season"},
    ),
    ("tenant-demo", "product-003", "这鞋子耐穿不？夏天穿会不会捂得慌啊？", {"spec_material"}),
    (
        "tenant-demo",
        "product-003",
        "这鞋底儿防滑咋样啊？我上次下雨差点出溜倒了，心里阴影老大了。",
        {"spec_sole"},
    ),
    (
        "tenant-demo",
        "product-004",
        "这玩意儿充满一次能用多久？我老忘充电，怕带出去一会儿就没电了。",
        {"spec_battery"},
    ),
    ("tenant-demo", "product-004", "坐地铁或过马路时这耳机能挡住那些吵声不？", {"spec_noise"}),
    (
        "tenant-demo",
        "product-005",
        "这手环是不是能一天到晚都盯着我心跳和血氧啊？不带停的？",
        {"spec_heart"},
    ),
    ("tenant-demo", "product-005", "下水的时候也懒得摘，应该没啥问题吧？", {"spec_waterproof"}),
    (
        "tenant-acme",
        "product-101",
        "这车电满了能跑多少路啊？充一次电得花多长时间？",
        {"spec_battery"},
    ),
    ("tenant-acme", "product-101", "这玩意收起来占地方不？平时挤地铁拎着费劲吗？", {"spec_fold"}),
    (
        "tenant-acme",
        "product-102",
        "这玩意儿过滤效果行不行啊？家里有老人小孩，怕空气里有病菌啥的能挡住不？",
        {"spec_filter"},
    ),
    ("tenant-acme", "product-102", "这净化器除味儿咋样？十来平的屋子够用不？", {"spec_cadr"}),
    (
        "tenant-other",
        "product-201",
        "这个储粮桶一次能装多少斤猫粮哇？我家那只吃货怕不是几天就干完了？",
        {"spec_capacity"},
    ),
    ("tenant-other", "product-201", "这玩意儿一天能设几顿？到点自己出粮不？", {"spec_schedule"}),
    (
        "tenant-demo",
        "product-006",
        "这玩意儿能自己磨豆子吗？磨出来粗细能随便调不？",
        {"spec_grind"},
    ),
    ("tenant-demo", "product-006", "这机器加热快吗？开机等多久能喝上啊？", {"spec_power"}),
    (
        "tenant-demo",
        "product-007",
        "这玩意儿吸地毯上的头发丝能吸干净不？还有边角缝里的灰呢？",
        {"spec_suction"},
    ),
    (
        "tenant-demo",
        "product-007",
        "这机器能自己记住家里啥样不？扫的时候能不能光扫一个房间？而且我住复式，它能自己上下楼不？",
        {"spec_map"},
    ),
    ("tenant-demo", "product-008", "这个腰托能不能调啊？我坐着老是腰酸。", {"spec_lumbar"}),
    ("tenant-demo", "product-008", "这椅子靠背能往后倒不？想累了眯一会儿。", {"spec_recline"}),
    (
        "tenant-acme",
        "product-103",
        "亲，这个帐篷下雨天没事吧？不会外面下大雨里面下小雨吧？",
        {"spec_waterproof"},
    ),
    (
        "tenant-acme",
        "product-103",
        "我们俩一人一个气垫床，塞进去会不会挤得没法转身？",
        {"spec_capacity"},
    ),
    (
        "tenant-acme",
        "product-104",
        "这玩意儿画质到底行不行啊？会不会糊得没法看？",
        {"spec_resolution"},
    ),
    ("tenant-acme", "product-104", "白天不拉窗帘会不会看不清啊？", {"spec_brightness"}),
    (
        "tenant-other",
        "product-202",
        "这玩意儿阻力调节方便不？我刚开始健身，怕买回来以后练一阵子又觉得不够用。",
        {"spec_resistance"},
    ),
    (
        "tenant-other",
        "product-202",
        "这个座子能不能自己调高度和前后啊？我个子矮怕够不着。",
        {"spec_seat"},
    ),
    ("tenant-demo", "product-009", "这壶能装多少啊？我一下午练下来够不够喝？", {"spec_capacity"}),
    (
        "tenant-demo",
        "product-009",
        "这杯子给宝宝用安全不？天天装水喝，心里有点不踏实。",
        {"spec_material"},
    ),
    ("tenant-demo", "product-010", "这衣服贴身穿真的暖和不？有啥特别设计没？", {"spec_warm"}),
    ("tenant-demo", "product-010", "这衣服料子是啥的？穿起来舒服吗？", {"spec_material"}),
    ("tenant-demo", "product-011", "这帽子戴上能挡太阳不？晒不晒脸啊？", {"spec_upf"}),
    ("tenant-demo", "product-011", "这帽子戴上能护住腮帮子和后颈不？太阳挺大的。", {"spec_brim"}),
    ("tenant-acme", "product-105", "这洗衣液洗完衣裳味大不？闻多了会晕不？", {"spec_scent"}),
    ("tenant-acme", "product-105", "这个一次能装多少水啊？差不多能用几回？", {"spec_capacity"}),
    (
        "tenant-acme",
        "product-106",
        "这榨汁机打出来的口感咋样？会不会有渣子卡喉咙啊？",
        {"spec_blade"},
    ),
    ("tenant-acme", "product-106", "榨完还得倒出来换杯子吗？能不能省事儿点？", {"spec_cup"}),
    ("tenant-acme", "product-107", "这款睡久了腰会不得劲吗？", {"spec_firmness"}),
    (
        "tenant-acme",
        "product-107",
        "这个护腰对我这种腰不行的人管用吗？怕戴了跟没戴一样……",
        {"spec_zone"},
    ),
    (
        "tenant-other",
        "product-203",
        "这猫砂是不是猫拉完自己就成一坨坨的，不用我再拿铲子费劲刨？",
        {"spec_auto"},
    ),
    (
        "tenant-other",
        "product-203",
        "两只猫用的话，这个够不够装啊？会不会一下就不行了？",
        {"spec_capacity"},
    ),
    (
        "tenant-other",
        "product-204",
        "这箱子坐飞机能直接拎上去不？还是要单独办托运啊？",
        {"spec_size"},
    ),
    ("tenant-other", "product-204", "这个箱子到底沉不沉啊？我一个人能搬得动不？", {"spec_weight"}),
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
        rank = _rank_of_expected(srcs, exp)
        per_query.append(
            {
                "query": q.get("query", ""),
                "tenant_id": q.get("tenant_id", ""),
                "product_id": q.get("product_id", ""),
                "expected": sorted(exp),
                "rank": rank,
                "recalled": rank is not None,
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


def summarize_failures(report: dict[str, Any]) -> dict[str, Any]:
    """Classify per-query failures into recall (expected not in top-k) vs mis-rank.

    ``recall_failures`` = the expected locator never surfaced in the returned top-k;
    ``misrank_failures`` = it surfaced but not at rank 1. Both are regression signals.
    """
    recall: list[dict[str, Any]] = []
    misrank: list[dict[str, Any]] = []
    for q in report["per_query"]:
        if not q["recalled"]:
            recall.append(q)
        elif q["rank"] != 1:
            misrank.append(q)
    return {
        "recall_failures": len(recall),
        "misrank_failures": len(misrank),
        "n": report["n"],
        "recall_queries": recall,
        "misrank_queries": misrank,
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
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Also print per-query failures (recall vs mis-rank) for regression analysis",
    )
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
    if args.diagnostics:
        summary = summarize_failures(report)
        print(
            json.dumps(
                {
                    "recall_failures": summary["recall_failures"],
                    "misrank_failures": summary["misrank_failures"],
                    "failures": [
                        {
                            "type": "recall" if not q["recalled"] else "misrank",
                            "tenant_id": q["tenant_id"],
                            "product_id": q["product_id"],
                            "query": q["query"],
                            "expected": q["expected"],
                            "rank": q["rank"],
                            "top_sources": q["top_sources"],
                        }
                        for q in report["per_query"]
                        if q["rank"] != 1
                    ],
                },
                ensure_ascii=False,
                indent=2,
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
    "summarize_failures",
]
