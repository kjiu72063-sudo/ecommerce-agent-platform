import pytest

from presale.artifact import InMemoryContextArtifactStore


def test_context_artifact_digest_is_content_derived():
    store = InMemoryContextArtifactStore()
    first = store.create_context_artifact(
        {"sections": [{"content_digest": "sha256:" + "a" * 64}], "total_tokens": 3}
    )
    same = store.create_context_artifact(
        {"sections": [{"content_digest": "sha256:" + "a" * 64}], "total_tokens": 3}
    )
    different = store.create_context_artifact(
        {"sections": [{"content_digest": "sha256:" + "b" * 64}], "total_tokens": 3}
    )

    assert first.digest == same.digest
    assert first.digest != different.digest
    assert first.id.startswith("art_")


def test_context_artifact_rejects_empty_content():
    store = InMemoryContextArtifactStore()
    with pytest.raises(ValueError, match="ARTIFACT_CONTENT_REQUIRED"):
        store.create_context_artifact({})
