from datetime import datetime, timezone

import pytest

from agent_platform_contracts.policies import canonical_sha256
from presale.contracts import ProductQuestion
from presale.knowledge import EvidenceItem
from presale.context import ContextBuildError, PresaleContextBuilder


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
POLICY_REF = {
    "kind": "ContextPolicy",
    "id": "cpo_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
    "version": "1.0.0",
    "digest": canonical_sha256({"policy": "presale"}),
}
ARTIFACT_REF = {
    "id": "art_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f427",
    "digest": canonical_sha256({"artifact": "context"}),
}


def evidence(
    *,
    content="适合夏季使用",
    tenant_id="tenant-demo",
    product_id="product-001",
    locator="spec.season",
    digest=None,
):
    return EvidenceItem(
        source_id="catalog-001",
        source_version="2026.09.01",
        locator=locator,
        content_digest=digest or canonical_sha256({"content": content}),
        tenant_id=tenant_id,
        product_id=product_id,
        content=content,
    )


def test_builds_b0_valid_context_with_provenance_and_priority():
    builder = PresaleContextBuilder(total_tokens=100, per_source_tokens={"evidence": 100})

    package = builder.build(
        QUESTION,
        [
            {"evidence": evidence(content="适合夏季使用", locator="spec.season"), "priority": 80},
            {"evidence": evidence(content="轻量透气面料", locator="spec.material"), "priority": 60},
        ],
        run_ref=RUN_REF,
        policy_ref=POLICY_REF,
        artifact_ref=ARTIFACT_REF,
    )

    assert str(package.run_ref.kind) == "AgentRun"
    assert str(package.policy_ref.kind) == "ContextPolicy"
    assert [section.priority for section in package.sections] == [80, 60]
    assert package.sections[0].provenance_refs == ["catalog-001@2026.09.01#spec.season"]
    assert package.total_tokens > 0


def test_deduplicates_same_content_digest_using_highest_priority():
    digest = canonical_sha256({"content": "适合夏季使用"})
    builder = PresaleContextBuilder(total_tokens=100, per_source_tokens={"evidence": 100})

    package = builder.build(
        QUESTION,
        [
            {
                "evidence": evidence(content="适合夏季使用", locator="spec.season", digest=digest),
                "priority": 30,
            },
            {
                "evidence": evidence(content="适合夏季使用", locator="faq.1", digest=digest),
                "priority": 90,
            },
        ],
        run_ref=RUN_REF,
        policy_ref=POLICY_REF,
        artifact_ref=ARTIFACT_REF,
    )

    assert len(package.sections) == 1
    assert package.sections[0].priority == 90
    assert package.sections[0].provenance_refs == ["catalog-001@2026.09.01#faq.1"]


@pytest.mark.parametrize(
    "item",
    [
        {"evidence": evidence(tenant_id="tenant-other"), "priority": 80},
        {"evidence": evidence(product_id="product-other"), "priority": 80},
    ],
)
def test_rejects_cross_tenant_or_cross_product_evidence(item):
    builder = PresaleContextBuilder(total_tokens=100, per_source_tokens={"evidence": 100})

    with pytest.raises(ContextBuildError, match="OUT_OF_SCOPE"):
        builder.build(
            QUESTION,
            [item],
            run_ref=RUN_REF,
            policy_ref=POLICY_REF,
            artifact_ref=ARTIFACT_REF,
        )


def test_rejects_single_source_budget_overflow():
    builder = PresaleContextBuilder(total_tokens=100, per_source_tokens={"evidence": 1})

    with pytest.raises(ContextBuildError, match="TOKEN_BUDGET_EXCEEDED"):
        builder.build(
            QUESTION,
            [{"evidence": evidence(content="这是一段超过单来源预算的商品说明"), "priority": 80}],
            run_ref=RUN_REF,
            policy_ref=POLICY_REF,
            artifact_ref=ARTIFACT_REF,
        )


def test_rejects_total_budget_overflow():
    builder = PresaleContextBuilder(total_tokens=1, per_source_tokens={"evidence": 100})

    with pytest.raises(ContextBuildError, match="TOKEN_BUDGET_EXCEEDED"):
        builder.build(
            QUESTION,
            [{"evidence": evidence(content="超过总预算的商品说明"), "priority": 80}],
            run_ref=RUN_REF,
            policy_ref=POLICY_REF,
            artifact_ref=ARTIFACT_REF,
        )


def test_rejects_non_evidence_item():
    builder = PresaleContextBuilder(total_tokens=100, per_source_tokens={"evidence": 100})

    with pytest.raises(ContextBuildError, match="INVALID_EVIDENCE"):
        builder.build(
            QUESTION,
            [{"evidence": {"content": "not an EvidenceItem"}, "priority": 80}],
            run_ref=RUN_REF,
            policy_ref=POLICY_REF,
            artifact_ref=ARTIFACT_REF,
        )


def test_malformed_policy_ref_raises_contract_invalid():
    builder = PresaleContextBuilder(total_tokens=100, per_source_tokens={"evidence": 100})

    with pytest.raises(ContextBuildError, match="CONTEXT_CONTRACT_INVALID"):
        builder.build(
            QUESTION,
            [{"evidence": evidence(), "priority": 80}],
            run_ref=RUN_REF,
            policy_ref={},  # missing required keys -> service/B0 validation fails
            artifact_ref=ARTIFACT_REF,
        )
