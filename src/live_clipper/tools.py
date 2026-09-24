"""Mock external services for live clipping: ASR transcript + video cut.

Real deployments swap these for an ASR API and ffmpeg; the Agent only sees
the small ports below so offline tests and CI stay deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptSegment:
    """One timed utterance from an ASR transcript."""

    start_s: float
    end_s: float
    text: str


# Canned transcripts keyed by media reference. Deterministic for golden eval.
_DEFAULT_TRANSCRIPTS: dict[str, list[TranscriptSegment]] = {
    "live-demo-001": [
        TranscriptSegment(0.0, 8.0, "欢迎来到直播间，今天先聊天气。"),
        TranscriptSegment(8.0, 25.0, "这件防晒衣 UPF50+，推荐给经常户外的朋友，现在下单有优惠。"),
        TranscriptSegment(25.0, 40.0, "接下来回答粉丝问题，尺码建议拍大一码。"),
        TranscriptSegment(40.0, 55.0, "库存不多了，喜欢的可以加购，感谢支持。"),
    ],
    "live-demo-002": [
        TranscriptSegment(0.0, 10.0, "大家好，我们随便聊聊今天的心情。"),
        TranscriptSegment(10.0, 22.0, "没有固定商品要介绍，稍后连线嘉宾。"),
    ],
    "live-demo-003": [
        TranscriptSegment(0.0, 5.0, "开场音乐。"),
        TranscriptSegment(
            5.0, 35.0, "这款扫地机器人激光导航不撞墙，今天直播间下单送配件，强烈推荐。"
        ),
        TranscriptSegment(35.0, 50.0, "评论区扣 1 看细节演示。"),
    ],
}


class MockAsrService:
    """Deterministic stand-in for a remote ASR API."""

    def __init__(self, transcripts: dict[str, list[TranscriptSegment]] | None = None):
        self._transcripts = dict(_DEFAULT_TRANSCRIPTS)
        if transcripts:
            self._transcripts.update(transcripts)

    def transcribe(self, *, audio_ref: str, language: str = "zh-CN") -> list[TranscriptSegment]:
        del language  # interface parity with a real ASR client
        return list(self._transcripts.get(audio_ref, []))


class MockVideoEditor:
    """Deterministic stand-in for ffmpeg cut; emits stable mock clip paths."""

    def cut(
        self,
        *,
        video_ref: str,
        start_s: float,
        end_s: float,
        output_format: str = "mp4",
    ) -> dict:
        slug = f"{video_ref}-{int(start_s)}-{int(end_s)}"
        return {
            "clip_id": f"clip_{slug}",
            "path": f"mock://clips/{slug}.{output_format}",
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": round(end_s - start_s, 3),
        }
