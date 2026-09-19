"""Hybrid retrieval (dense + BM25 + reciprocal rank fusion) for the presale slice.

Connects the presale ``ExternalRetrieval`` port to a Hybrid RAG: a local
sentence-transformers embedding (bge-large-zh-v1.5), a Milvus dense store, and an
in-process BM25 (rank_bm25) index, fused by Reciprocal Rank Fusion. The Milvus
client and embedding are injectable so the logic is testable offline; real
pymilvus / sentence-transformers are only imported when actually constructed.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, Callable

from .external_retrieval import ExternalRetrieval, RetrievalError

Embedding = Callable[[str], list[float]]

_CJK = re.compile(r"[\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    """CJK-aware tokenizer: whitespace words + CJK char-level tokens."""
    tokens: list[str] = []
    for word in text.lower().split():
        for part in re.split(r"([\u4e00-\u9fff]+)", word):
            if not part:
                continue
            if _CJK.fullmatch(part):
                tokens.extend(part)  # char-level for Chinese
            else:
                tokens.append(part)
    return tokens


def _flatten(fields: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, value in fields.items():
        locator = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.extend(_flatten(value, locator))
        elif isinstance(value, str) and value.strip():
            out.append((locator, value.strip()))
    return out


class SentenceTransformerEmbedding:
    """Lazy local embedding via sentence-transformers (bge-large-zh-v1.5)."""

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or os.environ.get(
            "PRESALE_EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5"
        )
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import (  # pyright: ignore[reportMissingImports]
                    SentenceTransformer,
                )
            except ImportError as exc:
                raise RetrievalError(
                    "SENTENCE_TRANSFORMERS_NOT_INSTALLED: pip install sentence-transformers"
                ) from exc
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def __call__(self, text: str) -> list[float]:
        return self._load().encode(text, normalize_embeddings=True).tolist()


class CrossEncoderReranker:
    """Cross-encoder reranker (sentence-transformers CrossEncoder).

    Re-scores candidate chunks against the query jointly to refine the fused ranking.
    ``model_name`` may be a HF repo id or a local directory (loaded offline).
    """

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or os.environ.get(
            "PRESALE_RERANKER_MODEL", "BAAI/bge-reranker-base"
        )
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import (  # pyright: ignore[reportMissingImports]
                    CrossEncoder,
                )
            except ImportError as exc:
                raise RetrievalError(
                    "SENTENCE_TRANSFORMERS_NOT_INSTALLED: uv sync --extra embedding"
                ) from exc
            self._model = CrossEncoder(self._model_name)
        return self._model

    def __call__(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return candidates
        scores = self._load().predict([(query, c["content"]) for c in candidates])
        order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
        return [candidates[i] for i in order]


class BM25Index:
    """In-process BM25 (rank_bm25) over chunk texts, keeping payloads."""

    def __init__(self):
        self._texts: list[str] = []
        self._payloads: list[dict[str, Any]] = []
        self._bm25 = None

    def add(self, texts: list[str], payloads: list[dict[str, Any]]) -> None:
        from rank_bm25 import BM25Okapi

        self._texts = list(texts)
        self._payloads = list(payloads)
        self._bm25 = BM25Okapi([_tokenize(t) for t in self._texts])

    def search(self, query: str, k: int) -> list[dict[str, Any]]:
        if self._bm25 is None or not self._texts:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._payloads[i] for i in ranked[:k] if scores[i] != 0]


class MilvusDense:
    """Milvus dense vector store. ``client`` injectable for offline tests."""

    def __init__(
        self, *, collection: str, dim: int, uri: str | None = None, client: Any | None = None
    ):
        self._collection = collection
        self._dim = dim
        self._uri = uri
        self._client = client

    def _get_client(self):
        if self._client is None:
            if self._uri is None:
                raise RetrievalError("MILVUS_URI_REQUIRED: set PRESALE_MILVUS_URI")
            uri = self._uri
            try:
                from pymilvus import MilvusClient  # pyright: ignore[reportMissingImports]
            except ImportError as exc:
                raise RetrievalError("PYMILVUS_NOT_INSTALLED: uv sync --extra hybrid") from exc
            self._client = MilvusClient(uri=uri)
        return self._client

    def ensure(self) -> None:
        c = self._get_client()
        if c.has_collection(self._collection):
            return
        # Real pymilvus MilvusClient: explicit schema with a VARCHAR primary key so the
        # str UUID point ids we write are valid (the default auto schema uses int64 pk).
        if hasattr(c, "create_schema"):
            from pymilvus import (  # pyright: ignore[reportMissingImports]
                DataType,
            )

            schema = c.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field(
                field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=64
            )
            schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=self._dim)
            for name, length in (
                ("source_id", 255),
                ("source_version", 64),
                ("locator", 255),
                ("content", 65535),
                ("tenant_id", 128),
                ("product_id", 128),
            ):
                schema.add_field(field_name=name, datatype=DataType.VARCHAR, max_length=length)
            index_params = c.prepare_index_params()
            index_params.add_index(
                field_name="vector", index_type="AUTOINDEX", metric_type="COSINE"
            )
            c.create_collection(
                collection_name=self._collection, schema=schema, index_params=index_params
            )
        else:
            # Injected test fake: keep the legacy signature so offline tests stay green.
            c.create_collection(self._collection, dimension=self._dim)

    def upsert(self, points: list[dict[str, Any]]) -> None:
        self._get_client().upsert(collection_name=self._collection, data=points)

    def search(
        self, vector: list[float], *, tenant_id: str, product_id: str, k: int
    ) -> list[dict[str, Any]]:
        res = self._get_client().search(
            collection_name=self._collection,
            data=[vector],
            limit=k,
            output_fields=[
                "source_id",
                "source_version",
                "locator",
                "content",
                "tenant_id",
                "product_id",
            ],
            filter=f'tenant_id == "{tenant_id}" and product_id == "{product_id}"',
        )
        return [hit["entity"] for hit in res[0]]


def _hit_id(source_id: str, version: str, locator: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{version}:{locator}"))


def _rrf(*lists: list[dict[str, Any]], k: int = 60) -> list[dict[str, Any]]:
    scores: dict[str, float] = {}
    seen: dict[str, dict[str, Any]] = {}
    for lst in lists:
        for rank, item in enumerate(lst):
            key = item["id"]
            seen[key] = item
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    ranked = sorted(scores, key=lambda key: scores[key], reverse=True)
    return [seen[key] for key in ranked]


def hybrid_transport(
    *,
    embedding: Embedding,
    dense: MilvusDense,
    bm25: BM25Index,
    top_k: int = 5,
    rrf_k: int = 60,
    reranker: Callable[[str, list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> Callable[..., list[dict[str, Any]]]:
    """Build an ExternalRetrieval transport that fuses dense + BM25 via RRF.

    When ``reranker`` is provided, the full fused candidate pool is re-scored and
    re-ordered (cross-encoder) before trimming to ``top_k``.
    """

    def transport(
        *, tenant_id: str, product_id: str, query: str, timeout_s: float
    ) -> list[dict[str, Any]]:
        vector = embedding(query)
        pool = top_k * 3
        dense_hits = [
            {
                **_payload(hit),
                "id": _hit_id(hit["source_id"], hit["source_version"], hit["locator"]),
            }
            for hit in dense.search(vector, tenant_id=tenant_id, product_id=product_id, k=pool)
        ]
        bm25_hits = [{**_payload(item), "id": item["id"]} for item in bm25.search(query, pool)]
        fused = _rrf(dense_hits, bm25_hits, k=rrf_k)
        if reranker is not None:
            fused = reranker(query, fused)
        return [_strip_id(hit) for hit in fused[:top_k]]

    return transport


def _payload(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        key: hit[key]
        for key in ("source_id", "source_version", "locator", "content", "tenant_id", "product_id")
        if key in hit
    }


def _strip_id(hit: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in hit.items() if key != "id"}


def index_hybrid(
    sources: list[Any],
    *,
    embedding: Embedding,
    dense: MilvusDense,
    bm25: BM25Index,
) -> int:
    """Vectorize each field fragment, persist dense points to Milvus, build BM25."""
    points: list[dict[str, Any]] = []
    bm25_texts: list[str] = []
    bm25_payloads: list[dict[str, Any]] = []
    for source in sources:
        for locator, content in _flatten(source.fields):
            payload = {
                "source_id": source.source_id,
                "source_version": source.version,
                "locator": locator,
                "content": content,
                "tenant_id": source.tenant_id,
                "product_id": source.product_id,
            }
            points.append(
                {
                    "id": _hit_id(source.source_id, source.version, locator),
                    "vector": embedding(content),
                    **payload,
                }
            )
            bm25_texts.append(content)
            bm25_payloads.append(
                {**payload, "id": _hit_id(source.source_id, source.version, locator)}
            )
    if points:
        dense.ensure()
        dense.upsert(points)
    bm25.add(bm25_texts, bm25_payloads)
    return len(points)


def hybrid_retriever_from_env() -> ExternalRetrieval | None:
    """Build a Hybrid external retriever when PRESALE_MILVUS_URI is set."""
    uri = os.environ.get("PRESALE_MILVUS_URI")
    if not uri:
        return None
    from ..cli import load_catalog

    collection = os.environ.get("PRESALE_MILVUS_COLLECTION", "presale")
    from .qdrant_retrieval import deterministic_embedding

    embedding: Embedding
    if os.environ.get("PRESALE_EMBEDDING") == "deterministic":
        embedding = deterministic_embedding
    else:
        embedding = SentenceTransformerEmbedding()
    dense = MilvusDense(
        collection=collection, dim=64 if embedding is deterministic_embedding else 1024, uri=uri
    )
    bm25 = BM25Index()
    catalog = os.environ.get("PRESALE_CATALOG")
    if catalog:
        index_hybrid(load_catalog(catalog), embedding=embedding, dense=dense, bm25=bm25)
    reranker = None
    if os.environ.get("PRESALE_RERANKER_MODEL"):
        reranker = CrossEncoderReranker()
    return ExternalRetrieval(
        transport=hybrid_transport(embedding=embedding, dense=dense, bm25=bm25, reranker=reranker)
    )


def main(argv: list[str] | None = None) -> None:
    """Index a catalog into Milvus (dense) and build BM25. Uses PRESALE_* env."""
    import argparse

    from ..cli import load_catalog

    parser = argparse.ArgumentParser(
        prog="presale-index-hybrid",
        description="Index catalog into Hybrid RAG (Milvus dense + BM25).",
    )
    parser.add_argument("catalog", help="Path to catalog JSON (or use PRESALE_CATALOG)")
    args = parser.parse_args(argv)
    catalog = args.catalog or os.environ.get("PRESALE_CATALOG")
    if not catalog:
        raise SystemExit("catalog path required (arg or PRESALE_CATALOG)")
    uri = os.environ.get("PRESALE_MILVUS_URI")
    if not uri:
        raise SystemExit("PRESALE_MILVUS_URI required")
    from .qdrant_retrieval import deterministic_embedding

    embedding: Embedding
    if os.environ.get("PRESALE_EMBEDDING") == "deterministic":
        embedding = deterministic_embedding
    else:
        embedding = SentenceTransformerEmbedding()
    collection = os.environ.get("PRESALE_MILVUS_COLLECTION", "presale")
    dense = MilvusDense(
        collection=collection, dim=64 if embedding is deterministic_embedding else 1024, uri=uri
    )
    bm25 = BM25Index()
    count = index_hybrid(load_catalog(catalog), embedding=embedding, dense=dense, bm25=bm25)
    print(f"indexed {count} chunks into Milvus {collection} at {uri}")


__all__ = [
    "BM25Index",
    "CrossEncoderReranker",
    "MilvusDense",
    "SentenceTransformerEmbedding",
    "hybrid_retriever_from_env",
    "hybrid_transport",
    "index_hybrid",
    "main",
]
