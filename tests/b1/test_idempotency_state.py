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

    # A retry with the same key must replay the persisted draft (not regenerate),
    # and — once the transient write failure is gone — finalize the claim to
    # succeeded so it does not remain in_progress forever.
    retried = await PresaleQaRunner(
        sources=[source()],
        idempotency_repo=base,  # healthy repo now: replay should finalize succeeded
        answer_repo=answers,
        trace_repo=traces,
    ).ask(question())

    assert retried.answer_draft.answer_id == persisted.answer_id
    final = await base.get("tenant-demo", "state-key-001")
    assert final.status == "succeeded"


@pytest.mark.asyncio
async def test_mark_failed_claim_is_set_even_when_trace_cleanup_fails():
    from presale.trace import PresaleRunTrace

    repo = InMemoryIdempotencyRepository()

    class TraceRepoDown:
        async def save(self, trace):
            pass

        async def get(self, run_ref, *, tenant_id):
            raise RuntimeError("trace repo down")

        async def list_by_tenant(self, *, tenant_id):
            return []

        async def mark_disposition(self, run_ref, *, tenant_id, state):
            pass

        async def mark_archived(self, run_ref, *, tenant_id):
            pass

    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=repo,
        trace_repo=TraceRepoDown(),
    )

    with pytest.raises(QaRuntimeError, match="ANSWER_GENERATION_FAILED"):
        await runner.ask(question())

    # tracer.fail reuses the broken trace repo and raises; the independent claim
    # cleanup must still run so the claim is never left stuck in_progress.
    claim = await repo.get("tenant-demo", "state-key-001")
    assert claim is not None
    assert claim.status == "failed"


@pytest.mark.asyncio
async def test_unconfirmed_trace_after_persist_is_not_marked_succeeded():
    from presale.trace import PresaleRunTrace

    repo = InMemoryIdempotencyRepository()

    class TraceGetBreaksOnceAttached:
        # Semantic discriminator: reads of an already-attached trace fail. This
        # targets the post-persist "trace not confirmed" branch without coupling
        # to how many times the pipeline calls get() before attach_answer.
        def __init__(self):
            self.attached = set()

        async def save(self, trace):
            if trace.answer_draft_id:
                self.attached.add(trace.run_ref)

        async def get(self, run_ref, *, tenant_id):
            if run_ref in self.attached:
                raise RuntimeError("trace get down after attach")
            return PresaleRunTrace(
                run_ref=run_ref,
                tenant_id=tenant_id,
                question_id="q",
                task_id="t",
                agent_run_id=run_ref,
                configuration_refs={},
                stages=[],
            )

        async def list_by_tenant(self, *, tenant_id):
            return []

        async def mark_disposition(self, run_ref, *, tenant_id, state):
            pass

        async def mark_archived(self, run_ref, *, tenant_id):
            pass

    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=repo,
        trace_repo=TraceGetBreaksOnceAttached(),
    )

    with pytest.raises(QaRuntimeError, match="ANSWER_GENERATION_FAILED"):
        await runner.ask(question())

    # The draft is durable but its trace was not confirmed readable: the claim
    # must not be marked succeeded (unconsumable) nor failed (forced duplicate),
    # only in_progress so a retry replays the durable draft.
    claim = await repo.get("tenant-demo", "state-key-001")
    assert claim is not None
    assert claim.status == "in_progress"


async def seed_state(*, claim, draft, attached, key="state-key-001"):
    """Seed a durable draft/trace/claim and return the shared repos + run_ref."""
    from presale.adapters.in_memory import (
        InMemoryAnswerDraftRepository,
        InMemoryRunTraceRepository,
    )
    from presale.answer import PresaleAnswerGenerator
    from presale.knowledge import EvidenceItem, RetrievalResult, RetrievalStatus
    from presale.trace import PresaleRunTrace, RunStage, StageRecord

    answers = InMemoryAnswerDraftRepository()
    traces = InMemoryRunTraceRepository()
    idem = InMemoryIdempotencyRepository()
    run_ref = "run_01111111-1111-7111-8111-111111111111"

    if draft:
        q = question()
        evidence = EvidenceItem(
            source_id="catalog-001",
            source_version="2026.09.01",
            locator="spec.season",
            content_digest=canonical_sha256({"content": "适合夏季"}),
            tenant_id="tenant-demo",
            product_id="product-001",
            content="适合夏季使用",
        )
        retrieval = RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=[evidence])
        ans = PresaleAnswerGenerator().generate(
            q, retrieval, run_ref={"kind": "AgentRun", "id": run_ref}, configuration_refs={}
        )
        await answers.save(ans, tenant_id="tenant-demo")
        trace = PresaleRunTrace(
            run_ref=run_ref,
            tenant_id="tenant-demo",
            question_id=q.question_id,
            task_id="task",
            agent_run_id=run_ref,
            configuration_refs={},
            stages=[
                StageRecord(
                    stage=RunStage.SUBMITTED, detail=q.question_id, occurred_at=q.requested_at
                )
            ],
            answer_draft_id=ans.answer_id if attached else None,
        )
        await traces.save(trace)

    if claim is not None:
        record = IdempotencyRecord(
            tenant_id="tenant-demo",
            idempotency_key=key,
            business_content_digest=canonical_sha256(
                {"product_id": "product-001", "question_text": "这款商品适合夏季使用吗？"}
            ),
            run_ref=run_ref,
            created_at=datetime.now(timezone.utc),
        )
        await idem.claim(record)
        if claim == "succeeded":
            await idem.update_status("tenant-demo", key, "succeeded")
        elif claim == "failed":
            await idem.update_status("tenant-demo", key, "failed")

    return answers, traces, idem, run_ref


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            {
                "claim": None,
                "draft": False,
                "attached": False,
                "expect_status": "succeeded",
                "expect_error": None,
            },
            id="fresh",
        ),
        pytest.param(
            {
                "claim": "in_progress",
                "draft": False,
                "attached": False,
                "expect_status": "in_progress",
                "expect_error": "IDEMPOTENCY_RESULT_NOT_READY",
            },
            id="in_progress_no_draft",
        ),
        pytest.param(
            {
                "claim": "in_progress",
                "draft": True,
                "attached": False,
                "expect_status": "in_progress",
                "expect_error": None,
            },
            id="in_progress_draft_unattached",
        ),
        pytest.param(
            {
                "claim": "in_progress",
                "draft": True,
                "attached": True,
                "expect_status": "succeeded",
                "expect_error": None,
            },
            id="in_progress_draft_attached",
        ),
        pytest.param(
            {
                "claim": "succeeded",
                "draft": True,
                "attached": True,
                "expect_status": "succeeded",
                "expect_error": None,
            },
            id="succeeded",
        ),
        pytest.param(
            {
                "claim": "failed",
                "draft": True,
                "attached": True,
                "expect_status": "succeeded",
                "expect_error": None,
            },
            id="failed_retry",
        ),
    ],
)
async def test_idempotency_state_transition_matrix(case):
    answers, traces, idem, _ = await seed_state(
        claim=case["claim"], draft=case["draft"], attached=case["attached"]
    )
    runner = PresaleQaRunner(
        sources=[source()], idempotency_repo=idem, answer_repo=answers, trace_repo=traces
    )

    error = None
    try:
        result = await runner.ask(question())
    except QaRuntimeError as exc:
        error = str(exc)
        result = None

    if case["expect_error"]:
        assert error is not None and case["expect_error"] in error
        assert result is None
    else:
        assert error is None, f"unexpected error: {error}"
        assert result is not None

    final = await idem.get("tenant-demo", "state-key-001")
    assert final.status == case["expect_status"]


@pytest.mark.asyncio
async def test_replay_confirm_failure_keeps_claim_in_progress():
    answers, traces, base, _ = await seed_state(claim="in_progress", draft=True, attached=True)

    class FailingSucceed:
        def __init__(self):
            self.succeeded_attempts = 0

        async def claim(self, record):
            return await base.claim(record)

        async def get(self, tenant_id, key):
            return await base.get(tenant_id, key)

        async def update_status(self, tenant_id, key, status):
            if status == "succeeded":
                self.succeeded_attempts += 1  # spy: confirm was actually attempted
                raise RuntimeError("db down while writing succeeded")
            return await base.update_status(tenant_id, key, status)

    failing = FailingSucceed()
    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=failing,
        answer_repo=answers,
        trace_repo=traces,
    )

    result = await runner.ask(question())

    assert result.answer_draft.answer_id  # replay returned the durable draft
    assert failing.succeeded_attempts >= 1, "replay must attempt to finalize succeeded"
    claim = await base.get("tenant-demo", "state-key-001")
    assert claim.status == "in_progress"  # confirm failed -> not finalized


@pytest.mark.asyncio
async def test_replay_trace_read_failure_surfaces_clean_error():
    from presale.trace import TraceError

    answers, traces, idem, _ = await seed_state(claim="in_progress", draft=True, attached=True)

    class TraceGetDown:
        async def save(self, trace):
            pass

        async def get(self, run_ref, *, tenant_id):
            raise TraceError("TRACE_NOT_FOUND")

        async def list_by_tenant(self, *, tenant_id):
            return []

        async def mark_disposition(self, run_ref, *, tenant_id, state):
            pass

        async def mark_archived(self, run_ref, *, tenant_id):
            pass

    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=idem,
        answer_repo=answers,
        trace_repo=TraceGetDown(),
    )

    with pytest.raises(QaRuntimeError, match="TRACE_NOT_FOUND"):
        await runner.ask(question())

    # The claim is left unchanged (in_progress) so a later retry can replay once
    # the trace is readable again.
    claim = await idem.get("tenant-demo", "state-key-001")
    assert claim.status == "in_progress"


@pytest.mark.asyncio
async def test_replay_answer_read_failure_surfaces_clean_error():
    answers, traces, idem, _ = await seed_state(claim="in_progress", draft=True, attached=True)

    class AnswerReadDown:
        async def get_by_run(self, run_ref, *, tenant_id):
            raise RuntimeError("answer read down")

    runner = PresaleQaRunner(
        sources=[source()],
        idempotency_repo=idem,
        answer_repo=AnswerReadDown(),
        trace_repo=traces,
    )

    with pytest.raises(QaRuntimeError, match="answer read down"):
        await runner.ask(question())

    # A storage fault while reading the durable draft leaves the claim unchanged.
    claim = await idem.get("tenant-demo", "state-key-001")
    assert claim.status == "in_progress"
