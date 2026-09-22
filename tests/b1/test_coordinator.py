"""MA-01/MA-02: AgentCoordinator multi-agent orchestration contract tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_runtime.coordinator import (
    AgentCoordinator,
    CoordinatorOutcome,
    format_coordinator_outcome,
)
from agent_runtime.harness import AgentRunResult, TerminalDecision
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runtime import PresaleRuntimeFactory
from review_agent.agent import ReviewAnalyzerAgent


class FakeAgent:
    """Scripted agent: returns configured need_human / answer per call."""

    def __init__(self, *, need_human=False, answer="fake answer", raise_on=None):
        self._need_human = need_human
        self._answer = answer
        self._raise_on = raise_on
        self.calls = 0

    async def run(self, question, step_context=None):
        self.calls += 1
        if self._raise_on is not None and self.calls >= self._raise_on:
            raise RuntimeError("agent boom")
        draft = type(
            "D",
            (),
            {
                "answer_id": f"ans-{self.calls}",
                "answer_text": self._answer,
                "need_human": self._need_human,
            },
        )
        result = AgentRunResult(run_ref=f"run-{self.calls}", need_human=self._need_human)
        # attach answer_text via a real answer_draft attribute used by coordinator
        result.answer_draft = draft
        return result

    @property
    def last_input(self):
        return self._last_input

    async def run_tracked(self, question, step_context=None):
        self._last_input = question
        return await self.run(question, step_context=step_context)


class AlwaysFinalizeLoop:
    def decide(self, step):
        from agent_runtime.harness import LoopDecision

        return LoopDecision.NEED_HUMAN if step.need_human else LoopDecision.FINALIZE


def _draft(text: str, need_human: bool = False):
    return type(
        "D",
        (),
        {"answer_id": f"ans-{text[:4]}", "answer_text": text, "need_human": need_human},
    )


class RecordingAgent:
    """Records the question it received, returns a fixed answer."""

    def __init__(self, answer="ok", need_human=False):
        self._answer = answer
        self._need_human = need_human
        self.received = None

    async def run(self, question, step_context=None):
        self.received = question
        draft = _draft(self._answer, self._need_human)
        result = AgentRunResult(run_ref="run-x", need_human=self._need_human)
        result.answer_draft = draft
        return result


# --- MA-01: AgentCoordinator core ---


@pytest.mark.asyncio
async def test_coordinator_runs_two_agents_in_order():
    """MA-01: two agents both run, in order."""
    a1, a2 = RecordingAgent("one"), RecordingAgent("two")
    coordinator = AgentCoordinator([a1, a2])

    outcome = await coordinator.execute("q")

    assert isinstance(outcome, CoordinatorOutcome)
    assert len(outcome.sub_outcomes) == 2
    assert a1.received == "q"
    assert outcome.overall_terminal is TerminalDecision.FINALIZE


@pytest.mark.asyncio
async def test_coordinator_short_circuits_on_need_human():
    """MA-01: first agent need_human -> second not run."""
    a1 = RecordingAgent(need_human=True)
    a2 = RecordingAgent()
    coordinator = AgentCoordinator([a1, a2])

    outcome = await coordinator.execute("q")

    assert len(outcome.sub_outcomes) == 1
    assert a2.received is None
    assert outcome.overall_terminal is TerminalDecision.NEED_HUMAN


@pytest.mark.asyncio
async def test_coordinator_single_agent_equivalent_to_harness():
    """MA-01: one agent behaves like a plain Harness run."""
    a = RecordingAgent("solo")
    coordinator = AgentCoordinator([a])

    outcome = await coordinator.execute("q")

    assert len(outcome.sub_outcomes) == 1
    assert outcome.overall_terminal is TerminalDecision.FINALIZE
    assert outcome.sub_outcomes[0].terminal is TerminalDecision.FINALIZE


@pytest.mark.asyncio
async def test_coordinator_agent_exception_propagates():
    """MA-01: an agent raising propagates to the caller."""
    a1 = RecordingAgent()
    a2 = FakeAgent(raise_on=1)
    coordinator = AgentCoordinator([a1, a2])

    with pytest.raises(RuntimeError, match="agent boom"):
        await coordinator.execute("q")


@pytest.mark.asyncio
async def test_coordinator_empty_agents_raises():
    """MA-01: coordinator with no agents is invalid."""
    with pytest.raises(ValueError):
        AgentCoordinator([])


# --- MA-02: result passing + observable output ---


@pytest.mark.asyncio
async def test_coordinator_passes_answer_text_to_next():
    """MA-02: second agent receives first agent's answer_text as question."""
    a1 = RecordingAgent("first-answer")
    a2 = RecordingAgent()
    coordinator = AgentCoordinator([a1, a2])

    await coordinator.execute("q")

    assert a2.received == "first-answer"


@pytest.mark.asyncio
async def test_coordinator_first_agent_no_draft_uses_original_question():
    """MA-02: when first agent yields no draft, second gets original question."""

    class NoDraftAgent(RecordingAgent):
        async def run(self, question, step_context=None):
            self.received = question
            result = AgentRunResult(run_ref="run-x", need_human=False)
            return result  # no answer_draft

    a1 = NoDraftAgent()
    a2 = RecordingAgent()
    coordinator = AgentCoordinator([a1, a2])

    await coordinator.execute("q")

    assert a2.received == "q"  # fell back to original question


@pytest.mark.asyncio
async def test_format_coordinator_outcome():
    """MA-02: format_coordinator_outcome renders a JSON-able dict."""
    a1 = RecordingAgent("first-answer", need_human=True)
    coordinator = AgentCoordinator([a1])

    outcome = await coordinator.execute("q")
    rendered = format_coordinator_outcome(outcome)

    assert rendered["overall_terminal"] == "need_human"
    assert len(rendered["sub_outcomes"]) == 1
    assert rendered["sub_outcomes"][0]["terminal"] == "need_human"


# --- MA-02: Presale -> Review end-to-end ---


class _Registry:
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


def _definition(kind, object_id, key):
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


def _factory():
    registry = _Registry(
        [
            _definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
            _definition(
                "PromptPackage", "prm_01111111-1111-7111-8111-111111111111", "presale-prompt"
            ),
            _definition(
                "ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111", "presale-context"
            ),
        ]
    )
    sources = [
        KnowledgeSource(
            source_id="catalog-001",
            version="2026.09.01",
            tenant_id="tenant-demo",
            product_id="product-001",
            status="published",
            fields={"spec": {"season": "适合夏季使用", "material": "纯棉"}},
        )
    ]
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
        sources=sources,
    ), sources


def _question(key="coord-key-0001"):
    return ProductQuestion(
        question_id="question-coord",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_coord_001"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_presale_then_review_agents_end_to_end():
    """MA-02: PresaleAgent -> ReviewAnalyzerAgent pipeline runs and passes answer_text."""
    f, sources = _factory()
    presale = f.create_agent()
    review = ReviewAnalyzerAgent(sources=sources)

    coordinator = AgentCoordinator([presale, review])
    outcome = await coordinator.execute(_question())

    assert len(outcome.sub_outcomes) == 2
    # Review agent received the presale answer text as a bare string (no product
    # context) -> no evidence -> needs human review, which short-circuits.
    assert outcome.overall_terminal is TerminalDecision.NEED_HUMAN
    # Review agent analyzed the presale answer text
    second_steps = outcome.sub_outcomes[1].steps
    assert second_steps[0].tool_calls[1]["tool"] == "analyze_review"
