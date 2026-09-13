import asyncio
from datetime import datetime, timezone

import pytest

from agent_platform_contracts.policies import canonical_sha256
from presale.adapters.in_memory import InMemoryIdempotencyRepository
from presale.contracts import ProductQuestion
from presale.definitions import FrozenConfiguration
from presale.idempotency import IdempotencyRecord
from presale.knowledge import KnowledgeSource
from presale.runner import PresaleQaResult, PresaleQaRunner, QaRuntimeError


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


@pytest.mark.asyncio
async def test_succeeded_claim_with_missing_draft_returns_not_ready():
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
    await repo.update_status("tenant-demo", "state-key-001", "succeeded")
    runner = PresaleQaRunner(sources=[source()], idempotency_repo=repo)

    with pytest.raises(ValueError, match="IDEMPOTENCY_RESULT_NOT_READY"):
        await runner.ask(question())


class BlockingDefinitionSource:
    """resolve() awaits an event so a run yields at a controlled point.

    This makes the claim interleave deterministic: the first caller claims and
    blocks inside resolve, letting a second concurrent caller observe the claim.
    """

    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def resolve(self, *, tenant_id):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return FrozenConfiguration(
            configuration_refs={
                "agent_spec": "1.0.0",
                "prompt_package": "1.0.0",
                "context_policy": "1.0.0",
            },
            policy_ref={
                "kind": "ContextPolicy",
                "id": "cpo_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
                "version": "1.0.0",
                "digest": canonical_sha256({"policy": "presale"}),
            },
        )


@pytest.mark.asyncio
async def test_concurrent_same_key_generates_single_answer():
    repo = InMemoryIdempotencyRepository()
    definition_source = BlockingDefinitionSource()
    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=repo,
        definition_source=definition_source,
    )

    first = asyncio.create_task(runner.ask(question()))
    await definition_source.started.wait()
    second = asyncio.create_task(runner.ask(question()))

    # The second caller must observe the in-flight claim and refuse to generate a
    # duplicate instead of racing into a second answer. It completes while the
    # first is still blocked at resolve().
    second_exc = None
    try:
        await second
    except QaRuntimeError as exc:
        second_exc = exc

    definition_source.release.set()
    first_result = await first

    assert definition_source.calls == 1, "a second run entered the fresh path"
    assert isinstance(first_result, PresaleQaResult)
    assert second_exc is not None
    assert "IDEMPOTENCY_RESULT_NOT_READY" in str(second_exc)
    claim = await repo.get("tenant-demo", "state-key-001")
    assert claim is not None
    assert claim.status == "succeeded"


@pytest.mark.asyncio
async def test_answer_persist_failure_marks_claim_failed_not_stuck():
    repo = InMemoryIdempotencyRepository()

    class FailingAnswerRepo:
        async def save(self, draft, *, tenant_id):
            raise RuntimeError("disk full")

        async def get_by_run(self, run_ref, *, tenant_id):
            return None

    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=repo,
        answer_repo=FailingAnswerRepo(),
    )

    with pytest.raises(QaRuntimeError, match="ANSWER_GENERATION_FAILED"):
        await runner.ask(question())

    claim = await repo.get("tenant-demo", "state-key-001")
    assert claim is not None
    assert claim.status == "failed", "claim must not be left stuck in_progress"

    # A failed claim can be retried: a fresh ask replaces it and succeeds.
    retried = await PresaleQaRunner(sources=[source()], idempotency_repo=repo).ask(question())
    assert retried.answer_draft.answer_id
    final = await repo.get("tenant-demo", "state-key-001")
    assert final.status == "succeeded"


@pytest.mark.asyncio
async def test_success_status_write_failure_replays_existing_answer():
    from presale.adapters.in_memory import (
        InMemoryAnswerDraftRepository,
        InMemoryRunTraceRepository,
    )

    base = InMemoryIdempotencyRepository()
    answers = InMemoryAnswerDraftRepository()
    traces = InMemoryRunTraceRepository()

    class SucceedWriteFailsRepository:
        async def claim(self, record):
            return await base.claim(record)

        async def get(self, tenant_id, idempotency_key):
            return await base.get(tenant_id, idempotency_key)

        async def update_status(self, tenant_id, idempotency_key, status):
            if status == "succeeded":
                raise RuntimeError("db down while writing succeeded")
            return await base.update_status(tenant_id, idempotency_key, status)

    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=SucceedWriteFailsRepository(),
        answer_repo=answers,
        trace_repo=traces,
    )

    with pytest.raises(QaRuntimeError, match="ANSWER_GENERATION_FAILED"):
        await runner.ask(question())

    claim = await base.get("tenant-demo", "state-key-001")
    assert claim is not None
    # The answer is already durable: do NOT mark the claim failed, which would
    # force a retry to regenerate a duplicate. Leave it in_progress instead.
    assert claim.status == "in_progress"
    persisted = await answers.get_by_run(claim.run_ref, tenant_id="tenant-demo")
    assert persisted is not None

    # A retry with the same key must replay the persisted draft, not regenerate.
    retried = await PresaleQaRunner(
        sources=[source()],
        idempotency_repo=SucceedWriteFailsRepository(),
        answer_repo=answers,
        trace_repo=traces,
    ).ask(question())

    assert retried.answer_draft.answer_id == persisted.answer_id
