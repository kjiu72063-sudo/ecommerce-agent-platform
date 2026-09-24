"""Live Clipper golden set for offline evaluation (versioned)."""

from __future__ import annotations

from typing import Any

# Bump when golden items or expected outcomes change.
LIVE_CLIPPER_GOLDEN_VERSION = "1.0.0"


def live_clipper_golden() -> list[dict[str, Any]]:
    """Cases: product pitch → ≥1 clip; small talk → 0 clips; keyword pitch → ≥1."""
    return [
        {
            "audio_ref": "live-demo-001",
            "query": "处理 live-demo-001 的直播回放并提取商品片段",
            "expected_min_clips": 1,
        },
        {
            "audio_ref": "live-demo-002",
            "query": "处理 live-demo-002 的直播回放并提取商品片段",
            "expected_min_clips": 0,
        },
        {
            "audio_ref": "live-demo-003",
            "query": "处理 live-demo-003 的直播回放并提取商品片段",
            "expected_min_clips": 1,
        },
    ]
