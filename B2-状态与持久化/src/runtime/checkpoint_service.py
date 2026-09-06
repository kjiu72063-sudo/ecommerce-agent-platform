"""B2 状态与持久化 - Checkpoint 最小能力服务

按 authoritative B0 的 Checkpoint 模型创建、查询快照；
恢复/重放仍属于 B5 Loop 前置能力，不在此阶段实现。
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import path_config

from datetime import datetime, timezone

from agent_platform_contracts.models import RESOURCE_MODELS

from .repositories import CheckpointRepository


class CheckpointService:
    """Checkpoint 生命周期服务"""

    def __init__(self, checkpoint_repo: CheckpointRepository):
        self.checkpoint_repo = checkpoint_repo

    async def create_checkpoint(self, payload: dict) -> dict:
        model_class = RESOURCE_MODELS.get("checkpoint")
        if not model_class:
            raise ValueError("Checkpoint model not found")
        validated = model_class.model_validate(payload)
        checkpoint = validated.model_dump(mode="json")
        checkpoint["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint["status"] = {"phase": "committed"}
        checkpoint_id = await self.checkpoint_repo.create_checkpoint(checkpoint)
        return {"id": checkpoint_id, "sequence": checkpoint["spec"]["sequence"]}

    async def get_checkpoint(self, checkpoint_id: str) -> dict | None:
        return await self.checkpoint_repo.get_checkpoint(checkpoint_id)

    async def get_latest_checkpoint(self, run_id: str) -> dict | None:
        return await self.checkpoint_repo.get_latest_checkpoint(run_id)

    async def list_checkpoints(self, run_id: str) -> list[dict]:
        return await self.checkpoint_repo.list_checkpoints(run_id)