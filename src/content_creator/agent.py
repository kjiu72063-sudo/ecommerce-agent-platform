"""ContentCreatorAgent: 自媒体运营 Agent（Harness 协议，mock 文案/图像工具）.

Pipeline: 解析 brief → 确定性文案模板 → mock 配图。输出待人工审核的
图文包建议（无 evidence 时必须 need_human）；non-goal：不直接外发。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from agent_platform_contracts.models import ObjectRef, ResourceKind
from agent_runtime.harness import AgentRunResult
from presale.answer import AnswerDraft

from .tools import MockImageGenerator

_PLATFORMS = ("xiaohongshu", "weibo", "douyin", "wechat")
_STYLES = ("professional", "casual", "humorous")


def _parse_brief(question: Any) -> dict[str, Any]:
    if isinstance(question, str):
        text = question
        product_id: str | None = None
        question_id = "question-content-creator"
    else:
        text = question.question_text or ""
        product_id = question.product_id
        question_id = question.question_id
    platform = next((p for p in _PLATFORMS if p in text), "xiaohongshu")
    style = next((s for s in _STYLES if s in text), "professional")
    need_images = "不要配图" not in text and "不要图" not in text
    match = re.search(r"product-\d+", text)
    if match:
        product_id = match.group(0)
    return {
        "product_id": product_id or "product-unknown",
        "platform": platform,
        "style": style,
        "need_images": need_images,
        "query": text,
        "question_id": question_id,
    }


def generate_marketing_copy(brief: dict[str, Any]) -> dict[str, Any]:
    """Deterministic copy template (no external LLM required)."""
    product = brief["product_id"]
    platform = brief["platform"]
    style = brief["style"]
    hooks = {
        "professional": f"【{platform}】{product} 专业评测要点",
        "casual": f"【{platform}】种草 {product} 的一天",
        "humorous": f"【{platform}】{product} 真香现场",
    }
    body = (
        f"围绕 {product} 的核心卖点，用 {style} 口吻讲清使用场景与差异点；"
        f"结尾引导点击商品卡了解详情（不直接承诺效果）。"
    )
    image_prompts: list[str] = []
    if brief.get("need_images", True):
        image_prompts = [
            f"{product} 主图白底特写",
            f"{product} 场景使用图",
        ]
    return {
        "text": f"{hooks[style]}\n{body}",
        "platform": platform,
        "image_prompts": image_prompts,
    }


class ContentCreatorAgent:
    """Create platform copy + optional mock images via injected ports."""

    def __init__(self, *, image_generator: MockImageGenerator | None = None):
        self._images = image_generator or MockImageGenerator()

    @staticmethod
    def _make_run_id() -> str:
        value = uuid.uuid4().int
        value = (value & ~(0xF << 76)) | (0x7 << 76)
        value = (value & ~(0x3 << 62)) | (0x2 << 62)
        return f"run_{uuid.UUID(int=value)}"

    async def run(self, question: Any, step_context=None) -> AgentRunResult:
        del step_context
        brief = _parse_brief(question)
        tool_calls: list[dict[str, Any]] = []

        copy = generate_marketing_copy(brief)
        tool_calls.append(
            {
                "tool": "generate_copy",
                "status": "matched",
                "platform": copy["platform"],
                "chars": len(copy["text"]),
            }
        )

        images = [
            self._images.generate(prompt=prompt, style=brief["style"])
            for prompt in copy["image_prompts"]
        ]
        tool_calls.append(
            {
                "tool": "generate_image",
                "status": "matched" if images else "no_evidence",
                "image_count": len(images),
            }
        )

        image_note = (
            f"配图 {len(images)} 张：{'、'.join(i['path'] for i in images)}。"
            if images
            else "未生成配图。"
        )
        answer_text = (
            f"平台 {copy['platform']} 文案：\n{copy['text']}\n{image_note}"
            f"（待人工审核后再进入素材流程）"
        )
        draft = AnswerDraft(
            answer_id="content-draft",
            question_id=brief["question_id"],
            run_ref=ObjectRef(kind=ResourceKind.AGENT_RUN, id=self._make_run_id()),
            answer_text=answer_text,
            evidence_refs=[],
            confidence_signal="unavailable",
            need_human=True,
            reason_codes=["CONTENT_RECOMMENDATION"],
            configuration_refs={},
            generated_at=datetime.now(timezone.utc),
        )
        return AgentRunResult(
            run_ref="run_content_creator",
            answer_draft=draft,
            need_human=True,
            tool_calls=tool_calls,
        )


__all__ = ["ContentCreatorAgent", "generate_marketing_copy"]
