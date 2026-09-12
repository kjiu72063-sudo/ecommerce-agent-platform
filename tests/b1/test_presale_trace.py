from datetime import datetime, timezone

import pytest

from agent_platform_contracts.models import ContextPackage
from presale.answer import PresaleAnswerGenerator
from presale.contracts import ProductQuestion
from presale.knowledge import EvidenceItem, RetrievalResult, RetrievalStatus
from presale.trace import PresaleRunTracer, TraceError


QUESTION = ProductQuestion(
    question_id="question-001",
    tenant_id="tenant-demo",
    submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    product_id="product-001",
    question_text="这款商品适合夏季使用吗？",
    requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    idempotency_key="question-001-key",
)
RUN_REF = {"kind": "AgentRun", "id": "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"}


def evidence():
    return EvidenceItem(
        source_id="catalog-001",
        source_version="2026.09.01",
        locator="spec.season",
        content_digest="sha256:" + "a" * 64,
        tenant_id="tenant-demo",
        product_id="product-001",
        content="适合夏季使用",
    )


def answer():
    return PresaleAnswerGenerator().generate(
        QUESTION,
        RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=[evidence()]),
        run_ref=RUN_REF,
        configuration_refs={"agent_spec": "1.0.0"},
    )


async def _start(tracer):
    return await tracer.start(
        question=QUESTION,
        task_id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
        agent_run_id=RUN_REF["id"],
        configuration_refs={},
    )


@pytest.mark.asyncio
async def test_start_records_question_and_returns_queryable_run_ref():
    tracer = PresaleRunTracer()

    trace_id = await tracer.start(
        question=QUESTION,
        task_id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
        agent_run_id=RUN_REF["id"],
        configuration_refs={"agent_spec": "1.0.0"},
    )

    trace = await tracer.get(trace_id, tenant_id="tenant-demo")
    assert trace.run_ref == trace_id
    assert trace.question_id == "question-001"
    assert trace.tenant_id == "tenant-demo"
    assert trace.task_id == "tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421"
    assert trace.agent_run_id == RUN_REF["id"]
    assert trace.stages[0].stage == "submitted"


@pytest.mark.asyncio
async def test_records_stages_and_attaches_context_and_answer():
    tracer = PresaleRunTracer()
    trace_id = await _start(tracer)

    await tracer.record_stage(trace_id, "knowledge_retrieved", "matched")
    context_package = _minimal_context()
    await tracer.attach_context(trace_id, context_package)
    draft = answer()
    await tracer.attach_answer(trace_id, draft)
    await tracer.record_stage(trace_id, "answer_generated", draft.answer_id)

    trace = await tracer.get(trace_id, tenant_id="tenant-demo")
    stages = [item.stage for item in trace.stages]
    assert "knowledge_retrieved" in stages
    assert "answer_generated" in stages
    assert trace.context_package_ref is not None
    assert trace.answer_draft_id == draft.answer_id
    assert trace.context_package_ref == context_package.run_ref.id


@pytest.mark.asyncio
async def test_failure_records_failed_event_and_reason():
    tracer = PresaleRunTracer()
    trace_id = await _start(tracer)

    await tracer.fail(trace_id, "CONTEXT_BUDGET_EXCEEDED")

    trace = await tracer.get(trace_id, tenant_id="tenant-demo")
    assert trace.failed is True
    assert trace.failure_reason == "CONTEXT_BUDGET_EXCEEDED"
    assert trace.stages[-1].stage == "failed"


@pytest.mark.asyncio
async def test_get_unknown_or_cross_tenant_returns_error():
    tracer = PresaleRunTracer()
    trace_id = await _start(tracer)

    with pytest.raises(TraceError, match="TRACE_NOT_FOUND"):
        await tracer.get(
            "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f999", tenant_id="tenant-demo"
        )

    with pytest.raises(TraceError, match="OUT_OF_SCOPE"):
        await tracer.get(trace_id, tenant_id="tenant-other")


@pytest.mark.asyncio
async def test_record_on_unknown_trace_fails():
    tracer = PresaleRunTracer()

    with pytest.raises(TraceError, match="TRACE_NOT_FOUND"):
        await tracer.record_stage(
            "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f999", "generated", "x"
        )


def _minimal_context() -> ContextPackage:
    return ContextPackage(
        run_ref=RUN_REF,
        model_call_sequence=1,
        policy_ref={
            "kind": "ContextPolicy",
            "id": "cpo_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
            "version": "1.0.0",
            "digest": "sha256:" + "b" * 64,
        },
        sections=[
            {
                "type": "evidence",
                "priority": 80,
                "token_count": 1,
                "provenance_refs": ["catalog-001@2026.09.01#spec.season"],
                "content_digest": "sha256:" + "a" * 64,
            }
        ],
        total_tokens=1,
        redaction_summary={"secret_count": 0, "pii_count": 0},
        content_digest="sha256:" + "c" * 64,
        artifact_ref={
            "id": "art_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f427",
            "digest": "sha256:" + "d" * 64,
        },
    )