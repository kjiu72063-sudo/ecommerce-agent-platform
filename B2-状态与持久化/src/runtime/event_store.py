"""B2 状态与持久化 - Event Store 服务"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import path_config

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4, UUID

from agent_platform_contracts.models import RESOURCE_MODELS


def _uuid7() -> UUID:
    """Generate a UUID-shaped v7 identifier on Python versions without uuid7."""
    value = uuid4().int
    value &= ~(0xF << 76)
    value |= 0x7 << 76
    value &= ~(0x3 << 62)
    value |= 0x2 << 62
    return UUID(int=value)
from agent_platform_contracts.policies import canonical_sha256

from .repositories import EventRepository


class EventStore:
    """事件存储服务"""

    def __init__(self, event_repo: EventRepository):
        self.event_repo = event_repo

    async def publish(self, event_type: str, subject_id: str, subject_kind: str,
                      data: dict, trace_id: str = None, span_id: str = None) -> str:
        """发布事件"""
        sequence = await self.event_repo.get_next_sequence(subject_id)
        event_id = f"evt_{_uuid7()}"

        if not trace_id:
            trace_id = _uuid7().hex
        if not span_id:
            span_id = _uuid7().hex[:16]

        event = {
            "api_version": "agent-platform/v1alpha1",
            "kind": "Event",
            "metadata": {
                "id": event_id,
                "revision": 1,
                "scope": {"type": "system"},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": {"actor_type": "system", "actor_id": "event_store"}
            },
            "spec": {
                "specversion": "1.0",
                "id": event_id,
                "source": "https://agent-platform.io/b2-event-store",
                "type": event_type,
                "time": datetime.now(timezone.utc).isoformat(),
                "datacontenttype": "application/json",
                "dataschema": f"https://agent-platform.io/schemas/events/{event_type.replace('.', '_')}/v1.0.0",
                "subject_ref": {"kind": subject_kind, "id": subject_id},
                "sequence": sequence,
                "trace": {
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "correlation_id": f"corr_{subject_id}"
                },
                "schema_ref": {
                    "id": f"sch_{event_type.replace('.', '_')}",
                    "version": "1.0.0",
                    "digest": canonical_sha256(data)
                },
                "data": data
            },
            "status": {"phase": "recorded"}
        }

        event = RESOURCE_MODELS["event"].model_validate(event).model_dump(mode="json")
        return await self.event_repo.save_event(event)

    async def get_events(self, subject_id: str, after_sequence: int = 0) -> list[dict]:
        """获取事件流"""
        return await self.event_repo.get_events(subject_id, after_sequence)

    async def get_latest_event(self, subject_id: str) -> Optional[dict]:
        """获取最新事件"""
        events = await self.event_repo.get_events(subject_id)
        return events[-1] if events else None

    async def rebuild_state(self, subject_id: str, initial_state: dict, apply_fn) -> dict:
        """从事件重建状态"""
        events = await self.event_repo.get_events(subject_id)
        state = initial_state.copy()
        for event in events:
            state = apply_fn(state, event)
        return state
