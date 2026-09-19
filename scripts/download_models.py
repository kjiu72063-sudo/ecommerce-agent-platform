"""Download local models (bge-large-zh embedding, bge-reranker) via hf-mirror GET.

Rationale: ``sentence_transformers``/``huggingface_hub`` do a HEAD metadata check that
hf-mirror does not satisfy (missing ``x-linked-etag``), so the normal ``SentenceTransformer()``
download fails even though plain GET works. We fetch every file with GET (which works)
into a local directory, then load it by path with ``HF_HUB_OFFLINE=1``.

Usage:
    python scripts/download_models.py bge-large-zh-v1.5
    python scripts/download_models.py bge-reranker-base
    python scripts/download_models.py all            # default

Idempotent; skips files already present.
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

BASE = "https://hf-mirror.com"
MODELS: dict[str, dict[str, object]] = {
    "bge-large-zh-v1.5": {
        "repo": "BAAI/bge-large-zh-v1.5",
        "dir": "bge-large-zh-v1.5",
        "files": [
            ".gitattributes",
            "README.md",
            "config.json",
            "config_sentence_transformers.json",
            "modules.json",
            "pytorch_model.bin",
            "sentence_bert_config.json",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.txt",
            "1_Pooling/config.json",
        ],
    },
    "bge-reranker-base": {
        "repo": "BAAI/bge-reranker-base",
        "dir": "bge-reranker-base",
        "files": [
            ".gitattributes",
            "README.md",
            "config.json",
            "pytorch_model.bin",
            "sentencepiece.bpe.model",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
        ],
    },
}
OUT_ROOT = Path(__file__).resolve().parent.parent / "models"


def download_model(key: str) -> None:
    spec = MODELS[key]
    endpoint = f"{BASE}/{spec['repo']}/resolve/main"
    out = OUT_ROOT / str(spec["dir"])
    out.mkdir(parents=True, exist_ok=True)
    files = [str(f) for f in spec["files"]]
    for rel in files:
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[{key}] skip {rel}")
            continue
        resp = requests.get(f"{endpoint}/{rel}", timeout=120, stream=True)
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(1024 * 512):
                fh.write(chunk)
        print(f"[{key}] downloaded {rel}")


def main() -> None:
    targets = sys.argv[1:] or ["all"]
    for key in targets:
        if key == "all":
            for k in MODELS:
                download_model(k)
        else:
            if key not in MODELS:
                raise SystemExit(f"unknown model {key}; choose from {sorted(MODELS)}")
            download_model(key)


if __name__ == "__main__":
    main()
