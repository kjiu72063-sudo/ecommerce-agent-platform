"""Deterministic V1 product-knowledge retrieval contracts and service."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent_platform_contracts.policies import canonical_sha256

from .contracts import EvidenceRef, ProductQuestion


class RetrievalPort(ABC):
    """Port that turns a tenant-scoped question into scoped, verified evidence."""

    @abstractmethod
    def retrieve(self, question: ProductQuestion) -> RetrievalResult:
        """Return a RetrievalResult scoped to the question's tenant and product.

        Must never return evidence belonging to another tenant/product.
        """


class KnowledgeSource(BaseModel):
    """Versioned, tenant-scoped product knowledge used by the V1 prototype."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=256)
    version: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    product_id: str = Field(min_length=1, max_length=256)
    status: Literal["published", "draft"]
    fields: dict[str, Any]


class RetrievalStatus(StrEnum):
    MATCHED = "matched"
    NO_EVIDENCE = "no_evidence"
    CONFLICT = "conflict"


class EvidenceItem(EvidenceRef):
    """A field/fragment-level fact selected from a knowledge source."""

    tenant_id: str = Field(min_length=1, max_length=128)
    product_id: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=4096)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RetrievalStatus
    evidence_items: list[EvidenceItem] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_matches_items(self) -> RetrievalResult:
        if self.status is RetrievalStatus.MATCHED and not self.evidence_items:
            raise ValueError("matched retrieval requires evidence_items")
        if self.status is RetrievalStatus.NO_EVIDENCE and self.evidence_items:
            raise ValueError("no_evidence retrieval cannot contain evidence_items")
        if self.status is RetrievalStatus.CONFLICT and len(self.evidence_items) < 2:
            raise ValueError("conflict retrieval requires at least two evidence_items")
        return self


class DeterministicKnowledgeRetriever(RetrievalPort):
    """Match question terms against published, in-scope knowledge fields."""

    def __init__(self, sources: list[KnowledgeSource]):
        self.sources = list(sources)

    def retrieve(self, question: ProductQuestion) -> RetrievalResult:
        in_scope = [
            item
            for item in self.sources
            if item.status == "published"
            and item.tenant_id == question.tenant_id
            and item.product_id == question.product_id
        ]
        if not in_scope:
            return RetrievalResult(
                status=RetrievalStatus.NO_EVIDENCE,
                reason_codes=["OUT_OF_SCOPE"],
            )

        terms = self._terms(question.question_text)
        matched: list[EvidenceItem] = []
        for item in sorted(in_scope, key=lambda source: (source.source_id, source.version)):
            for locator, content in self._flatten(item.fields):
                searchable = f"{locator} {content}".lower()
                if len(terms.intersection(self._terms(searchable))) < 2:
                    continue
                matched.append(
                    EvidenceItem(
                        source_id=item.source_id,
                        source_version=item.version,
                        locator=locator,
                        content_digest=canonical_sha256(
                            {
                                "source_id": item.source_id,
                                "version": item.version,
                                "locator": locator,
                                "content": content,
                            }
                        ),
                        tenant_id=item.tenant_id,
                        product_id=item.product_id,
                        content=content,
                    )
                )

        if not matched:
            return RetrievalResult(
                status=RetrievalStatus.NO_EVIDENCE,
                reason_codes=["NO_EVIDENCE"],
            )

        grouped: dict[str, set[str]] = {}
        for item in matched:
            grouped.setdefault(item.locator, set()).add(item.content)
        if any(len(contents) > 1 for contents in grouped.values()):
            return RetrievalResult(
                status=RetrievalStatus.CONFLICT,
                evidence_items=matched,
                reason_codes=["CONFLICTING_EVIDENCE"],
            )
        return RetrievalResult(status=RetrievalStatus.MATCHED, evidence_items=matched)

    @staticmethod
    def _terms(value: str) -> set[str]:
        normalized = value.lower()
        ascii_terms = set(re.findall(r"[a-z0-9_-]+", normalized))
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
        chinese_terms = {chinese[index : index + 2] for index in range(len(chinese) - 1)}
        stop_terms = {"这款", "商品", "适合", "使用", "吗", "是否"}
        return (ascii_terms | chinese_terms) - stop_terms

    @classmethod
    def _flatten(cls, value: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
        flattened: list[tuple[str, str]] = []
        for key in sorted(value):
            locator = f"{prefix}.{key}" if prefix else key
            child = value[key]
            if isinstance(child, dict):
                flattened.extend(cls._flatten(child, locator))
            elif isinstance(child, list):
                for index, item in enumerate(child):
                    flattened.append((f"{locator}[{index}]", str(item)))
            else:
                flattened.append((locator, str(child)))
        return flattened
