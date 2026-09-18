"""Real-Milvus Hybrid RAG integration test.

Skipped unless ``MILVUS_INTEGRATION=1`` is set (the CI gate job does not set it, so
it is collection-time skipped there; the ``milvus-integration`` CI job sets it and
runs against a real Milvus 2.4 standalone service container).

Expects env: ``PRESALE_MILVUS_URI`` (default ``http://127.0.0.1:19530``),
optionally ``PRESALE_EMBEDDING`` (default deterministic) and
``PRESALE_MILVUS_COLLECTION`` (default ``presale_hybrid``).
"""

import os
from datetime import datetime, timezone

import pytest

from presale.adapters.external_retrieval import RetrievalStatus
from presale.adapters.hybrid_retrieval import hybrid_retriever_from_env
from presale.contracts import ProductQuestion

pytestmark = pytest.mark.skipif(
    not os.environ.get("MILVUS_INTEGRATION"),
    reason="set MILVUS_INTEGRATION=1 with a real Milvus at PRESALE_MILVUS_URI",
)

URI = os.environ.get("PRESALE_MILVUS_URI", "http://127.0.0.1:19530")
TENANT = "tenant-demo"
PRODUCT = "product-001"


@pytest.fixture(scope="module")
def retriever():
    os.environ.setdefault("PRESALE_EMBEDDING", "deterministic")
    os.environ.setdefault("PRESALE_MILVUS_URI", URI)
    os.environ.setdefault("PRESALE_MILVUS_COLLECTION", "presale_hybrid")
    os.environ.setdefault("PRESALE_CATALOG", "src/presale/data/sample_catalog.json")
    retriever = hybrid_retriever_from_env()
    assert retriever is not None, f"PRESALE_MILVUS_URI={os.environ.get('PRESALE_MILVUS_URI')}"
    return retriever


def _question(tenant: str, product: str, text: str) -> ProductQuestion:
    return ProductQuestion(
        question_id="q-milvus-int-0001",
        tenant_id=tenant,
        submitted_by={"actor_type": "user", "actor_id": "usr_milvus_int_0001"},
        product_id=product,
        question_text=text,
        requested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        idempotency_key="milvus-int-0001",
    )


def test_real_hybrid_retrieval_matches_correct_tenant(retriever):
    result = retriever.retrieve(_question(TENANT, PRODUCT, "这款商品适合夏季使用吗？"))

    assert result.status is RetrievalStatus.MATCHED
    assert result.evidence_items, "expected fused dense+BM25 evidence"
    assert all(item.tenant_id == TENANT for item in result.evidence_items)
    assert all(item.product_id == PRODUCT for item in result.evidence_items)


def test_real_hybrid_no_cross_tenant_leak(retriever):
    result = retriever.retrieve(_question("tenant-other", PRODUCT, "这款商品适合夏季使用吗？"))

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert not result.evidence_items


def test_real_hybrid_no_cross_product_leak(retriever):
    result = retriever.retrieve(_question(TENANT, "product-999", "这款商品适合夏季使用吗？"))

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert not result.evidence_items
