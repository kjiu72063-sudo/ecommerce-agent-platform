"""Live Clipper Agent - 直播切片 Agent（mock 外部 ASR/视频服务）."""

from .agent import LiveClipperAgent, extract_product_segments
from .golden import LIVE_CLIPPER_GOLDEN_VERSION, live_clipper_golden
from .tools import MockAsrService, MockVideoEditor, TranscriptSegment

__all__ = [
    "LIVE_CLIPPER_GOLDEN_VERSION",
    "LiveClipperAgent",
    "MockAsrService",
    "MockVideoEditor",
    "TranscriptSegment",
    "extract_product_segments",
    "live_clipper_golden",
]
