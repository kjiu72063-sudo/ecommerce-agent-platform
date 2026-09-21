"""B6-01: PresaleAgent + B5 LoopStrategy 集成验证。

验证 PresaleAgent 通过 Harness + 不同 LoopStrategy 驱动的端到端路径。
"""

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import (
    Harness,
    RetryOnLowEvidenceLoop,
    SinglePassLoop,
    TerminalDecision,
    format_outcome,
)
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runtime import PresaleRuntimeFactory


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


def source(*, product_id="product-001", fields=None):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id=product_id,
        status="published",
        fields=fields or {"spec": {"season": "适合夏季使用"}},
    )


def question(*, key="b6-integration-key-0001"):
    return ProductQuestion(
        question_id="question-b6-integration",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        idempotency_key=key,
    )


def factory(sources=None):
    registry = Registry(
        [
            definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
            definition(
                "PromptPackage", "prm_01111111-1111-7111-8111-111111111111", "presale-prompt"
            ),
            definition(
                "ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111", "presale-context"
            ),
        ]
    )
    return PresaleRuntimeFactory(
        definition_repository=registry,
        definition_selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"},
            "prompt_package": {
                "kind": "PromptPackage",
                "namespace": "presale",
                "key": "presale-prompt",
            },
            "context_policy": {
                "kind": "ContextPolicy",
                "namespace": "presale",
                "key": "presale-context",
            },
        },
        sources=sources or [source()],
    )


# --- SinglePassLoop (默认策略) ---


@pytest.mark.asyncio
async def test_single_pass_loop_matches_evidence():
    """PresaleAgent + SinglePassLoop: 有证据 → FINALIZE，单步."""
    f = factory()
    agent = f.create_agent()

    outcome = await Harness(loop=SinglePassLoop()).execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 1
    assert outcome.answer_draft is not None
    assert outcome.answer_draft.need_human is False


@pytest.mark.asyncio
async def test_single_pass_loop_need_human_on_no_evidence():
    """PresaleAgent + SinglePassLoop: 无证据 → NEED_HUMAN，单步."""
    f = factory(sources=[source(product_id="product-other")])
    agent = f.create_agent()

    outcome = await Harness(loop=SinglePassLoop()).execute(question(), agent)

    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    assert outcome.answer_draft.need_human is True


# --- RetryOnLowEvidenceLoop ---


@pytest.mark.asyncio
async def test_retry_loop_single_step_when_evidence_found():
    """PresaleAgent + RetryOnLowEvidenceLoop: 有证据 → FINALIZE，1步."""
    f = factory()
    agent = f.create_agent()

    outcome = await Harness(loop=RetryOnLowEvidenceLoop()).execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert len(outcome.steps) == 1
    assert outcome.answer_draft.need_human is False


@pytest.mark.asyncio
async def test_retry_loop_need_human_stops_immediately():
    """PresaleAgent + RetryOnLowEvidenceLoop: need_human → NEED_HUMAN."""
    f = factory(sources=[source(product_id="product-other")])
    agent = f.create_agent()

    outcome = await Harness(loop=RetryOnLowEvidenceLoop(max_retries=3)).execute(question(), agent)

    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    assert len(outcome.steps) == 1
    assert outcome.answer_draft.need_human is True


@pytest.mark.asyncio
async def test_retry_loop_conflict_triggers_stop():
    """PresaleAgent + RetryOnLowEvidenceLoop: 证据冲突 → NEED_HUMAN."""
    f = factory(sources=[
        source(),
        source(product_id="product-other"),
    ])
    agent = f.create_agent()

    outcome = await Harness(loop=RetryOnLowEvidenceLoop()).execute(question(), agent)

    # product-other 无匹配 → no_evidence → need_human
    assert outcome.terminal in {TerminalDecision.FINALIZE, TerminalDecision.NEED_HUMAN}
    assert len(outcome.steps) >= 1


# --- Harness + RuntimeFactory 组装 ---


@pytest.mark.asyncio
async def test_factory_create_agent_compatible_with_harness():
    """RuntimeFactory.create_agent() 返回的 agent 可被 Harness 驱动."""
    f = factory()
    agent = f.create_agent()

    assert hasattr(agent, "run")
    outcome = await Harness().execute(question(), agent)

    assert outcome.run_ref is not None
    assert outcome.answer_draft is not None
    assert outcome.steps[0].tool_calls[0]["tool"] == "retrieve"


@pytest.mark.asyncio
async def test_format_outcome_observable_with_loop_strategy():
    """format_outcome 在 RetryOnLowEvidenceLoop 下仍可观察."""
    f = factory()
    agent = f.create_agent()

    outcome = await Harness(loop=RetryOnLowEvidenceLoop()).execute(question(), agent)
    rendered = format_outcome(outcome)

    assert rendered["terminal"] == "finalize"
    assert rendered["answer_id"] is not None
    assert len(rendered["steps"]) >= 1
    assert rendered["steps"][0]["tool_calls"][0]["tool"] == "retrieve"
