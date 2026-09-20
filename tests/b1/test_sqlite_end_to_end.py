"""SQLite end-to-end: full persist + cross-instance replay via create_sqlite."""

import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from presale.contracts import ProductQuestion
from presale.knowledge import KnowledgeSource
from presale.runtime import PresaleRuntimeFactory


class _Registry:
    def __init__(self, objects):
        self.objects = objects

    async def list_by_filter(self, filter, limit=100, offset=0):
        return [
            obj
            for obj in self.objects
            if obj["kind"] == filter.kind
            and obj["metadata"]["namespace"] == filter.namespace
            and obj["metadata"]["key"] == filter.key
            and obj["status"]["phase"] == filter.phase
            and obj["metadata"]["scope"]["tenant_id"] == filter.tenant_id
        ]


def definition(kind, object_id, key):
    return {
        "kind": kind,
        "metadata": {
            "id": object_id,
            "key": key,
            "namespace": "presale",
            "version": "1.0.0",
            "content_digest": "sha256:" + "a" * 64,
            "scope": {"type": "tenant", "tenant_id": "tenant-demo"},
        },
        "status": {"phase": "active"},
    }


def _sources():
    return [
        KnowledgeSource(
            source_id="catalog-001",
            version="2026.09.01",
            tenant_id="tenant-demo",
            product_id="product-001",
            status="published",
            fields={"spec": {"season": "适合夏季使用"}},
        )
    ]


def _question(*, key="sqlite-e2e-key-0001"):
    return ProductQuestion(
        question_id="question-sqlite-e2e",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        idempotency_key=key,
    )


def _assembly(db: Path, sources):
    registry = _Registry(
        [
            definition("AgentSpec", "agt_01111111-1111-7111-8111-111111111111", "presale-agent"),
            definition(
                "PromptPackage", "prm_01111111-1111-7111-8111-111111111111", "presale-prompt"
            ),
            definition(
                "ContextPolicy", "cpo_01111111-1111-7111-8111-111111111111", "presale-context"
            ),
        ]
    )
    return PresaleRuntimeFactory.create_sqlite(
        database=str(db),
        definition_repository=registry,
        definition_selectors={
            "agent_spec": {"kind": "AgentSpec", "namespace": "presale", "key": "presale-agent"},
            "prompt_package": {
                "kind": "PromptPackage",
                "namespace": "presale",
                "key": "presale-prompt",
            },
            "context_policy": {
                "kind": "ContextPolicy",
                "namespace": "presale",
                "key": "presale-context",
            },
        },
        sources=sources,
    )


@pytest.mark.asyncio
async def test_sqlite_persists_and_replays_across_instances():
    tmp = Path(tempfile.mkdtemp(prefix="sqlite_e2e_"))
    try:
        db = tmp / "presale.sqlite3"
        sources = _sources()
        question = _question()

        factory, store = _assembly(db, sources)
        runner = factory.create_runner()
        first = await runner.ask(question)
        assert first.answer_draft is not None
        assert first.answer_draft.need_human is False  # matched -> supported
        store.close()

        # Reopen the SAME db as a fresh assembly/instance; same idempotency key must
        # replay the persisted draft instead of regenerating.
        factory2, store2 = _assembly(db, sources)
        runner2 = factory2.create_runner()
        replay = await runner2.ask(_question(key=question.idempotency_key))
        assert replay.answer_draft.answer_id == first.answer_draft.answer_id
        assert replay.answer_draft.answer_text == first.answer_draft.answer_text
        assert replay.run_ref == first.run_ref
        store2.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
