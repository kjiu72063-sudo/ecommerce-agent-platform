"""Deterministic V1 AnswerDraft generation boundary."""

from __future__ import annotations

from datetime import datetime, timezone

from .contracts import AnswerDraft, ProductQuestion
from .knowledge import EvidenceItem, RetrievalResult, RetrievalStatus


class AnswerGenerationError(ValueError):
    """Answer generation failed without producing a trustworthy draft."""


class PresaleAnswerGenerator:
    """Generate deterministic answer drafts for internal review."""

    def generate(
        self,
        question: ProductQuestion,
        retrieval: RetrievalResult,
        *,
        run_ref: dict[str, str],
        configuration_refs: dict[str, str],
    ) -> AnswerDraft:
        reason_codes = list(retrieval.reason_codes)
        realtime_reason = self._realtime_reason(question.question_text)
        if realtime_reason:
            reason_codes.append(realtime_reason)

        if realtime_reason or retrieval.status is RetrievalStatus.CONFLICT:
            return self._human_review_draft(
                question,
                retrieval.evidence_items,
                run_ref,
                configuration_refs,
                reason_codes,
                confidence_signal="conflicting"
                if retrieval.status is RetrievalStatus.CONFLICT
                else "uncertain",
            )
        if retrieval.status is RetrievalStatus.NO_EVIDENCE:
            return self._human_review_draft(
                question,
                [],
                run_ref,
                configuration_refs,
                reason_codes or ["NO_EVIDENCE"],
                confidence_signal="unavailable",
            )

        try:
            answer_text = self._render_supported_answer(question, retrieval.evidence_items)
        except Exception as exc:
            raise AnswerGenerationError("ANSWER_GENERATION_FAILED") from exc

        return AnswerDraft(
            answer_id=f"answer-{question.question_id}",
            question_id=question.question_id,
            run_ref=run_ref,
            answer_text=answer_text,
            evidence_refs=[
                item.model_dump(exclude={"tenant_id", "product_id", "content"})
                for item in retrieval.evidence_items
            ],
            confidence_signal="supported",
            need_human=False,
            reason_codes=[],
            configuration_refs=dict(configuration_refs),
            generated_at=datetime.now(timezone.utc),
        )

    def _human_review_draft(
        self,
        question: ProductQuestion,
        evidence_items: list[EvidenceItem],
        run_ref: dict[str, str],
        configuration_refs: dict[str, str],
        reason_codes: list[str],
        *,
        confidence_signal: str,
    ) -> AnswerDraft:
        return AnswerDraft(
            answer_id=f"answer-{question.question_id}",
            question_id=question.question_id,
            run_ref=run_ref,
            answer_text="当前无法确认，请转人工处理。",
            evidence_refs=[
                item.model_dump(exclude={"tenant_id", "product_id", "content"})
                for item in evidence_items
            ],
            confidence_signal=confidence_signal,
            need_human=True,
            reason_codes=reason_codes,
            configuration_refs=dict(configuration_refs),
            generated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _render_supported_answer(
        question: ProductQuestion, evidence_items: list[EvidenceItem]
    ) -> str:
        evidence_text = "；".join(item.content for item in evidence_items)
        return f"根据已发布商品资料，{evidence_text}。"

    @staticmethod
    def _realtime_reason(question_text: str) -> str | None:
        realtime_terms = ("价格", "库存", "配送", "发货", "到货")
        return "REAL_TIME_DATA" if any(term in question_text for term in realtime_terms) else None
