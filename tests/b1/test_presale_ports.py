import asyncio
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from presale.answer import PresaleAnswerGenerator
from presale.contracts import ProductQuestion
from presale.disposition import DispositionType, HumanDispositionRecord
from presale.knowledge import EvidenceItem, RetrievalResult, RetrievalStatus
from presale.ports import (
    AnswerDraftRepository,
    DispositionRepository,
    EvidenceRepository,
    NotFoundError,
    ProductQuestionRepository,
    RunTraceRepository,
)
from presale.trace import DispositionState, PresaleRunTrace, RunStage, StageRecord


def question():
    return ProductQuestion(
        question_id="question-port",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
        product_id="product-001",
        question_text="这款商品适合夏季使用吗？",
        requested_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
        idempotency_key="port-key-001",
    )


RUN_REF = {"kind": "AgentRun", "id": "run_01111111-1111-7111-8111-111111111111"}


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


def draft():
    return PresaleAnswerGenerator().generate(
        question(),
        RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=[evidence()]),
        run_ref=RUN_REF,
        configuration_refs={"agent_spec": "1.0.0"},
    )


def disposition():
    return HumanDispositionRecord(
        disposition=DispositionType.ACCEPTED,
        original_answer=draft(),
        actor_id="usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        reason="确认",
        occurred_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )


def trace():
    return PresaleRunTrace(
        run_ref=RUN_REF["id"],
        tenant_id="tenant-demo",
        question_id="question-port",
        task_id="tsk_01111111-1111-7111-8111-111111111111",
        agent_run_id=RUN_REF["id"],
        configuration_refs={},
        stages=[
            StageRecord(
                stage=RunStage.SUBMITTED,
                detail="question-port",
                occurred_at=datetime.now(timezone.utc),
            )
        ],
    )


class FakeQuestionRepo(ProductQuestionRepository):
    def __init__(self):
        self.questions = {}

    async def save(self, question):
        self.questions[question.question_id] = question

    async def get(self, question_id, *, tenant_id):
        q = self.questions.get(question_id)
        if q is None or q.tenant_id != tenant_id:
            raise NotFoundError("not found")
        return q

    async def find_by_idempotency(self, tenant_id, idempotency_key):
        for q in self.questions.values():
            if q.tenant_id == tenant_id and q.idempotency_key == idempotency_key:
                return q
        return None


class FakeEvidenceRepo(EvidenceRepository):
    def __init__(self):
        self.evidence = {}

    async def save_evidence(self, run_ref, items):
        self.evidence[run_ref] = items

    async def get_by_run(self, run_ref, *, tenant_id):
        items = self.evidence.get(run_ref)
        if items is None:
            raise NotFoundError("not found")
        return items


class FakeDraftRepo(AnswerDraftRepository):
    def __init__(self):
        self.drafts = {}

    async def save(self, draft, *, tenant_id):
        self.drafts[(draft.run_ref.id, tenant_id)] = draft

    async def get_by_run(self, run_ref, *, tenant_id):
        return self.drafts.get((run_ref, tenant_id))


class FakeDispositionRepo(DispositionRepository):
    def __init__(self):
        self.dispositions = {}

    async def save(self, record, *, tenant_id):
        self.dispositions[(record.original_answer.answer_id, tenant_id)] = record

    async def get_by_answer(self, answer_id, *, tenant_id):
        return self.dispositions.get((answer_id, tenant_id))


class FakeTraceRepo(RunTraceRepository):
    def __init__(self):
        self.traces = {}

    async def save(self, trace):
        self.traces[trace.run_ref] = trace

    async def get(self, run_ref, *, tenant_id):
        t = self.traces.get(run_ref)
        if t is None or t.tenant_id != tenant_id:
            raise NotFoundError("not found")
        return t

    async def mark_disposition(self, run_ref, *, tenant_id, state):
        t = await self.get(run_ref, tenant_id=tenant_id)
        self.traces[run_ref] = t.model_copy(update={"disposition_state": DispositionState(state)})

    async def mark_archived(self, run_ref, *, tenant_id):
        t = await self.get(run_ref, tenant_id=tenant_id)
        self.traces[run_ref] = t.model_copy(update={"archived": True})


def test_ports_are_implementable_and_tenant_scoped():
    questions = FakeQuestionRepo()
    evidence_repo = FakeEvidenceRepo()
    drafts = FakeDraftRepo()
    dispositions = FakeDispositionRepo()
    traces = FakeTraceRepo()

    async def run():
        await questions.save(question())
        got = await questions.get("question-port", tenant_id="tenant-demo")
        assert got.question_id == "question-port"
        with pytest.raises(NotFoundError):
            await questions.get("question-port", tenant_id="tenant-other")
        await evidence_repo.save_evidence(RUN_REF["id"], [evidence()])
        items = await evidence_repo.get_by_run(RUN_REF["id"], tenant_id="tenant-demo")
        assert len(items) == 1
        await drafts.save(draft(), tenant_id="tenant-demo")
        await dispositions.save(disposition(), tenant_id="tenant-demo")
        await traces.save(trace())
        await traces.mark_disposition(RUN_REF["id"], tenant_id="tenant-demo", state="complete")
        t = await traces.get(RUN_REF["id"], tenant_id="tenant-demo")
        assert t.disposition_state is DispositionState.COMPLETE
        await traces.mark_archived(RUN_REF["id"], tenant_id="tenant-demo")
        assert (await traces.get(RUN_REF["id"], tenant_id="tenant-demo")).archived is True

    asyncio.run(run())


def test_port_data_objects_validate_and_serialize():
    ev = evidence()
    dumped = ev.model_dump(mode="json")
    assert dumped["tenant_id"] == "tenant-demo"
    assert dumped["product_id"] == "product-001"

    q = question()
    assert q.model_dump(mode="json")["idempotency_key"] == "port-key-001"

    tr = trace()
    assert tr.model_dump(mode="json")["tenant_id"] == "tenant-demo"


def test_evidence_requires_tenant_and_product_scope():
    with pytest.raises(ValidationError):
        EvidenceItem(
            source_id="catalog-001",
            source_version="1",
            locator="x",
            content_digest="sha256:" + "a" * 64,
            tenant_id="",
            product_id="",
            content="x",
        )
