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
    "bge-reranker-large": {
        "repo": "BAAI/bge-reranker-large",
        "dir": "bge-reranker-large",
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

# Expected byte size of each model's weight file; used to validate a complete
# download (a tiny/incomplete partial must not be treated as done).
WEIGHT_SIZE: dict[str, int] = {
    "bge-large-zh-v1.5": 1302220525,
    "bge-reranker-base": 1112251061,
    "bge-reranker-large": 2239705845,
}


def _weight_size(key: str, rel: str) -> int | None:
    return WEIGHT_SIZE[key] if rel == "pytorch_model.bin" else None


def _is_complete(key: str, rel: str, size: int) -> bool:
    expected = _weight_size(key, rel)
    return size == expected if expected is not None else size > 0


def _download_resume(url: str, dest: Path, expected: int | None, attempts: int = 8) -> None:
    """Download ``url`` to ``dest`` with Range-based resume and retries.

    Writes to ``<dest>.part`` and atomically moves to ``dest`` on completion. A
    partial ``.part`` is kept across attempts so a dropped connection resumes
    instead of restarting (the mirror drops large transfers intermittently).
    """
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, attempts + 1):
        offset = part.stat().st_size if part.exists() else 0
        if expected is not None and offset >= expected:
            part.replace(dest)
            return
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        resp = requests.get(url, headers=headers, timeout=120, stream=True)
        if resp.status_code == 416:
            part.replace(dest)
            return
        if resp.status_code not in (200, 206):
            resp.raise_for_status()
        mode = "ab" if resp.status_code == 206 and offset else "wb"
        with part.open(mode) as fh:
            for chunk in resp.iter_content(1024 * 512):
                fh.write(chunk)
        if expected is None or part.stat().st_size >= expected:
            part.replace(dest)
            return
        print(f"  partial {part.stat().st_size} bytes, retry {attempt}")
    raise RuntimeError(f"gave up downloading {dest.name} after {attempts} attempts")


def download_model(key: str) -> None:
    spec = MODELS[key]
    endpoint = f"{BASE}/{spec['repo']}/resolve/main"
    out = OUT_ROOT / str(spec["dir"])
    out.mkdir(parents=True, exist_ok=True)
    for rel in [str(f) for f in spec["files"]]:
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        expected = _weight_size(key, rel)
        if dest.exists() and _is_complete(key, rel, dest.stat().st_size):
            print(f"[{key}] skip {rel}")
            continue
        part = dest.with_suffix(dest.suffix + ".part")
        if dest.exists():
            if expected is not None and dest.stat().st_size > 0 and not part.exists():
                # Recover a partial left by an older non-resumable downloader.
                dest.replace(part)
            else:
                dest.unlink()
        try:
            _download_resume(f"{endpoint}/{rel}", dest, expected)
            print(f"[{key}] downloaded {rel}")
        finally:
            # drop any stale temp so a future run starts fresh
            if part.exists():
                part.unlink()


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
