"""ReviewAnalyzerAgent: 商品评价分析 Agent.

Analyzes product reviews using deterministic rules (sentiment + keyword
extraction). Demonstrates a second business agent on the platform
besides the presale QA agent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent_runtime.harness import AgentRunResult
from presale.answer import AnswerDraft
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource

# Sentiment keyword dictionaries
_POSITIVE_WORDS = frozenset({
    "好", "棒", "赞", "喜欢", "满意", "推荐", "优秀", "出色", "完美",
    "不错", "舒适", "耐用", "实用", "漂亮", "美观", "精致",
    "方便", "快捷", "高效", "值得", "惊喜", "超值", "良心", "靠谱",
})

_NEGATIVE_WORDS = frozenset({
    "差", "坏", "烂", "失望", "不好", "退货", "退款", "垃圾", "坑",
    "骗", "假", "劣质", "糟糕", "难用", "浪费", "后悔", "问题",
    "故障", "损坏", "缺陷", "投诉", "差评", "不推荐", "不满意",
})

_NEUTRAL_WORDS = frozenset({
    "收到", "已买", "等待", "一般", "普通", "还行", "可以", "正常",
    "未使用", "暂无", "中评",
})


def analyze_review(text: str) -> dict[str, Any]:
    """Deterministic sentiment analysis + keyword extraction.

    Returns:
        {"sentiment": "positive"|"negative"|"neutral", "keywords": [...]}
    """
    pos_count = sum(1 for w in _POSITIVE_WORDS if w in text)
    neg_count = sum(1 for w in _NEGATIVE_WORDS if w in text)
    neu_count = sum(1 for w in _NEUTRAL_WORDS if w in text)

    if pos_count > neg_count and pos_count > neu_count:
        sentiment = "positive"
        word_set = _POSITIVE_WORDS
    elif neg_count > pos_count and neg_count > neu_count:
        sentiment = "negative"
        word_set = _NEGATIVE_WORDS
    else:
        sentiment = "neutral"
        word_set = _NEUTRAL_WORDS

    keywords = [w for w in word_set if w in text]
    return {"sentiment": sentiment, "keywords": keywords}


class ReviewAnalyzerAgent:
    """Analyze product reviews with two tools: retrieve + analyze.

    Uses the Agent protocol so it can be driven by Harness + LoopStrategy.
    """

    def __init__(self, *, sources: list[KnowledgeSource] | None = None):
        self._sources = sources or []

    @staticmethod
    def _make_run_id() -> str:
        import uuid
        value = uuid.uuid4().int
        value = (value & ~(0xF << 76)) | (0x7 << 76)
        value = (value & ~(0x3 << 62)) | (0x2 << 62)
        return f"run_{uuid.UUID(int=value)}"

    async def run(
        self, question: ProductQuestion, step_context=None
    ) -> AgentRunResult:
        tool_calls: list[dict[str, Any]] = []

        # Tool 1: retrieve_knowledge (deterministic)
        evidence = [
            src for src in self._sources
            if src.product_id == question.product_id
        ]
        retrieve_status = "matched" if evidence else "no_evidence"
        tool_calls.append({
            "tool": "retrieve_knowledge",
            "product_id": question.product_id,
            "status": retrieve_status,
            "evidence_count": len(evidence),
        })

        # Tool 2: analyze_review (analyze the question text as a "review")
        analysis = analyze_review(question.question_text)
        tool_calls.append({
            "tool": "analyze_review",
            "sentiment": analysis["sentiment"],
            "keywords": analysis["keywords"],
        })

        # Build answer from analysis
        # Review analysis is a recommendation, always requires human review
        need_human = True
        reason_codes = ["ANALYSIS_RECOMMENDATION"]
        answer_text = (
            f"情感分析：{analysis['sentiment']}。"
            f"关键词：{', '.join(analysis['keywords']) or '无'}。"
        )
        if evidence:
            answer_text += f"参考商品知识：{evidence[0].source_id}。"

        draft = AnswerDraft(
            answer_id="review-draft",
            question_id=question.question_id,
            run_ref={"kind": "AgentRun", "id": self._make_run_id()},
            answer_text=answer_text,
            evidence_refs=[],
            confidence_signal="unavailable",
            need_human=need_human,
            reason_codes=reason_codes,
            configuration_refs={},
            generated_at=datetime.now(timezone.utc),
        )

        return AgentRunResult(
            run_ref="run_review",
            answer_draft=draft,
            need_human=need_human,
            tool_calls=tool_calls,
        )
