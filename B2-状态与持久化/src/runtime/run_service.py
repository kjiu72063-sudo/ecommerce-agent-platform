"""B2 状态与持久化 - AgentRun 最小闭环服务

只依据 authoritative B0 的 AgentRun 模型和状态机实现生命周期；
不在此阶段实现模型调用或 Harness。
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import path_config

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from agent_platform_contracts.models import RESOURCE_MODELS
from agent_platform_contracts.state_machines import transition, StateTransitionError

from .repositories import RunRepository, EventRepository
from .event_store import EventStore


class RunService:
    """AgentRun 生命周期服务"""

    def __init__(self, run_repo: RunRepository, event_repo: EventRepository):
        self.run_repo = run_repo
        self.event_repo = event_repo
        self.event_store = EventStore(event_repo)

    @asynccontextmanager
    async def _transaction(self):
        store = getattr(self.run_repo, "store", None)
        if store is not None and store is getattr(self.event_repo, "store", None):
            async with store.transaction():
                yield
        else:
            yield

    async def create_run(self, payload: dict, actor: dict) -> dict:
        """创建 AgentRun（初始状态 created）"""
        model_class = RESOURCE_MODELS.get("agent-run")
        if not model_class:
            raise ValueError("AgentRun model not found")
        validated = model_class.model_validate(payload)
        run_dict = validated.model_dump(mode="json")
        run_dict["status"] = {"phase": "created"}
        run_dict["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()

        async with self._transaction():
            run_id = await self.run_repo.create_run(run_dict)
            await self.event_store.publish("run.created", run_id, "AgentRun", {"run_id": run_id})
        return {"id": run_id, "phase": "created"}

    async def get_run(self, run_id: str) -> dict | None:
        return await self.run_repo.get_run(run_id)

    async def get_runs_by_task(self, task_id: str) -> list[dict]:
        return await self.run_repo.get_runs_by_task(task_id)

    async def _transition(self, run_id: str, target: str, reason: str = None) -> dict:
        run = await self.run_repo.get_run(run_id)
        if not run:
            raise ValueError(f"AgentRun not found: {run_id}")
        current = run["status"]["phase"]
        try:
            transition("agent-run", current, target)
        except StateTransitionError as e:
            raise ValueError(f"Invalid transition: {e}")
        updates = {}
        if reason:
            updates["reason"] = reason
        async with self._transaction():
            ok = await self.run_repo.update_run_status(run_id, target, updates)
            if not ok:
                raise ValueError(f"AgentRun not found: {run_id}")
            await self.event_store.publish(f"run.{target.replace('_', '.')}", run_id, "AgentRun", {})
        return {"id": run_id, "phase": target}

    async def resolve_run(self, run_id: str) -> dict:
        """created -> resolving"""
        return await self._transition(run_id, "resolving")

    async def ready_run(self, run_id: str) -> dict:
        """resolving -> ready"""
        return await self._transition(run_id, "ready")

    async def start_run(self, run_id: str) -> dict:
        return await self._transition(run_id, "running")

    async def wait_run(self, run_id: str, wait_for: str) -> dict:
        if wait_for not in ("waiting_tool", "waiting_approval", "waiting_input"):
            raise ValueError(f"Unknown wait state: {wait_for}")
        return await self._transition(run_id, wait_for)

    async def complete_run(self, run_id: str) -> dict:
        return await self._transition(run_id, "succeeded")

    async def fail_run(self, run_id: str, error_code: str, error_message: str) -> dict:
        run = await self.run_repo.get_run(run_id)
        if not run:
            raise ValueError(f"AgentRun not found: {run_id}")
        error = {
            "code": error_code,
            "category": "internal",
            "message": error_message,
            "retryable": False,
            "safe_to_retry": False,
            "severity": "error",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        current = run["status"]["phase"]
        try:
            transition("agent-run", current, "failed")
        except StateTransitionError as e:
            raise ValueError(f"Invalid transition: {e}")
        async with self._transaction():
            await self.run_repo.update_run_status(run_id, "failed", {"error": error})
            await self.event_store.publish("run.failed", run_id, "AgentRun", {"error": error})
        return {"id": run_id, "phase": "failed"}

    async def cancel_run(self, run_id: str, reason: str = None) -> dict:
        return await self._transition(run_id, "cancelled", reason)
