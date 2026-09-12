from datetime import datetime, timezone

import pytest

from agent_platform_contracts.policies import canonical_sha256
from presale.adapters.in_memory import InMemoryIdempotencyRepository
from presale.contracts import ProductQuestion
from presale.idempotency import IdempotencyRecord
from presale.knowledge import KnowledgeSource
from presale.runner import PresaleQaRunner


def question():
    return ProductQuestion(
        question_id="question-state",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime.now(timezone.utc),
        idempotency_key="state-key-001",
    )


def source():
    return KnowledgeSource(
        source_id="catalog-001",
        version="2026.09.01",
        tenant_id="tenant-demo",
        product_id="product-001",
        status="published",
        fields={"spec": {"season": "适合夏季使用"}},
    )


@pytest.mark.asyncio
async def test_successful_run_persists_succeeded_claim():
    repo = InMemoryIdempotencyRepository()
    runner = PresaleQaRunner(sources=[source()], idempotency_repo=repo)

    await runner.ask(question())

    claim = await repo.get("tenant-demo", "state-key-001")
    assert claim is not None
    assert claim.status == "succeeded"


@pytest.mark.asyncio
async def test_fixed_agent_run_id_still_replays_existing_claim():
    repo = InMemoryIdempotencyRepository()
    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=repo,
        agent_run_id="run_01111111-1111-7111-8111-111111111111",
    )

    first = await runner.ask(question())
    second = await runner.ask(question())

    assert second.run_ref == first.run_ref
    assert second.answer_draft.answer_id == first.answer_draft.answer_id


@pytest.mark.asyncio
async def test_existing_in_progress_claim_returns_not_ready():
    repo = InMemoryIdempotencyRepository()
    await repo.claim(
        IdempotencyRecord(
            tenant_id="tenant-demo",
            idempotency_key="state-key-001",
            business_content_digest=canonical_sha256(
                {"product_id": "product-001", "question_text": "这款商品适合夏季使用吗？"}
            ),
            run_ref="run_02222222-2222-7222-8222-222222222222",
            created_at=datetime.now(timezone.utc),
        )
    )
    runner = PresaleQaRunner(sources=[source()], idempotency_repo=repo)

    with pytest.raises(ValueError, match="IDEMPOTENCY_RESULT_NOT_READY"):
        await runner.ask(question())
