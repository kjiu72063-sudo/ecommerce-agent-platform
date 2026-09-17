"""Qdrant-backed external retrieval: LLM embedding + search transport + indexing.

Connects the presale ``ExternalRetrieval`` port to a local Qdrant (Docker) store.
The search query is embedded via the LLM provider's OpenAI-compatible
``/embeddings`` endpoint, then a Qdrant vector search scoped by tenant_id and
product_id returns evidence payloads that satisfy the existing
``{"items":[...]}`` transport contract.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import httpx

from .external_retrieval import ExternalRetrieval, RetrievalError

Embedding = Callable[[str], list[float]]


def _flatten(fields: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, value in fields.items():
        locator = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.extend(_flatten(value, locator))
        elif isinstance(value, str) and value.strip():
            out.append((locator, value.strip()))
    return out


def _embed(base_url: str, model: str, api_key: str, text: str) -> list[float]:
    url = base_url.rstrip("/") + "/embeddings"
    payload = {"model": model, "input": text}
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    return data["data"][0]["embedding"]


def embedding_from_env() -> Embedding:
    """Build an embedding callable from env (LLM provider's /embeddings endpoint).

    Falls back to PRESALE_LLM_* when dedicated PRESALE_EMBEDDING_* vars are unset.
    """
    base_url = os.environ.get("PRESALE_EMBEDDING_BASE_URL") or os.environ.get(
        "PRESALE_LLM_BASE_URL"
    )
    model = os.environ.get("PRESALE_EMBEDDING_MODEL") or os.environ.get("PRESALE_LLM_MODEL")
    api_key = os.environ.get("PRESALE_EMBEDDING_API_KEY") or os.environ.get("PRESALE_LLM_API_KEY")
    if not (base_url and model and api_key):
        raise RetrievalError("EMBEDDING_NOT_CONFIGURED: set PRESALE_LLM_* or PRESALE_EMBEDDING_*")
    return lambda text: _embed(base_url, model, api_key, text)


def qdrant_transport(
    *,
    embedding: Embedding,
    base_url: str,
    collection: str,
    top_k: int = 5,
    client: httpx.Client | None = None,
) -> Callable[..., list[dict[str, Any]]]:
    """Build an ExternalRetrieval transport that embeds the query and searches Qdrant."""

    def transport(
        *, tenant_id: str, product_id: str, query: str, timeout_s: float
    ) -> list[dict[str, Any]]:
        vector = embedding(query)
        payload = {
            "vector": vector,
            "limit": top_k,
            "filter": {
                "must": [
                    {"key": "tenant_id", "match": {"value": tenant_id}},
                    {"key": "product_id", "match": {"value": product_id}},
                ]
            },
            "with_payload": True,
        }
        url = base_url.rstrip("/") + f"/collections/{collection}/points/search"
        http = client or httpx.Client(timeout=timeout_s)
        try:
            response = http.post(url, json=payload)
            response.raise_for_status()
            hits = response.json()["result"]
        finally:
            if client is None:
                http.close()
        return [hit["payload"] for hit in hits]

    return transport


def qdrant_retriever_from_env() -> ExternalRetrieval | None:
    """Build an ExternalRetrieval backed by Qdrant when PRESALE_QDRANT_URL is set."""
    base_url = os.environ.get("PRESALE_QDRANT_URL")
    if not base_url:
        return None
    collection = os.environ.get("PRESALE_QDRANT_COLLECTION", "presale")
    return ExternalRetrieval(
        transport=qdrant_transport(
            embedding=embedding_from_env(), base_url=base_url, collection=collection
        )
    )


def index_sources(
    sources: list[Any],
    *,
    embedding: Embedding,
    base_url: str,
    collection: str,
    client: httpx.Client | None = None,
    batch_size: int = 64,
) -> int:
    """Vectorize each source field fragment and upsert it into Qdrant.

    Returns the number of points written. Each point's payload carries the
    fields ExternalRetrieval expects (source_id/version/locator/content) plus
    tenant_id/product_id for scoped search.
    """
    points: list[dict[str, Any]] = []
    vector_size: int | None = None
    for source in sources:
        for locator, content in _flatten(source.fields):
            vector = embedding(f"{locator} {content}")
            if vector_size is None:
                vector_size = len(vector)
            points.append(
                {
                    "id": f"{source.source_id}:{source.version}:{locator}",
                    "vector": vector,
                    "payload": {
                        "source_id": source.source_id,
                        "source_version": source.version,
                        "locator": locator,
                        "content": content,
                        "tenant_id": source.tenant_id,
                        "product_id": source.product_id,
                    },
                }
            )
    if not points or vector_size is None:
        return 0

    http = client or httpx.Client(timeout=30.0)
    try:
        http.put(
            base_url.rstrip("/") + f"/collections/{collection}",
            json={"vectors": {"size": vector_size, "distance": "Cosine"}},
        )
        for start in range(0, len(points), batch_size):
            _upsert(http, base_url, collection, points[start : start + batch_size])
    finally:
        if client is None:
            http.close()
    return len(points)


def _upsert(
    http: httpx.Client, base_url: str, collection: str, points: list[dict[str, Any]]
) -> None:
    resp = http.put(
        base_url.rstrip("/") + f"/collections/{collection}/points",
        json={"points": points},
    )
    resp.raise_for_status()


def main(argv: list[str] | None = None) -> None:
    """Index a catalog JSON into Qdrant. Uses PRESALE_CATALOG + Qdrant env vars."""
    import argparse

    from ..cli import load_catalog

    parser = argparse.ArgumentParser(
        prog="presale-index", description="Vectorize catalog KnowledgeSource into Qdrant."
    )
    parser.add_argument(
        "catalog", help="Path to catalog JSON (or leave unset to use PRESALE_CATALOG)"
    )
    args = parser.parse_args(argv)
    catalog = args.catalog or os.environ.get("PRESALE_CATALOG")
    if not catalog:
        raise SystemExit("catalog path required (arg or PRESALE_CATALOG)")
    base_url = os.environ.get("PRESALE_QDRANT_URL")
    if not base_url:
        raise SystemExit("PRESALE_QDRANT_URL required")
    collection = os.environ.get("PRESALE_QDRANT_COLLECTION", "presale")
    sources = load_catalog(catalog)
    count = index_sources(
        sources, embedding=embedding_from_env(), base_url=base_url, collection=collection
    )
    print(f"indexed {count} points into {collection} at {base_url}")


__all__ = [
    "embedding_from_env",
    "index_sources",
    "main",
    "qdrant_retriever_from_env",
    "qdrant_transport",
]
