"""B2 状态与持久化 - in-memory prototype 仓储实现

用于开发和测试；SQLite 后端见 sqlite_repositories.py。
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Optional

from .repositories import (
    CheckpointRepository,
    EventRepository,
    RunRepository,
    TaskFilter,
    TaskRepository,
)


class InMemoryTaskRepository(TaskRepository):
    """内存版任务仓储"""

    def __init__(self):
        self._tasks: dict[str, dict] = {}

    async def create_task(self, task: dict) -> str:
        task_id = task["metadata"]["id"]
        if task_id in self._tasks:
            raise ValueError(f"Task already exists: {task_id}")
        self._tasks[task_id] = copy.deepcopy(task)
        return task_id

    async def get_task(self, task_id: str) -> Optional[dict]:
        task = self._tasks.get(task_id)
        return copy.deepcopy(task) if task else None

    async def update_task_status(self, task_id: str, phase: str, updates: dict = None) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task["status"]["phase"] = phase
        if updates:
            task["status"].update(updates)
        task["metadata"]["revision"] = task["metadata"].get("revision", 0) + 1
        return True

    async def list_tasks(self, filter: TaskFilter, limit: int = 100) -> list[dict]:
        results = []
        for task in self._tasks.values():
            if self._matches_filter(task, filter):
                results.append(copy.deepcopy(task))
        return results[:limit]

    async def find_by_idempotency_key(
        self, tenant_id: str, source_type: str, key: str
    ) -> Optional[dict]:
        for task in self._tasks.values():
            spec = task.get("spec", {})
            idem_key = spec.get("idempotency_key", "")
            if idem_key == f"{tenant_id}:{source_type}:{key}":
                return copy.deepcopy(task)
        return None

    def _matches_filter(self, task: dict, filter: TaskFilter) -> bool:
        status = task.get("status", {})
        spec = task.get("spec", {})
        scope = task.get("metadata", {}).get("scope", {})
        if filter.phase and status.get("phase") != filter.phase:
            return False
        if filter.domain and spec.get("domain") != filter.domain:
            return False
        if filter.tenant_id and scope.get("tenant_id") != filter.tenant_id:
            return False
        return True


class InMemoryRunRepository(RunRepository):
    """内存版 AgentRun 仓储"""

    def __init__(self):
        self._runs: dict[str, dict] = {}
        self._run_versions: dict[str, list[dict]] = {}

    async def create_run(self, run: dict) -> str:
        run_id = run["metadata"]["id"]
        if run_id in self._runs:
            raise ValueError(f"Run already exists: {run_id}")
        self._runs[run_id] = copy.deepcopy(run)
        return run_id

    async def get_run(self, run_id: str) -> Optional[dict]:
        run = self._runs.get(run_id)
        return copy.deepcopy(run) if run else None

    async def update_run_status(self, run_id: str, phase: str, updates: dict = None) -> bool:
        run = self._runs.get(run_id)
        if not run:
            return False
        run["status"]["phase"] = phase
        if updates:
            run["status"].update(updates)
        run["metadata"]["revision"] = run["metadata"].get("revision", 0) + 1
        return True

    async def get_runs_by_task(self, task_id: str) -> list[dict]:
        results = []
        for run in self._runs.values():
            if run.get("spec", {}).get("task_ref", {}).get("id") == task_id:
                results.append(copy.deepcopy(run))
        return sorted(results, key=lambda x: x["spec"].get("attempt", 0))

    async def save_version(self, run_id: str, spec_snapshot: dict) -> None:
        self._run_versions.setdefault(run_id, []).append(
            {
                "run_id": run_id,
                "spec_snapshot": copy.deepcopy(spec_snapshot),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def get_versions(self, run_id: str) -> list[dict]:
        return copy.deepcopy(self._run_versions.get(run_id, []))


class InMemoryCheckpointRepository(CheckpointRepository):
    """内存版 Checkpoint 仓储"""

    def __init__(self):
        self._checkpoints: dict[str, dict] = {}

    async def create_checkpoint(self, checkpoint: dict) -> str:
        checkpoint_id = checkpoint["metadata"]["id"]
        if checkpoint_id in self._checkpoints:
            raise ValueError(f"Checkpoint already exists: {checkpoint_id}")
        self._checkpoints[checkpoint_id] = copy.deepcopy(checkpoint)
        return checkpoint_id

    async def get_checkpoint(self, checkpoint_id: str) -> dict | None:
        checkpoint = self._checkpoints.get(checkpoint_id)
        return copy.deepcopy(checkpoint) if checkpoint else None

    async def get_latest_checkpoint(self, run_id: str) -> dict | None:
        found = None
        for checkpoint in self._checkpoints.values():
            if checkpoint.get("spec", {}).get("run_ref", {}).get("id") == run_id:
                if found is None or checkpoint["spec"]["sequence"] > found["spec"]["sequence"]:
                    found = checkpoint
        return copy.deepcopy(found) if found else None

    async def list_checkpoints(self, run_id: str) -> list[dict]:
        results = [
            copy.deepcopy(cp)
            for cp in self._checkpoints.values()
            if cp.get("spec", {}).get("run_ref", {}).get("id") == run_id
        ]
        return sorted(results, key=lambda x: x["spec"].get("sequence", 0))


class InMemoryEventRepository(EventRepository):
    """内存版事件仓储"""

    def __init__(self):
        self._events: list[dict] = []

    async def save_event(self, event: dict) -> str:
        event_id = event["metadata"]["id"]
        self._events.append(copy.deepcopy(event))
        return event_id

    async def get_events(self, subject_id: str, after_sequence: int = 0) -> list[dict]:
        results = []
        for event in self._events:
            subject_ref = event.get("spec", {}).get("subject_ref", {})
            sequence = event.get("spec", {}).get("sequence", 0)
            if subject_ref.get("id") == subject_id and sequence > after_sequence:
                results.append(copy.deepcopy(event))
        return sorted(results, key=lambda x: x["spec"].get("sequence", 0))

    async def get_next_sequence(self, subject_id: str) -> int:
        max_seq = 0
        for event in self._events:
            subject_ref = event.get("spec", {}).get("subject_ref", {})
            sequence = event.get("spec", {}).get("sequence", 0)
            if subject_ref.get("id") == subject_id and sequence > max_seq:
                max_seq = sequence
        return max_seq + 1
