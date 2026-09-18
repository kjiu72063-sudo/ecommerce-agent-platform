from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agent_platform_contracts.models import ObjectRef, ResourceKind
from presale.contracts import AnswerDraft, ProductQuestion

VALID_QUESTION = {
    "question_id": "question-001",
    "tenant_id": "tenant-demo",
    "submitted_by": {"actor_type": "user", "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"},
    "product_id": "product-001",
    "question_text": "这款商品适合夏季使用吗？",
    "requested_at": datetime(2026, 9, 7, tzinfo=timezone.utc),
    "idempotency_key": "question-001-key",
}

VALID_EVIDENCE = {
    "source_id": "product-catalog",
    "source_version": "2026.09.01",
    "locator": "spec.season",
    "content_digest": "sha256:" + "a" * 64,
}

VALID_ANSWER = {
    "answer_id": "answer-001",
    "question_id": "question-001",
    "run_ref": {
        "kind": ResourceKind.AGENT_RUN,
        "id": "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
    },
    "answer_text": "根据商品资料，这款商品适合夏季使用。",
    "evidence_refs": [VALID_EVIDENCE],
    "confidence_signal": "supported",
    "need_human": False,
    "reason_codes": [],
    "generated_at": datetime(2026, 9, 7, tzinfo=timezone.utc),
}


def test_product_question_is_valid_and_serializable():
    question = ProductQuestion.model_validate(VALID_QUESTION)

    dumped = question.model_dump(mode="json")

    assert dumped["tenant_id"] == "tenant-demo"
    assert dumped["submitted_by"]["actor_id"] == VALID_QUESTION["submitted_by"]["actor_id"]
    assert dumped["product_id"] == "product-001"
    assert dumped["idempotency_key"] == "question-001-key"


@pytest.mark.parametrize("missing", ["tenant_id", "submitted_by", "product_id"])
def test_product_question_requires_scope_and_operator(missing):
    payload = {**VALID_QUESTION}
    payload.pop(missing)

    with pytest.raises(ValidationError):
        ProductQuestion.model_validate(payload)


def test_product_question_rejects_blank_text_and_short_idempotency_key():
    with pytest.raises(ValidationError):
        ProductQuestion.model_validate({**VALID_QUESTION, "question_text": "   "})

    with pytest.raises(ValidationError):
        ProductQuestion.model_validate({**VALID_QUESTION, "idempotency_key": "short"})


def test_answer_draft_with_evidence_is_valid_and_serializable():
    answer = AnswerDraft.model_validate(VALID_ANSWER)

    dumped = answer.model_dump(mode="json")

    assert dumped["question_id"] == "question-001"
    assert dumped["run_ref"]["kind"] == "AgentRun"
    assert dumped["evidence_refs"][0]["locator"] == "spec.season"
    assert dumped["need_human"] is False


def test_answer_draft_without_evidence_requires_human():
    payload = {**VALID_ANSWER, "evidence_refs": [], "need_human": False}

    with pytest.raises(ValidationError):
        AnswerDraft.model_validate(payload)

    human_answer = AnswerDraft.model_validate(
        {**payload, "need_human": True, "reason_codes": ["NO_EVIDENCE"]}
    )
    assert human_answer.need_human is True


def test_answer_draft_requires_agent_run_reference():
    payload = {
        **VALID_ANSWER,
        "run_ref": ObjectRef(
            kind=ResourceKind.TASK,
            id="tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
        ),
    }

    with pytest.raises(ValidationError):
        AnswerDraft.model_validate(payload)
