from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from presale.contracts import ProductQuestion
from presale.knowledge import (
    DeterministicKnowledgeRetriever,
    KnowledgeSource,
    RetrievalStatus,
)

QUESTION = ProductQuestion(
    question_id="question-001",
    tenant_id="tenant-demo",
    submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    product_id="product-001",
    question_text="这款商品适合夏季使用吗？",
    requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    idempotency_key="question-001-key",
)


def source(
    *,
    source_id="catalog-001",
    version="2026.09.01",
    tenant_id="tenant-demo",
    product_id="product-001",
    season="适合夏季使用",
    status="published",
):
    return KnowledgeSource(
        source_id=source_id,
        version=version,
        tenant_id=tenant_id,
        product_id=product_id,
        status=status,
        fields={"spec": {"season": season, "material": "轻量透气面料"}},
    )


def test_retrieval_returns_reproducible_field_level_evidence():
    retriever = DeterministicKnowledgeRetriever([source()])

    first = retriever.retrieve(QUESTION)
    second = retriever.retrieve(QUESTION)

    assert first.status is RetrievalStatus.MATCHED
    assert first.evidence_items[0].locator == "spec.season"
    assert first.evidence_items[0].source_id == "catalog-001"
    assert first.evidence_items[0].source_version == "2026.09.01"
    assert first.evidence_items[0].product_id == "product-001"
    assert first.evidence_items[0].tenant_id == "tenant-demo"
    assert first.evidence_items[0].content_digest == second.evidence_items[0].content_digest


def test_retrieval_ignores_unpublished_sources():
    retriever = DeterministicKnowledgeRetriever([source(status="draft")])

    result = retriever.retrieve(QUESTION)

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert result.evidence_items == []


def test_retrieval_rejects_cross_tenant_or_cross_product_sources():
    retriever = DeterministicKnowledgeRetriever(
        [source(tenant_id="tenant-other"), source(product_id="product-other")]
    )

    result = retriever.retrieve(QUESTION)

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert result.evidence_items == []
    assert "OUT_OF_SCOPE" in result.reason_codes


def test_retrieval_reports_no_evidence_explicitly():
    retriever = DeterministicKnowledgeRetriever(
        [source(season="仅适合室内收纳", source_id="catalog-002")]
    )

    result = retriever.retrieve(QUESTION)

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert result.evidence_items == []
    assert "NO_EVIDENCE" in result.reason_codes


def test_retrieval_reports_conflicting_sources_for_same_field():
    retriever = DeterministicKnowledgeRetriever(
        [
            source(source_id="catalog-001", season="适合夏季使用"),
            source(source_id="catalog-002", season="不适合夏季使用"),
        ]
    )

    result = retriever.retrieve(QUESTION)

    assert result.status is RetrievalStatus.CONFLICT
    assert len(result.evidence_items) == 2
    assert {item.locator for item in result.evidence_items} == {"spec.season"}
    assert "CONFLICTING_EVIDENCE" in result.reason_codes


def test_knowledge_source_requires_published_versioned_scope():
    with pytest.raises(ValidationError):
        KnowledgeSource(
            source_id="catalog-001",
            version="",
            tenant_id="tenant-demo",
            product_id="product-001",
            status="published",
            fields={"spec": {"season": "适合夏季使用"}},
        )
