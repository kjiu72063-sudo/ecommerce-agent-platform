"""Context output artifact seam."""

from __future__ import annotations

from typing import Any

from agent_platform_contracts.models import ArtifactRef
from agent_platform_contracts.policies import canonical_sha256


class InMemoryContextArtifactStore:
    """Deterministic artifact store for context snapshots."""

    def __init__(self):
        self._snapshots: dict[str, dict[str, Any]] = {}

    def create_context_artifact(self, content: dict[str, Any]) -> ArtifactRef:
        if not content:
            raise ValueError("ARTIFACT_CONTENT_REQUIRED")
        digest = canonical_sha256(content)
        uuid_hex = digest.split(":", 1)[1]
        artifact_id = (
            "art_"
            f"{uuid_hex[:8]}-{uuid_hex[8:12]}-7{uuid_hex[13:16]}-"
            f"a{uuid_hex[17:20]}-{uuid_hex[20:32]}"
        )
        self._snapshots[artifact_id] = dict(content)
        return ArtifactRef(kind="Artifact", id=artifact_id, digest=digest)

    def get(self, artifact_id: str) -> dict[str, Any] | None:
        snapshot = self._snapshots.get(artifact_id)
        return dict(snapshot) if snapshot is not None else None
