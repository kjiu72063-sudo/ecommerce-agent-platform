"""B2 状态与持久化 - 运行时仓储接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TaskFilter:
    """任务查询过滤器"""
    kind: Optional[str] = None
    phase: Optional[str] = None
    tenant_id: Optional[str] = None
    domain: Optional[str] = None


class TaskRepository(ABC):
    """任务仓储接口"""

    @abstractmethod
    async def create_task(self, task: dict) -> str:
        """创建任务"""
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务"""
        pass

    @abstractmethod
    async def update_task_status(self, task_id: str, phase: str, updates: dict = None) -> bool:
        """更新任务状态"""
        pass

    @abstractmethod
    async def list_tasks(self, filter: TaskFilter, limit: int = 100) -> list[dict]:
        """查询任务列表"""
        pass

    @abstractmethod
    async def find_by_idempotency_key(self, tenant_id: str, source_type: str, key: str) -> Optional[dict]:
        """按幂等键查找任务"""
        pass


class RunRepository(ABC):
    """AgentRun 仓储接口"""

    @abstractmethod
    async def create_run(self, run: dict) -> str:
        """创建 AgentRun"""
        pass

    @abstractmethod
    async def save_version(self, run_id: str, spec_snapshot: dict) -> None:
        """保存 Run 版本快照"""
        pass

    @abstractmethod
    async def get_versions(self, run_id: str) -> list[dict]:
        """获取 Run 版本历史"""
        pass

    @abstractmethod
    async def get_run(self, run_id: str) -> Optional[dict]:
        """获取 AgentRun"""
        pass

    @abstractmethod
    async def update_run_status(self, run_id: str, phase: str, updates: dict = None) -> bool:
        """更新 AgentRun 状态"""
        pass

    @abstractmethod
    async def get_runs_by_task(self, task_id: str) -> list[dict]:
        """获取任务的所有 Run"""
        pass


class CheckpointRepository(ABC):
    """Checkpoint 仓储接口"""

    @abstractmethod
    async def create_checkpoint(self, checkpoint: dict) -> str:
        """创建 Checkpoint"""
        pass

    @abstractmethod
    async def get_checkpoint(self, checkpoint_id: str) -> Optional[dict]:
        """获取 Checkpoint"""
        pass

    @abstractmethod
    async def get_latest_checkpoint(self, run_id: str) -> Optional[dict]:
        """获取某 Run 的最新 Checkpoint"""
        pass

    @abstractmethod
    async def list_checkpoints(self, run_id: str) -> list[dict]:
        """按 Run 查询 Checkpoint 列表"""
        pass


class EventRepository(ABC):
    """事件仓储接口"""

    @abstractmethod
    async def save_event(self, event: dict) -> str:
        """保存事件"""
        pass

    @abstractmethod
    async def get_events(self, subject_id: str, after_sequence: int = 0) -> list[dict]:
        """获取事件流"""
        pass

    @abstractmethod
    async def get_next_sequence(self, subject_id: str) -> int:
        """获取下一个序号"""
        pass

