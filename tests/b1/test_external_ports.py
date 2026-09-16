"""Contract tests for the external-adapter ports (RetrievalPort / GeneratorPort).

These prove the deterministic V1 implementations conform to the port contracts
and that the runner can be wired to an injected implementation, which is the
seam the external-adapter stage (OpenAI-compatible LLM / external retrieval)
plugs into without changing business contracts.
"""

from datetime import datetime, timezone

import pytest

from presale.answer import GeneratorPort, PresaleAnswerGenerator
from presale.contracts import ProductQuestion
from presale.knowledge import (
    DeterministicKnowledgeRetriever,
    KnowledgeSource,
    RetrievalPort,
    RetrievalResult,
    RetrievalStatus,
)
from presale.runner import PresaleQaRunner


def source(
    *, season="适合夏季使用", tenant_id="tenant-demo", product_id="product-001", status="published"
):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id=product_id,
        status=status,
        fields={"spec": {"season": season}},
    )


def question():
    return ProductQuestion(
        question_id="question-port",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        idempotency_key="port-key-000001",
    )


def test_deterministic_retriever_conforms_to_retrieval_port():
    assert issubclass(DeterministicKnowledgeRetriever, RetrievalPort)
    retriever = DeterministicKnowledgeRetriever(
        [source(tenant_id="tenant-other"), source(product_id="product-other")]
    )

    result = retriever.retrieve(question())

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert "OUT_OF_SCOPE" in result.reason_codes
    assert result.evidence_items == []


def test_retrieval_port_returns_only_in_scope_evidence():
    retriever = DeterministicKnowledgeRetriever([source()])

    result = retriever.retrieve(question())

    assert result.status is RetrievalStatus.MATCHED
    assert result.evidence_items
    assert all(item.tenant_id == "tenant-demo" for item in result.evidence_items)
    assert all(item.product_id == "product-001" for item in result.evidence_items)


def test_generator_port_returns_an_answer_draft():
    assert issubclass(PresaleAnswerGenerator, GeneratorPort)
    generator = PresaleAnswerGenerator()
    retrieval = DeterministicKnowledgeRetriever([source()]).retrieve(question())

    draft = generator.generate(
        question(),
        retrieval,
        run_ref={"kind": "AgentRun", "id": "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        configuration_refs={"agent_spec": "1.0.0"},
    )

    assert draft.answer_text
    assert draft.question_id == "question-port"


@pytest.mark.asyncio
async def test_runner_uses_injected_retriever():
    # A custom RetrievalPort drives behavior through the runner: proves the seam
    # the external adapter plugs into without touching business contracts.
    class AlwaysNoEvidenceRetriever(RetrievalPort):
        def retrieve(self, question):
            return RetrievalResult(status=RetrievalStatus.NO_EVIDENCE, reason_codes=["INJECTED"])

    runner = PresaleQaRunner(sources=[source()], retriever=AlwaysNoEvidenceRetriever())

    result = await runner.ask(question())

    assert result.answer_draft.need_human is True
    assert "INJECTED" in result.answer_draft.reason_codes
