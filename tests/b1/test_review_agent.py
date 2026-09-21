"""D-01/D-02: ReviewAnalyzerAgent + analyze_review tool.

Tests the new review analysis agent that exercises the platform's
multi-agent support with two tools: retrieve_knowledge + analyze_review.
"""

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import Harness, TerminalDecision
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource


class Registry:
    def __init__(self, objects):
        self.objects = objects

    async def list_by_filter(self, filter, limit=100, offset=0):
        return [
            obj
            for obj in self.objects
            if obj["kind"] == filter.kind
            and obj["metadata"]["namespace"] == filter.namespace
            and obj["metadata"]["key"] == filter.key
            and obj["status"]["phase"] == filter.phase
            and obj["metadata"]["scope"]["tenant_id"] == filter.tenant_id
        ]


def definition(kind, object_id, key):
    return {
        "kind": kind,
        "metadata": {
            "id": object_id,
            "key": key,
            "namespace": "presale",
            "version": "1.0.0",
            "content_digest": "sha256:" + "a" * 64,
            "scope": {"type": "tenant", "tenant_id": "tenant-demo"},
        },
        "status": {"phase": "active"},
    }


def source(*, product_id="product-001"):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id=product_id,
        status="published",
        fields={"spec": {"season": "适合夏季使用", "material": "纯棉"}},
    )


def question(*, key="review-key-0001", product_id="product-001"):
    return ProductQuestion(
        question_id="question-review",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_review_001"},
        product_id=product_id,
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        idempotency_key=key,
    )


# --- D-01: ReviewAnalyzerAgent unit tests ---


from review_agent.agent import ReviewAnalyzerAgent, analyze_review


def test_analyze_review_positive():
    """analyze_review detects positive sentiment."""
    result = analyze_review("这个产品非常好用，质量很棒，推荐购买！")
    assert result["sentiment"] == "positive"
    assert len(result["keywords"]) > 0


def test_analyze_review_negative():
    """analyze_review detects negative sentiment."""
    result = analyze_review("产品质量很差，非常失望，不推荐。")
    assert result["sentiment"] == "negative"
    assert len(result["keywords"]) > 0


def test_analyze_review_neutral():
    """analyze_review detects neutral sentiment."""
    result = analyze_review("产品收到，还没使用。")
    assert result["sentiment"] == "neutral"


def test_review_analyzer_agent_implements_protocol():
    """ReviewAnalyzerAgent satisfies the Agent protocol."""
    agent = ReviewAnalyzerAgent(sources=[source()])
    assert hasattr(agent, "run")
    assert callable(agent.run)


@pytest.mark.asyncio
async def test_review_analyzer_agent_run_returns_result():
    """ReviewAnalyzerAgent.run() returns AgentRunResult with tool_calls."""
    from agent_runtime.harness import AgentRunResult

    agent = ReviewAnalyzerAgent(sources=[source()])
    result = await agent.run(question())

    assert isinstance(result, AgentRunResult)
    assert result.run_ref is not None
    assert len(result.tool_calls) >= 1  # at least analyze_review


# --- D-02: Integration tests ---


@pytest.mark.asyncio
async def test_review_analyzer_single_pass_loop():
    """ReviewAnalyzerAgent + SinglePassLoop → NEED_HUMAN (always needs review)."""
    agent = ReviewAnalyzerAgent(sources=[source()])
    outcome = await Harness().execute(question(), agent)

    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    assert outcome.answer_draft is not None
    assert outcome.answer_draft.need_human is True
    assert len(outcome.steps) == 1
    # Two tools called: retrieve_knowledge + analyze_review
    assert len(outcome.steps[0].tool_calls) == 2
    assert outcome.steps[0].tool_calls[0]["tool"] == "retrieve_knowledge"
    assert outcome.steps[0].tool_calls[1]["tool"] == "analyze_review"


@pytest.mark.asyncio
async def test_review_analyzer_need_human_without_evidence():
    """ReviewAnalyzerAgent without matching source → NEED_HUMAN."""
    agent = ReviewAnalyzerAgent(sources=[])
    outcome = await Harness().execute(question(), agent)

    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    assert outcome.answer_draft.need_human is True
    assert "ANALYSIS_RECOMMENDATION" in outcome.answer_draft.reason_codes


@pytest.mark.asyncio
async def test_review_analyzer_format_outcome():
    """format_outcome renders ReviewAnalyzerAgent results."""
    from agent_runtime.harness import format_outcome

    agent = ReviewAnalyzerAgent(sources=[source()])
    outcome = await Harness().execute(question(), agent)
    rendered = format_outcome(outcome)

    assert rendered["terminal"] == "need_human"
    assert rendered["answer_id"] is not None
    assert rendered["answer_text"] is not None
    assert len(rendered["steps"]) == 1
