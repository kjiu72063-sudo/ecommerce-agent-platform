"""Offline tests for Hybrid retrieval (dense + BM25 + RRF), fake Milvus."""

from datetime import datetime, timezone

from presale.adapters.external_retrieval import ExternalRetrieval, RetrievalStatus
from presale.adapters.hybrid_retrieval import (
    BM25Index,
    MilvusDense,
    hybrid_transport,
    index_hybrid,
)
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource


def fake_embed(text: str) -> list[float]:
    return [1.0, 0.0]


def source(
    *, source_id="catalog-001", tenant_id="tenant-demo", product_id="product-001", fields=None
):
    return KnowledgeSource(
        source_id=source_id,
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id=product_id,
        status="published",
        fields=fields if fields is not None else {"spec": {"season": "适合夏季使用"}},
    )


def question():
    return ProductQuestion(
        question_id="q-hybrid",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        idempotency_key="hybrid-key-0001",
    )


class FakeMilvus:
    def __init__(self):
        self.points = []
        self.created = False

    def has_collection(self, name):
        return self.created

    def create_collection(self, name, dimension):
        self.created = True

    def upsert(self, collection_name, data):
        self.points.extend(data)

    def search(self, collection_name, data, limit, output_fields, filter=""):
        return [[{"entity": {k: p.get(k) for k in output_fields}} for p in self.points[:limit]]]


def test_index_hybrid_populates_milvus_and_bm25():
    fake = FakeMilvus()
    dense = MilvusDense(collection="presale", dim=2, client=fake)
    bm25 = BM25Index()

    count = index_hybrid([source()], embedding=fake_embed, dense=dense, bm25=bm25)

    assert count == 1
    assert fake.points and fake.points[0]["vector"] == [1.0, 0.0]
    hits = bm25.search("适合夏季", 3)
    assert hits and hits[0]["content"] == "适合夏季使用"


def test_hybrid_transport_fuses_dense_and_bm25_into_evidence():
    fake = FakeMilvus()
    dense = MilvusDense(collection="presale", dim=2, client=fake)
    bm25 = BM25Index()
    index_hybrid([source()], embedding=fake_embed, dense=dense, bm25=bm25)

    transport = hybrid_transport(embedding=fake_embed, dense=dense, bm25=bm25)
    retrieval = ExternalRetrieval(transport=transport)

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.MATCHED
    assert result.evidence_items
    assert result.evidence_items[0].source_id == "catalog-001"
    assert result.evidence_items[0].content_digest.startswith("sha256:")


def test_hybrid_transport_applies_reranker():
    fake = FakeMilvus()
    dense = MilvusDense(collection="presale", dim=2, client=fake)
    bm25 = BM25Index()
    s1 = source(source_id="src-a", fields={"spec": {"fruit": "苹果是红色的水果，脆甜"}})
    s2 = source(source_id="src-b", fields={"spec": {"fruit": "香蕉是黄色的水果，软糯"}})
    index_hybrid([s1, s2], embedding=fake_embed, dense=dense, bm25=bm25)

    def promote_b(query, candidates):
        return sorted(candidates, key=lambda c: 0 if c["source_id"] == "src-b" else 1)

    transport = hybrid_transport(embedding=fake_embed, dense=dense, bm25=bm25, reranker=promote_b)
    retrieval = ExternalRetrieval(transport=transport)

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.MATCHED
    assert result.evidence_items and result.evidence_items[0].source_id == "src-b"
