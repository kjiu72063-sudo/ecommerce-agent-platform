"""Download BAAI/bge-large-zh-v1.5 into ./models via the hf-mirror GET endpoints.

Rationale: ``sentence_transformers``/``huggingface_hub`` do a HEAD metadata check that
hf-mirror does not satisfy (missing ``x-linked-etag``), so the normal ``SentenceTransformer()``
download fails even though plain GET works. We fetch every file with GET (which works)
into a local directory, then load it by local path with ``HF_HUB_OFFLINE=1``.

Usage: ``python scripts/download_bge_zh.py``  (idempotent; skips existing files)
"""

from __future__ import annotations

from pathlib import Path

import requests

ENDPOINT = "https://hf-mirror.com/BAAI/bge-large-zh-v1.5/resolve/main"
OUT = Path(__file__).resolve().parent.parent / "models" / "bge-large-zh-v1.5"
FILES = [
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
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for rel in FILES:
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            print(f"skip {rel}")
            continue
        resp = requests.get(f"{ENDPOINT}/{rel}", timeout=120, stream=True)
        resp.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in resp.iter_content(1024 * 512):
                fh.write(chunk)
        print(f"downloaded {rel}")


if __name__ == "__main__":
    main()
