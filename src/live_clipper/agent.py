"""LiveClipperAgent: 直播切片 Agent（Harness 协议，mock ASR/视频工具）.

Pipeline: ASR 转写 → 确定性商品片段抽取 → mock 剪辑。输出是待人工审核的
切片建议（AnswerDraft 无 evidence 时必须 need_human）。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from agent_platform_contracts.models import ObjectRef, ResourceKind
from agent_runtime.harness import AgentRunResult
from presale.answer import AnswerDraft

from .tools import MockAsrService, MockVideoEditor, TranscriptSegment

# Utterance keywords that mark a product-pitch segment (deterministic).
_PITCH_MARKERS = frozenset(
    {
        "推荐",
        "下单",
        "优惠",
        "加购",
        "库存",
        "抢",
        "拍",
        "买",
        "赠",
        "福利",
        "直播间下单",
        "扣",
    }
)

_MIN_CLIP_S = 10.0
_MAX_CLIP_S = 180.0


def extract_product_segments(
    segments: list[TranscriptSegment],
    *,
    min_duration_s: float = _MIN_CLIP_S,
    max_duration_s: float = _MAX_CLIP_S,
) -> list[dict[str, Any]]:
    """Pick pitch utterances whose duration fits clip bounds (deterministic)."""
    picked: list[dict[str, Any]] = []
    for seg in segments:
        duration = seg.end_s - seg.start_s
        if duration < min_duration_s or duration > max_duration_s:
            continue
        if any(marker in seg.text for marker in _PITCH_MARKERS):
            picked.append(
                {
                    "start_s": seg.start_s,
                    "end_s": seg.end_s,
                    "duration_s": round(duration, 3),
                    "text": seg.text,
                }
            )
    return picked


class LiveClipperAgent:
    """Cut product clips from a live replay via injected mock ASR/video tools."""

    def __init__(
        self,
        *,
        asr: MockAsrService | None = None,
        video_editor: MockVideoEditor | None = None,
        min_clip_s: float = _MIN_CLIP_S,
        max_clip_s: float = _MAX_CLIP_S,
    ):
        self._asr = asr or MockAsrService()
        self._editor = video_editor or MockVideoEditor()
        self._min_clip_s = min_clip_s
        self._max_clip_s = max_clip_s

    @staticmethod
    def _make_run_id() -> str:
        value = uuid.uuid4().int
        value = (value & ~(0xF << 76)) | (0x7 << 76)
        value = (value & ~(0x3 << 62)) | (0x2 << 62)
        return f"run_{uuid.UUID(int=value)}"

    @staticmethod
    def _media_ref(question: Any) -> str:
        if isinstance(question, str):
            text = question
        else:
            text = getattr(question, "question_text", "") or ""
        match = re.search(r"live-demo-\d+", text)
        if match:
            return match.group(0)
        return text.strip() or "unknown-media"

    async def run(self, question: Any, step_context=None) -> AgentRunResult:
        del step_context
        media_ref = self._media_ref(question)
        question_id = "question-live-clip" if isinstance(question, str) else question.question_id
        tool_calls: list[dict[str, Any]] = []

        segments = self._asr.transcribe(audio_ref=media_ref)
        tool_calls.append(
            {
                "tool": "asr_transcribe",
                "audio_ref": media_ref,
                "status": "matched" if segments else "no_evidence",
                "segment_count": len(segments),
            }
        )

        picked = extract_product_segments(
            segments, min_duration_s=self._min_clip_s, max_duration_s=self._max_clip_s
        )
        tool_calls.append(
            {
                "tool": "extract_product_segments",
                "status": "matched" if picked else "no_evidence",
                "segment_count": len(picked),
            }
        )

        clips = [
            self._editor.cut(
                video_ref=media_ref,
                start_s=seg["start_s"],
                end_s=seg["end_s"],
            )
            for seg in picked
        ]
        tool_calls.append(
            {
                "tool": "video_cut",
                "status": "matched" if clips else "no_evidence",
                "clip_count": len(clips),
            }
        )

        # Clips are suggestions for human review before asset export; no real
        # media evidence refs → contract requires need_human.
        if clips:
            answer_text = (
                f"为 {media_ref} 生成 {len(clips)} 个商品切片建议，"
                f"时长：{'、'.join(str(c['duration_s']) + 's' for c in clips)}。"
                f"路径：{'、'.join(c['path'] for c in clips)}。"
            )
            reason_codes = ["CLIP_RECOMMENDATION"]
        else:
            answer_text = f"{media_ref} 未发现符合条件的商品口播片段，无需切片。"
            reason_codes = ["NO_PRODUCT_SEGMENT"]

        draft = AnswerDraft(
            answer_id="live-clip-draft",
            question_id=question_id,
            run_ref=ObjectRef(kind=ResourceKind.AGENT_RUN, id=self._make_run_id()),
            answer_text=answer_text,
            evidence_refs=[],
            confidence_signal="unavailable",
            need_human=True,
            reason_codes=reason_codes,
            configuration_refs={},
            generated_at=datetime.now(timezone.utc),
        )
        return AgentRunResult(
            run_ref="run_live_clipper",
            answer_draft=draft,
            need_human=True,
            tool_calls=tool_calls,
        )


__all__ = ["LiveClipperAgent", "extract_product_segments"]
