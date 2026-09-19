"""Sweep Hybrid retrieval pool/RRF/reranker settings on one indexed corpus.

Usage (real bge + locally downloaded rerankers):
    HF_HUB_OFFLINE=1 PRESALE_MILVUS_URI=http://127.0.0.1:19530 \
      PRESALE_EMBEDDING_MODEL=models/bge-large-zh-v1.5 \
      python scripts/sweep_retrieval.py

The corpus is indexed once; every row reuses the same Milvus and BM25 state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from presale.adapters.external_retrieval import ExternalRetrieval
from presale.adapters.hybrid_retrieval import (
    BM25Index,
    CrossEncoderReranker,
    MilvusDense,
    SentenceTransformerEmbedding,
    hybrid_transport,
    index_hybrid,
)
from presale.adapters.retrieval_eval import evaluate_retriever
from presale.cli import load_catalog


def _csv_ints(raw: str) -> list[int]:
    return [int(value.strip()) for value in raw.split(",") if value.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep Hybrid retrieval parameters.")
    parser.add_argument("--catalog", default="src/presale/data/dev_catalog.json")
    parser.add_argument(
        "--uri", default=os.environ.get("PRESALE_MILVUS_URI", "http://127.0.0.1:19530")
    )
    parser.add_argument("--collection", default="presale_hybrid_1024")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--pools", default="15,30,60")
    parser.add_argument("--rrf-ks", default="20,60,100")
    parser.add_argument("--embedding-model", default=os.environ.get("PRESALE_EMBEDDING_MODEL"))
    parser.add_argument(
        "--reranker-models",
        default="none,models/bge-reranker-base,models/bge-reranker-large",
        help="comma-separated paths, or none; missing paths are skipped",
    )
    args = parser.parse_args()

    if not args.embedding_model:
        raise SystemExit("--embedding-model or PRESALE_EMBEDDING_MODEL is required")
    embedding = SentenceTransformerEmbedding(args.embedding_model)
    dense = MilvusDense(collection=args.collection, dim=1024, uri=args.uri)
    bm25 = BM25Index()
    index_hybrid(load_catalog(args.catalog), embedding=embedding, dense=dense, bm25=bm25)

    rerankers: dict[str, object | None] = {"none": None}
    for model in [item.strip() for item in args.reranker_models.split(",") if item.strip()]:
        if model == "none":
            continue
        if not Path(model).exists():
            print(
                json.dumps(
                    {"skip_reranker": model, "reason": "model path missing"}, ensure_ascii=False
                )
            )
            continue
        rerankers[model] = CrossEncoderReranker(model)

    rows: list[dict[str, object]] = []
    for pool in _csv_ints(args.pools):
        for rrf_k in _csv_ints(args.rrf_ks):
            for name, reranker in rerankers.items():
                retriever = ExternalRetrieval(
                    transport=hybrid_transport(
                        embedding=embedding,
                        dense=dense,
                        bm25=bm25,
                        top_k=args.top_k,
                        pool=pool,
                        rrf_k=rrf_k,
                        reranker=reranker,
                    )
                )
                report = evaluate_retriever(retriever)
                row = {
                    "reranker": name,
                    "pool": pool,
                    "rrf_k": rrf_k,
                    **report["hit_at_k"],
                    "mrr": report["mrr"],
                    "precision@5": report["precision@5"],
                }
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False))

    best = max(rows, key=lambda row: (float(row["mrr"]), float(row["hit@1"])))
    print("BEST " + json.dumps(best, ensure_ascii=False))


if __name__ == "__main__":
    main()
