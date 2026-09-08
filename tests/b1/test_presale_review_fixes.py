from datetime import datetime, timezone

import pytest

from presale.answer import PresaleAnswerGenerator
from presale.contracts import ProductQuestion
from presale.knowledge import DeterministicKnowledgeRetriever, KnowledgeSource, RetrievalStatus
from presale.runner import PresaleQaRunner
from presale.trace import TraceError


def question(text="这款商品适合夏季使用吗？", tenant_id="tenant-demo"):
    return ProductQuestion(
        question_id="question-review",
        tenant_id=tenant_id,
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text=text,
        requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        idempotency_key="review-key-001",
    )


def source(season="适合四季使用"):
    return KnowledgeSource(
        source_id="catalog-review",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id="product-001",
        status="published",
        fields={"spec": {"season": season}},
    )


def test_trace_lookup_requires_matching_tenant():
    runner = PresaleQaRunner(
        sources=[KnowledgeSource(
            source_id="catalog-review",
            version="2026.09.01",
            tenant_id="tenant-demo",
            product_id="product-001",
            status="published",
            fields={"spec": {"season": "适合夏季使用"}},
        )]
    )
    result = runner.ask(question("这款商品适合夏季使用吗？"))

    with pytest.raises(TraceError, match="TENANT_ID_REQUIRED"):
        runner.get_trace(result.run_ref)

    with pytest.raises(TraceError, match="OUT_OF_SCOPE"):
        runner.get_trace(result.run_ref, tenant_id="tenant-other")

    trace = runner.get_trace(result.run_ref, tenant_id="tenant-demo")
    assert trace.run_ref == result.run_ref


def test_retrieval_does_not_treat_one_bridging_bigram_as_evidence():
    result = DeterministicKnowledgeRetriever([source()]).retrieve(question())

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert result.evidence_items == []


def test_realtime_terms_keep_conservative_human_review_boundary():
    question_with_realtime_intent = question("现在还有库存吗？")
    result = DeterministicKnowledgeRetriever([source("库存充足")]).retrieve(
        question_with_realtime_intent
    )
    draft = PresaleAnswerGenerator().generate(
        question_with_realtime_intent,
        result,
        run_ref={"kind": "AgentRun", "id": "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        configuration_refs={},
    )

    assert draft.need_human is True
    assert "REAL_TIME_DATA" in draft.reason_codes
