"""方向5: LiveClipperAgent + ContentCreatorAgent (mock external services)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent_runtime.harness import Harness, TerminalDecision
from content_creator.agent import ContentCreatorAgent, generate_marketing_copy
from content_creator.golden import content_creator_golden
from live_clipper.agent import LiveClipperAgent, extract_product_segments
from live_clipper.golden import live_clipper_golden
from live_clipper.tools import MockAsrService, TranscriptSegment
from presale.adapters.eval_framework import (
    MODES,
    run_content_creator,
    run_live_clipper,
    summarize,
)
from presale.contracts import ProductQuestion


def _question(text: str, *, product_id: str = "product-001") -> ProductQuestion:
    return ProductQuestion(
        question_id="question-d5",
        tenant_id="tenant-demo",
        submitted_by={"actor_type": "user", "actor_id": "usr_d5"},
        product_id=product_id,
        question_text=text,
        requested_at=datetime(2026, 9, 24, tzinfo=timezone.utc),
        idempotency_key="direction5-key-0001",
    )


# --- LiveClipper ---


def test_mock_asr_returns_canned_transcript():
    asr = MockAsrService()
    segments = asr.transcribe(audio_ref="live-demo-001")
    assert len(segments) >= 3
    assert any("防晒衣" in s.text for s in segments)


def test_extract_product_segments_picks_pitch_only():
    segments = [
        TranscriptSegment(0.0, 5.0, "随便聊聊"),
        TranscriptSegment(5.0, 30.0, "这件防晒衣推荐下单，有优惠。"),
        TranscriptSegment(30.0, 200.0, "超长闲聊没有商品信息"),  # too long
    ]
    picked = extract_product_segments(segments)
    assert len(picked) == 1
    assert "推荐" in picked[0]["text"]


@pytest.mark.asyncio
async def test_live_clipper_agent_produces_clips_and_needs_human():
    agent = LiveClipperAgent()
    outcome = await Harness().execute("处理 live-demo-001 的直播回放并提取商品片段", agent)
    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    draft = outcome.answer_draft
    assert draft is not None
    assert draft.need_human is True
    assert "切片建议" in draft.answer_text
    tools = {c["tool"] for step in outcome.steps for c in step.tool_calls}
    assert {"asr_transcribe", "extract_product_segments", "video_cut"} <= tools
    cut = next(c for step in outcome.steps for c in step.tool_calls if c["tool"] == "video_cut")
    assert cut["clip_count"] >= 1


@pytest.mark.asyncio
async def test_live_clipper_agent_no_pitch_no_clips():
    agent = LiveClipperAgent()
    outcome = await Harness().execute("处理 live-demo-002 的直播回放并提取商品片段", agent)
    assert outcome.answer_draft is not None
    assert "无需切片" in outcome.answer_draft.answer_text
    cut = next(c for step in outcome.steps for c in step.tool_calls if c["tool"] == "video_cut")
    assert cut["clip_count"] == 0


def test_live_clipper_golden_versioned():
    from live_clipper.golden import LIVE_CLIPPER_GOLDEN_VERSION

    assert LIVE_CLIPPER_GOLDEN_VERSION
    assert len(live_clipper_golden()) >= 3


def test_run_live_clipper_eval_offline():
    report = run_live_clipper()
    assert report["n"] == 3
    assert report["errors"] == 0
    assert report["clips_expectation_rate"] == 1.0
    assert report["need_human_rate"] == 1.0
    assert report["total_clips"] >= 2
    assert "live-clipper:" in summarize("live-clipper", report)
    assert "live-clipper" in MODES


# --- ContentCreator ---


def test_generate_marketing_copy_template():
    copy = generate_marketing_copy(
        {
            "product_id": "product-001",
            "platform": "xiaohongshu",
            "style": "professional",
            "need_images": True,
        }
    )
    assert "xiaohongshu" in copy["text"]
    assert "product-001" in copy["text"]
    assert len(copy["image_prompts"]) == 2


@pytest.mark.asyncio
async def test_content_creator_agent_with_images():
    agent = ContentCreatorAgent()
    q = _question("为 product-001 生成 xiaohongshu professional 文案，需要配图")
    outcome = await Harness().execute(q, agent)
    assert outcome.terminal is TerminalDecision.NEED_HUMAN
    draft = outcome.answer_draft
    assert draft is not None
    assert draft.need_human is True
    assert "xiaohongshu" in draft.answer_text
    img = next(
        c for step in outcome.steps for c in step.tool_calls if c["tool"] == "generate_image"
    )
    assert img["image_count"] == 2


@pytest.mark.asyncio
async def test_content_creator_agent_without_images():
    agent = ContentCreatorAgent()
    q = _question("为 product-002 生成 weibo casual 文案，不要配图", product_id="product-002")
    outcome = await Harness().execute(q, agent)
    img = next(
        c for step in outcome.steps for c in step.tool_calls if c["tool"] == "generate_image"
    )
    assert img["image_count"] == 0
    assert outcome.answer_draft is not None
    assert "未生成配图" in outcome.answer_draft.answer_text


def test_content_creator_golden_versioned():
    from content_creator.golden import CONTENT_CREATOR_GOLDEN_VERSION

    assert CONTENT_CREATOR_GOLDEN_VERSION
    assert len(content_creator_golden()) >= 3


def test_run_content_creator_eval_offline():
    report = run_content_creator()
    assert report["n"] == 3
    assert report["errors"] == 0
    assert report["copy_pass_rate"] == 1.0
    assert report["images_pass_rate"] == 1.0
    assert report["need_human_rate"] == 1.0
    assert report["total_images"] == 4
    assert "content-creator:" in summarize("content-creator", report)
    assert "content-creator" in MODES
