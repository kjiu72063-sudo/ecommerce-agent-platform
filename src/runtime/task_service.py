"""B2 状态与持久化 - Task 服务"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from agent_platform_contracts.models import RESOURCE_MODELS
from agent_platform_contracts.state_machines import StateTransitionError, transition

from .event_store import EventStore
from .repositories import EventRepository, TaskFilter, TaskRepository


class TaskService:
    """Task 调度服务"""

    def __init__(self, task_repo: TaskRepository, event_repo: EventRepository):
        self.task_repo = task_repo
        self.event_repo = event_repo
        self.event_store = EventStore(event_repo)

    @asynccontextmanager
    async def _transaction(self):
        store = getattr(self.task_repo, "store", None)
        if store is not None and store is getattr(self.event_repo, "store", None):
            async with store.transaction():
                yield
        else:
            yield

    async def create_task(self, payload: dict, actor: dict) -> dict:
        """创建任务"""
        async with self._transaction():
            model_class = RESOURCE_MODELS.get("task")
            if not model_class:
                raise ValueError("Task model not found")

            validated = model_class.model_validate(payload)
            task_dict = validated.model_dump(mode="json")
            task_dict["status"] = {"phase": "created"}
            task_dict["metadata"]["created_at"] = datetime.now(timezone.utc).isoformat()

            # 幂等检查：直接用 idempotency_key 查找
            idem_key = task_dict["spec"].get("idempotency_key")
            if idem_key:
                # 检查是否已存在相同幂等键的任务
                for existing_task in await self.task_repo.list_tasks(TaskFilter(), limit=1000):
                    existing_key = existing_task.get("spec", {}).get("idempotency_key")
                    if existing_key == idem_key:
                        return {"id": existing_task["metadata"]["id"], "status": "already_exists"}

            task_id = await self.task_repo.create_task(task_dict)

            # 发布事件
            await self._publish_event("task.created", task_id, "Task", {"task_id": task_id})

            return {"id": task_id, "phase": "created"}

    async def get_task(self, task_id: str) -> Optional[dict]:
        return await self.task_repo.get_task(task_id)

    async def list_tasks(self, filter: TaskFilter, limit: int = 100) -> list[dict]:
        return await self.task_repo.list_tasks(filter, limit)

    async def validate_task(self, task_id: str, actor: dict) -> dict:
        """验证任务"""
        async with self._transaction():
            task = await self.task_repo.get_task(task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            current_phase = task["status"]["phase"]
            try:
                transition("task", current_phase, "validated")
            except StateTransitionError as e:
                raise ValueError(f"Invalid transition: {e}")

            await self.task_repo.update_task_status(task_id, "validated")
            await self._publish_event("task.validated", task_id, "Task", {})

            return {"id": task_id, "phase": "validated"}

    async def queue_task(self, task_id: str) -> dict:
        """将任务加入队列"""
        async with self._transaction():
            task = await self.task_repo.get_task(task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            current_phase = task["status"]["phase"]
            try:
                transition("task", current_phase, "queued")
            except StateTransitionError as e:
                raise ValueError(f"Invalid transition: {e}")

            await self.task_repo.update_task_status(task_id, "queued")
            await self._publish_event("task.queued", task_id, "Task", {})

            return {"id": task_id, "phase": "queued"}

    async def start_task(self, task_id: str) -> dict:
        """开始执行任务"""
        async with self._transaction():
            task = await self.task_repo.get_task(task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            current_phase = task["status"]["phase"]
            try:
                transition("task", current_phase, "running")
            except StateTransitionError as e:
                raise ValueError(f"Invalid transition: {e}")

            await self.task_repo.update_task_status(task_id, "running")
            await self._publish_event("task.started", task_id, "Task", {})

            return {"id": task_id, "phase": "running"}

    async def complete_task(self, task_id: str, artifact_id: str = None) -> dict:
        """完成任务"""
        async with self._transaction():
            task = await self.task_repo.get_task(task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            current_phase = task["status"]["phase"]
            try:
                transition("task", current_phase, "succeeded")
            except StateTransitionError as e:
                raise ValueError(f"Invalid transition: {e}")

            updates = {}
            if artifact_id:
                updates["final_artifact_ref"] = {"kind": "Artifact", "id": artifact_id}

            await self.task_repo.update_task_status(task_id, "succeeded", updates)
            await self._publish_event(
                "task.succeeded", task_id, "Task", {"artifact_id": artifact_id}
            )

            return {"id": task_id, "phase": "succeeded"}

    async def fail_task(self, task_id: str, error_code: str, error_message: str) -> dict:
        """任务失败"""
        async with self._transaction():
            task = await self.task_repo.get_task(task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            current_phase = task["status"]["phase"]
            try:
                transition("task", current_phase, "failed")
            except StateTransitionError as e:
                raise ValueError(f"Invalid transition: {e}")

            error = {
                "code": error_code,
                "category": "internal",
                "message": error_message,
                "retryable": False,
                "safe_to_retry": False,
                "severity": "error",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
            await self.task_repo.update_task_status(task_id, "failed", {"error": error})
            await self._publish_event("task.failed", task_id, "Task", {"error": error})

            return {"id": task_id, "phase": "failed"}

    async def cancel_task(self, task_id: str, reason: str = None) -> dict:
        """取消任务"""
        async with self._transaction():
            task = await self.task_repo.get_task(task_id)
            if not task:
                raise ValueError(f"Task not found: {task_id}")

            current_phase = task["status"]["phase"]
            try:
                transition("task", current_phase, "cancelled")
            except StateTransitionError as e:
                raise ValueError(f"Invalid transition: {e}")

            await self.task_repo.update_task_status(task_id, "cancelled", {"reason": reason})
            await self._publish_event("task.cancelled", task_id, "Task", {"reason": reason})

            return {"id": task_id, "phase": "cancelled"}

    async def _publish_event(self, event_type: str, subject_id: str, subject_kind: str, data: dict):
        """统一通过 EventStore 发布并校验事件。"""
        await self.event_store.publish(event_type, subject_id, subject_kind, data)
