"""Offline tests for Hybrid retrieval (dense + BM25 + RRF), fake Milvus."""

from datetime import datetime, timezone

from presale.adapters.external_retrieval import ExternalRetrieval, RetrievalStatus
from presale.adapters.hybrid_retrieval import (
    BM25Index,
    MilvusDense,
    _rrf_weighted,
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


def test_rrf_weighted_equal_scores_break_ties_by_id():
    """Equal RRF scores must order by id so ANN arrival order cannot flap ranks."""

    def hit(source_id: str) -> dict:
        return {"id": f"{source_id}::locator", "source_id": source_id}

    dense = [hit("src-z"), hit("src-a")]
    bm25 = [hit("src-a"), hit("src-z")]
    fused = _rrf_weighted(dense, bm25)
    ids = [h["source_id"] for h in fused]
    assert ids == ["src-a", "src-z"]
    # Swapping input order must not change the fused order.
    fused_swapped = _rrf_weighted(list(reversed(dense)), list(reversed(bm25)))
    assert [h["source_id"] for h in fused_swapped] == ["src-a", "src-z"]


class EmptyMilvus(FakeMilvus):
    """Dense side returns no hits (filtered ANN empty) while BM25 still has data."""

    def search(self, collection_name, data, limit, output_fields, filter=""):
        return [[]]


def test_bm25_search_scopes_tenant_product_before_topk():
    """Scope before top-k: other products must not occupy the result slots."""
    bm25 = BM25Index()
    index_hybrid(
        [
            source(
                source_id="target",
                tenant_id="tenant-acme",
                product_id="product-103",
                fields={"spec": {"capacity": "标称双人，空间可放下两张睡垫"}},
            ),
            source(
                source_id="noise-1",
                tenant_id="tenant-other",
                product_id="product-201",
                fields={"spec": {"capacity": "大容量粮仓 气垫床 挤 转身 画质"}},
            ),
            source(
                source_id="noise-2",
                tenant_id="tenant-demo",
                product_id="product-002",
                fields={"spec": {"waterproof": "气垫床 挤 转身 画质 容量"}},
            ),
        ],
        embedding=fake_embed,
        dense=MilvusDense(collection="presale", dim=2, client=FakeMilvus()),
        bm25=bm25,
    )
    query = "我们俩一人一个气垫床，塞进去会不会挤得没法转身？"

    unscoped = bm25.search(query, 5)
    assert unscoped  # global ranking still available without scope
    scoped = bm25.search(query, 5, tenant_id="tenant-acme", product_id="product-103")
    assert scoped
    assert all(h["tenant_id"] == "tenant-acme" and h["product_id"] == "product-103" for h in scoped)
    assert any(h["locator"] == "spec.capacity" for h in scoped)


def test_hybrid_transport_dense_empty_keeps_product_evidence():
    """Dense empty + global BM25 would wipe the product after top_k trim; scope fixes it."""
    bm25 = BM25Index()
    dense = MilvusDense(collection="presale", dim=2, client=EmptyMilvus())
    index_hybrid(
        [
            source(
                source_id="tent",
                tenant_id="tenant-acme",
                product_id="product-103",
                fields={
                    "spec": {
                        "capacity": "标称双人，空间可放下两张睡垫",
                        "waterproof": "防雨不渗水",
                    }
                },
            ),
            source(
                source_id="filler-a",
                tenant_id="tenant-other",
                product_id="product-201",
                fields={"spec": {"note": "气垫床 挤 转身 容量 双人 睡垫 大容量"}},
            ),
            source(
                source_id="filler-b",
                tenant_id="tenant-demo",
                product_id="product-002",
                fields={"spec": {"note": "气垫床 挤 转身 容量 双人 睡垫"}},
            ),
        ],
        embedding=fake_embed,
        dense=dense,
        bm25=bm25,
    )
    transport = hybrid_transport(embedding=fake_embed, dense=dense, bm25=bm25, top_k=5, pool=15)
    retrieval = ExternalRetrieval(transport=transport)
    q = ProductQuestion(
        question_id="q-dense-empty",
        tenant_id="tenant-acme",
        submitted_by={
            "actor_type": "user",
            "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        },
        product_id="product-103",
        question_text="我们俩一人一个气垫床，塞进去会不会挤得没法转身？",
        requested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        idempotency_key="dense-empty-0001",
    )

    result = retrieval.retrieve(q)

    assert result.status is RetrievalStatus.MATCHED
    assert result.evidence_items
    assert all(
        e.tenant_id == "tenant-acme" and e.product_id == "product-103"
        for e in result.evidence_items
    )
    assert any(e.locator == "spec.capacity" for e in result.evidence_items)
