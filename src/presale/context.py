"""V1 presale ContextPackage assembly boundary."""

from __future__ import annotations

from typing import Any

from agent_platform_contracts.models import ContextPackage
from context.context_service import ContextService, TokenBudgetExceeded, estimate_tokens

from .contracts import ProductQuestion
from .knowledge import EvidenceItem


class ContextBuildError(ValueError):
    """A presale context could not be built within its scope or budget."""


class PresaleContextBuilder:
    """Validate presale evidence and delegate package validation to B3."""

    def __init__(self, *, total_tokens: int, per_source_tokens: dict[str, int]):
        self.total_tokens = total_tokens
        self.per_source_tokens = dict(per_source_tokens)

    def build(
        self,
        question: ProductQuestion,
        evidence_sources: list[dict[str, Any]],
        *,
        run_ref: dict[str, str],
        policy_ref: dict[str, str],
        artifact_ref: dict[str, str],
    ) -> Any:
        if not evidence_sources:
            raise ContextBuildError("NO_EVIDENCE")

        descriptor_sources: list[dict[str, Any]] = []
        seen: set[str] = set()
        ordered_sources = sorted(
            evidence_sources, key=lambda item: item.get("priority", 0), reverse=True
        )
        for entry in ordered_sources:
            evidence = entry["evidence"]
            if not isinstance(evidence, EvidenceItem):
                raise ContextBuildError("INVALID_EVIDENCE")
            if (
                evidence.tenant_id != question.tenant_id
                or evidence.product_id != question.product_id
            ):
                raise ContextBuildError("OUT_OF_SCOPE")

            token_count = estimate_tokens(evidence.content)
            per_limit = self.per_source_tokens.get("evidence", self.total_tokens)
            if token_count > per_limit:
                raise ContextBuildError("TOKEN_BUDGET_EXCEEDED")

            if evidence.content_digest in seen:
                continue
            seen.add(evidence.content_digest)
            descriptor_sources.append(
                {
                    "type": "evidence",
                    "content": evidence.content,
                    "priority": entry.get("priority", 0),
                    "provenance": [
                        f"{evidence.source_id}@{evidence.source_version}#{evidence.locator}"
                    ],
                }
            )

        if not descriptor_sources:
            raise ContextBuildError("NO_EVIDENCE")

        total = sum(estimate_tokens(source["content"]) for source in descriptor_sources)
        if total > self.total_tokens:
            raise ContextBuildError("TOKEN_BUDGET_EXCEEDED")

        policy = {
            "spec": {
                "token_budget": {
                    "total_tokens": self.total_tokens,
                    "per_source": self.per_source_tokens,
                }
            }
        }
        service = ContextService(policy)
        descriptor = {
            "run_ref": run_ref,
            "model_call_sequence": 1,
            "policy_ref": policy_ref,
            "artifact_ref": artifact_ref,
            "redaction_summary": {"secret_count": 0, "pii_count": 0},
            "sources": descriptor_sources,
        }
        try:
            return ContextPackage.model_validate(service.build(descriptor))
        except TokenBudgetExceeded as exc:
            raise ContextBuildError("TOKEN_BUDGET_EXCEEDED") from exc
        except (KeyError, ValueError) as exc:
            raise ContextBuildError("CONTEXT_CONTRACT_INVALID") from exc
