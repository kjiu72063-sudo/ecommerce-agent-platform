"""Contract tests for ExternalRetrieval (offline, injected transport)."""

from datetime import datetime, timezone

import pytest

from presale.adapters.external_retrieval import ExternalRetrieval, RetrievalError
from presale.contracts import ProductQuestion
from presale.knowledge import (
    DeterministicKnowledgeRetriever,
    KnowledgeSource,
    RetrievalPort,
    RetrievalResult,
    RetrievalStatus,
)


def source(*, tenant_id="tenant-demo", product_id="product-001"):
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id=product_id,
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def question():
    return ProductQuestion(
        question_id="question-ext",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key="ext-key-000003",
    )


def ev(
    *,
    source_id="ext-001",
    content="适合夏季使用",
    tenant_id="tenant-demo",
    product_id="product-001",
):
    return {
        "source_id": source_id,
        "source_version": "2026.09",
        "locator": "spec.season",
        "content": content,
        "tenant_id": tenant_id,
        "product_id": product_id,
    }


def fake_transport(results, captured=None):
    def _transport(*, query, tenant_id, product_id, timeout_s):
        if captured is not None:
            captured.update({"query": query, "tenant_id": tenant_id, "product_id": product_id})
        return results

    return _transport


def test_external_retrieval_conforms_to_retrieval_port():
    assert issubclass(ExternalRetrieval, RetrievalPort)


def test_transport_results_map_to_scoped_matched_evidence():
    captured = {}
    retrieval = ExternalRetrieval(transport=fake_transport([ev()], captured=captured))

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.MATCHED
    assert "EXTERNAL_RETRIEVAL" in result.reason_codes
    assert len(result.evidence_items) == 1
    assert result.evidence_items[0].source_id == "ext-001"
    assert result.evidence_items[0].tenant_id == "tenant-demo"
    assert captured["query"] == "这款商品适合夏季使用吗？"


def test_empty_transport_is_no_evidence():
    retrieval = ExternalRetrieval(transport=fake_transport([]))

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert "EXTERNAL_NO_EVIDENCE" in result.reason_codes


def test_cross_tenant_evidence_is_never_leaked():
    retrieval = ExternalRetrieval(
        transport=fake_transport([ev(tenant_id="tenant-other"), ev(product_id="product-other")])
    )

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert result.evidence_items == []


def test_transport_failure_without_fallback_raises():
    def boom(*, query, tenant_id, product_id, timeout_s):
        raise RuntimeError("search service down")

    with pytest.raises(RetrievalError, match="RETRIEVAL_CALL_FAILED"):
        ExternalRetrieval(transport=boom).retrieve(question())


def test_transport_failure_with_fallback_degrades():
    def boom(*, query, tenant_id, product_id, timeout_s):
        raise RuntimeError("search service down")

    fallback = DeterministicKnowledgeRetriever([source()])
    retrieval = ExternalRetrieval(transport=boom, fallback=fallback)

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.MATCHED
    assert "RETRIEVAL_DEGRADED" in result.reason_codes


def test_unconfigured_transport_is_explicit(monkeypatch):
    monkeypatch.delenv("PRESALE_RETRIEVAL_BASE_URL", raising=False)
    with pytest.raises(RetrievalError, match="RETRIEVAL_NOT_CONFIGURED"):
        ExternalRetrieval().retrieve(question())


@pytest.mark.asyncio
async def test_external_retrieval_plugs_into_runner():
    from presale.runner import PresaleQaRunner

    retrieval = ExternalRetrieval(transport=fake_transport([ev()]))
    runner = PresaleQaRunner(sources=[source()], retriever=retrieval)

    result = await runner.ask(question())

    assert result.answer_draft.evidence_refs
    assert result.answer_draft.evidence_refs[0].source_id == "ext-001"
    assert result.answer_draft.need_human is False
