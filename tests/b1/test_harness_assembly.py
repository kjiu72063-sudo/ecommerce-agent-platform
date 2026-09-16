"""T05: production assembly creates a Harness-drivable agent, outputs observable."""

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import Harness, TerminalDecision, format_outcome
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


def definition(kind, object_id, key, version="1.0.0"):
    return {
        "kind": kind,
        "metadata": {
            "id": object_id,
            "key": key,
            "namespace": "presale",
            "version": version,
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
        fields={"spec": {"season": "适合夏季使用"}},
    )


def question(*, idempotency_key="assembly-key-0005"):
    return ProductQuestion(
        question_id="question-harness-assembly",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key=idempotency_key,
    )


def factory():
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
        sources=[source()],
    )


@pytest.mark.asyncio
async def test_create_agent_drives_presale_qa_through_harness():
    f = factory()
    agent = f.create_agent()

    outcome = await Harness().execute(question(), agent)

    assert outcome.terminal is TerminalDecision.FINALIZE
    assert outcome.answer_draft is not None
    assert outcome.answer_draft.need_human is False


@pytest.mark.asyncio
async def test_format_outcome_is_observable():
    f = factory()
    outcome = await Harness().execute(question(), f.create_agent())

    rendered = format_outcome(outcome)

    assert rendered["run_ref"] == outcome.run_ref
    assert rendered["terminal"] == "finalize"
    assert rendered["answer_id"] == outcome.answer_draft.answer_id
    assert len(rendered["steps"]) == 1
    assert rendered["steps"][0]["tool_calls"][0]["tool"] == "retrieve"


@pytest.mark.asyncio
async def test_create_runner_remains_usable_directly():
    f = factory()

    runner = f.create_runner()
    result = await runner.ask(question(idempotency_key="assembly-key-0006"))

    assert result.answer_draft.answer_text
    assert result.answer_draft.need_human is False
