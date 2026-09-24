"""Content Creator golden set for offline evaluation (versioned)."""

from __future__ import annotations

from typing import Any

# Bump when golden items or expected outcomes change.
CONTENT_CREATOR_GOLDEN_VERSION = "1.0.0"


def content_creator_golden() -> list[dict[str, Any]]:
    """Briefs: platform/style drive deterministic copy; need_images controls mock image gen."""
    return [
        {
            "product_id": "product-001",
            "query": "为 product-001 生成 xiaohongshu professional 文案，需要配图",
            "expected_platform": "xiaohongshu",
            "expected_images": 2,
        },
        {
            "product_id": "product-002",
            "query": "为 product-002 生成 weibo casual 文案，不要配图",
            "expected_platform": "weibo",
            "expected_images": 0,
        },
        {
            "product_id": "product-005",
            "query": "为 product-005 生成 douyin professional 文案，需要配图",
            "expected_platform": "douyin",
            "expected_images": 2,
        },
    ]
