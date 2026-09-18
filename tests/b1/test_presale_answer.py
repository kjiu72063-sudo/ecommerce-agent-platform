from datetime import datetime, timezone

import pytest

from agent_platform_contracts.policies import canonical_sha256
from presale.answer import AnswerGenerationError, PresaleAnswerGenerator
from presale.contracts import ProductQuestion
from presale.knowledge import EvidenceItem, RetrievalResult, RetrievalStatus

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


def evidence(content="适合夏季使用", locator="spec.season", source_id="catalog-001"):
    return EvidenceItem(
        source_id=source_id,
        source_version="2026.09.01",
        locator=locator,
        content_digest=canonical_sha256({"content": content}),
        tenant_id="tenant-demo",
        product_id="product-001",
        content=content,
    )


def matched(*items):
    return RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=list(items))


def test_generates_supported_answer_with_evidence_and_configuration_refs():
    generator = PresaleAnswerGenerator()

    draft = generator.generate(
        QUESTION,
        matched(evidence()),
        run_ref=RUN_REF,
        configuration_refs={"agent_spec": "1.0.0", "prompt_package": "1.0.0"},
    )

    assert draft.question_id == "question-001"
    assert draft.run_ref.id == RUN_REF["id"]
    assert draft.evidence_refs[0].locator == "spec.season"
    assert draft.confidence_signal == "supported"
    assert draft.need_human is False
    assert draft.configuration_refs["agent_spec"] == "1.0.0"
    assert "适合夏季使用" in draft.answer_text


def test_no_evidence_returns_human_review_draft_without_fact_claim():
    generator = PresaleAnswerGenerator()

    draft = generator.generate(
        QUESTION,
        RetrievalResult(status=RetrievalStatus.NO_EVIDENCE, reason_codes=["NO_EVIDENCE"]),
        run_ref=RUN_REF,
        configuration_refs={},
    )

    assert draft.need_human is True
    assert draft.confidence_signal == "unavailable"
    assert draft.reason_codes == ["NO_EVIDENCE"]
    assert draft.evidence_refs == []
    assert "无法确认" in draft.answer_text


def test_conflicting_evidence_requires_human_review():
    result = RetrievalResult(
        status=RetrievalStatus.CONFLICT,
        evidence_items=[
            evidence("适合夏季使用"),
            evidence("不适合夏季使用", source_id="catalog-002"),
        ],
        reason_codes=["CONFLICTING_EVIDENCE"],
    )

    draft = PresaleAnswerGenerator().generate(
        QUESTION, result, run_ref=RUN_REF, configuration_refs={}
    )

    assert draft.need_human is True
    assert draft.confidence_signal == "conflicting"
    assert draft.reason_codes == ["CONFLICTING_EVIDENCE"]


@pytest.mark.parametrize("question_text", ["现在价格是多少？", "还有库存吗？", "什么时候配送？"])
def test_realtime_questions_require_human_review(question_text):
    question = QUESTION.model_copy(update={"question_text": question_text})

    draft = PresaleAnswerGenerator().generate(
        question,
        matched(evidence(content="固定商品资料")),
        run_ref=RUN_REF,
        configuration_refs={},
    )

    assert draft.need_human is True
    assert "REAL_TIME_DATA" in draft.reason_codes


def test_generation_failure_is_explicit():
    class FailingGenerator(PresaleAnswerGenerator):
        def _render_supported_answer(self, question, evidence_items):
            raise RuntimeError("template unavailable")

    with pytest.raises(AnswerGenerationError, match="ANSWER_GENERATION_FAILED"):
        FailingGenerator().generate(
            QUESTION,
            matched(evidence()),
            run_ref=RUN_REF,
            configuration_refs={},
        )
