"""Offline tests for the Qdrant-backed external retrieval (fake transport)."""

from datetime import datetime, timezone

import httpx
import pytest

from presale.adapters.external_retrieval import ExternalRetrieval
from presale.adapters.qdrant_retrieval import (
    embedding_from_env,
    index_sources,
    qdrant_transport,
)
from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource, RetrievalStatus


def vectorize(text: str) -> list[float]:
    return [float(len(text)), 1.5]  # deterministic fake embedding (2 dims)


def question():
    return ProductQuestion(
        question_id="q-retrieval",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 18, tzinfo=timezone.utc),
        idempotency_key="retrieval-key-0001",
    )


def source(*, source_id="catalog-001", tenant_id="tenant-demo", product_id="product-001"):
    return KnowledgeSource(
        source_id=source_id,
        version="2026.09.01",
        tenant_id=tenant_id,
        product_id=product_id,
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


def qdrant_search_handler(hits):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/points/search"):
            return httpx.Response(200, json={"result": [{"payload": h} for h in hits]})
        if request.url.path.endswith("/points") and request.method == "PUT":
            return httpx.Response(200, json={"result": {"status": "ok"}})
        if "/collections/" in request.url.path and request.method == "PUT":
            return httpx.Response(200, json={"result": True})
        return httpx.Response(200, json={})

    return handler


def test_qdrant_search_maps_hits_to_scoped_evidence():
    hits = [
        {
            "source_id": "ext-q1",
            "source_version": "2026.09",
            "locator": "spec.season",
            "content": "适合夏季使用",
            "tenant_id": "tenant-demo",
            "product_id": "product-001",
        }
    ]
    client = httpx.Client(transport=httpx.MockTransport(qdrant_search_handler(hits)))
    transport = qdrant_transport(
        embedding=vectorize, base_url="http://qdrant:6333", collection="presale", client=client
    )
    retrieval = ExternalRetrieval(transport=transport)

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.MATCHED
    assert result.evidence_items[0].source_id == "ext-q1"
    assert result.evidence_items[0].content_digest.startswith("sha256:")
    client.close()


def test_qdrant_search_sends_scoped_filter():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"result": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transport = qdrant_transport(
        embedding=vectorize, base_url="http://qdrant:6333", collection="presale", client=client
    )
    retrieval = ExternalRetrieval(transport=transport)

    result = retrieval.retrieve(question())

    assert result.status is RetrievalStatus.NO_EVIDENCE
    assert '"tenant_id"' in seen["body"] and '"tenant-demo"' in seen["body"]
    assert '"product_id"' in seen["body"] and '"product-001"' in seen["body"]
    client.close()


def test_index_sources_embeds_and_upserts():
    writes = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/points") and request.method == "PUT":
            body = request.read().decode()
            writes.append(len(body))
            return httpx.Response(200, json={"result": {"status": "ok"}})
        return httpx.Response(200, json={"result": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    count = index_sources(
        [source()],
        embedding=vectorize,
        base_url="http://qdrant:6333",
        collection="presale",
        client=client,
        batch_size=64,
    )

    assert count == 1  # one field fragment (spec.season)
    assert writes  # an upsert HTTP request was sent
    client.close()


def test_embedding_from_env_resolves_when_configured(monkeypatch):
    monkeypatch.setenv("PRESALE_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("PRESALE_LLM_MODEL", "m")
    monkeypatch.setenv("PRESALE_LLM_API_KEY", "k")

    fn = embedding_from_env()

    assert callable(fn)
