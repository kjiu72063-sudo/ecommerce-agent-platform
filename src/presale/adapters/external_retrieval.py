"""External retrieval RetrievalPort adapter for the presale slice.

Calls an injectable external retrieval transport (the seam for a real vector
DB / search service, wired later at assembly) and maps results to a tenant- and
product-scoped ``RetrievalResult``. The transport, query builder and optional
fallback are injectable so the ring is fully testable offline; out-of-scope
evidence is never leaked.
"""

from __future__ import annotations

from typing import Any, Callable

from agent_platform_contracts.policies import canonical_sha256

from ..contracts import ProductQuestion
from ..knowledge import EvidenceItem, RetrievalPort, RetrievalResult, RetrievalStatus

RetrievalTransport = Callable[..., list[dict[str, Any]]]
QueryBuilder = Callable[[ProductQuestion], str]


class RetrievalError(RuntimeError):
    """External retrieval failed without producing a trustworthy result."""


def _unconfigured_transport(*, tenant_id: str, product_id: str, query: str, timeout_s: float):
    raise RetrievalError("RETRIEVAL_NOT_CONFIGURED: inject a transport to use external retrieval")


def default_query_builder(question: ProductQuestion) -> str:
    return question.question_text


class ExternalRetrieval(RetrievalPort):
    """Retrieve scoped evidence from an external search/vector transport."""

    def __init__(
        self,
        *,
        transport: RetrievalTransport | None = None,
        query_builder: QueryBuilder | None = None,
        fallback: RetrievalPort | None = None,
        timeout_s: float = 5.0,
    ):
        self._transport = transport or _unconfigured_transport
        self._query_builder = query_builder or default_query_builder
        self._fallback = fallback
        self._timeout_s = timeout_s

    def retrieve(self, question: ProductQuestion) -> RetrievalResult:
        query = self._query_builder(question)
        try:
            raw = self._transport(
                query=query,
                tenant_id=question.tenant_id,
                product_id=question.product_id,
                timeout_s=self._timeout_s,
            )
        except Exception as exc:
            if self._fallback is not None:
                result = self._fallback.retrieve(question)
                return result.model_copy(
                    update={"reason_codes": [*result.reason_codes, "RETRIEVAL_DEGRADED"]}
                )
            if isinstance(exc, RetrievalError):
                raise
            raise RetrievalError("RETRIEVAL_CALL_FAILED") from exc

        items = self._parse(raw, question)
        if not items:
            return RetrievalResult(
                status=RetrievalStatus.NO_EVIDENCE, reason_codes=["EXTERNAL_NO_EVIDENCE"]
            )
        return RetrievalResult(
            status=RetrievalStatus.MATCHED,
            evidence_items=items,
            reason_codes=["EXTERNAL_RETRIEVAL"],
        )

    def _parse(self, raw: list[dict[str, Any]], question: ProductQuestion) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for entry in raw:
            tenant = entry.get("tenant_id", question.tenant_id)
            product = entry.get("product_id", question.product_id)
            # Never leak cross-tenant / cross-product evidence.
            if tenant != question.tenant_id or product != question.product_id:
                continue
            content = entry.get("content")
            if not content or not entry.get("source_id") or not entry.get("locator"):
                continue
            items.append(
                EvidenceItem(
                    source_id=entry["source_id"],
                    source_version=entry.get("source_version", "external"),
                    locator=entry["locator"],
                    content_digest=canonical_sha256({"content": content}),
                    tenant_id=tenant,
                    product_id=product,
                    content=content,
                )
            )
        return items


__all__ = ["ExternalRetrieval", "RetrievalError", "default_query_builder"]
