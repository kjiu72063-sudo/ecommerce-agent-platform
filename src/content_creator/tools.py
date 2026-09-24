"""Mock image generation port for the content creator agent."""

from __future__ import annotations

import hashlib


class MockImageGenerator:
    """Deterministic stand-in for an image-generation API."""

    def generate(self, *, prompt: str, style: str = "product") -> dict:
        digest = hashlib.sha256(f"{style}:{prompt}".encode()).hexdigest()[:12]
        return {
            "image_id": f"img_{digest}",
            "path": f"mock://images/{digest}.png",
            "prompt": prompt,
            "style": style,
        }
