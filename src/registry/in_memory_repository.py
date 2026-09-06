"""B1 能力注册中心 - in-memory prototype Repository 实现

用于开发、测试和演示；程序重启后数据丢失。SQLite 后端见 sqlite_repository.py。
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Optional

from .repository import DefinitionFilter, DefinitionRepository


class InMemoryDefinitionRepository(DefinitionRepository):
    """内存版定义对象仓储

    所有数据存储在内存中，程序重启后丢失。
    用途：开发、测试、演示
    """

    def __init__(self):
        self._objects: dict[str, dict] = {}  # id -> object
        self._versions: dict[str, list[dict]] = {}  # object_id -> versions
        self._dependencies: list[dict] = []  # 所有依赖
        self._audit_logs: list[dict] = []  # 所有审计日志

    async def create(self, obj: dict) -> str:
        """创建定义对象"""
        obj_id = obj["metadata"]["id"]

        if obj_id in self._objects:
            raise ValueError(f"Object already exists: {obj_id}")

        # 深拷贝，防止外部修改
        self._objects[obj_id] = copy.deepcopy(obj)

        return obj_id

    async def get_by_id(self, id: str) -> Optional[dict]:
        """按 ID 获取"""
        obj = self._objects.get(id)
        return copy.deepcopy(obj) if obj else None

    async def get_by_nkv(self, namespace: str, key: str, version: str) -> Optional[dict]:
        """按 namespace + key + version 获取"""
        for obj in self._objects.values():
            meta = obj.get("metadata", {})
            if (
                meta.get("namespace") == namespace
                and meta.get("key") == key
                and meta.get("version") == version
            ):
                return copy.deepcopy(obj)
        return None

    async def update(self, id: str, expected_revision: int, updates: dict) -> bool:
        """乐观并发更新"""
        obj = self._objects.get(id)
        if not obj:
            return False

        # 检查 revision
        if obj["metadata"]["revision"] != expected_revision:
            return False

        # 应用更新
        for key, value in updates.items():
            if key == "status":
                obj["status"] = value
            elif key == "metadata":
                obj["metadata"].update(value)
            else:
                obj[key] = value

        # 递增 revision
        obj["metadata"]["revision"] = expected_revision + 1

        return True

    async def list_by_filter(
        self, filter: DefinitionFilter, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """按过滤器查询"""
        results = []

        for obj in self._objects.values():
            if self._matches_filter(obj, filter):
                results.append(copy.deepcopy(obj))

        # 排序：按创建时间降序
        results.sort(key=lambda x: x["metadata"].get("created_at", ""), reverse=True)

        return results[offset : offset + limit]

    async def count_by_filter(self, filter: DefinitionFilter) -> int:
        """按过滤器统计数量"""
        count = 0
        for obj in self._objects.values():
            if self._matches_filter(obj, filter):
                count += 1
        return count

    async def delete(self, id: str) -> bool:
        """删除定义对象"""
        if id not in self._objects:
            return False

        obj = self._objects[id]
        phase = obj.get("status", {}).get("phase")

        # 只有 draft 状态可以删除
        if phase != "draft":
            raise ValueError(f"Cannot delete object in {phase} state")

        del self._objects[id]
        return True

    async def save_version(
        self,
        object_id: str,
        version: str,
        revision: int,
        content_digest: str,
        spec_snapshot: dict,
        created_by: dict,
    ) -> None:
        """保存版本历史"""
        if object_id not in self._versions:
            self._versions[object_id] = []

        self._versions[object_id].append(
            {
                "object_id": object_id,
                "version": version,
                "revision": revision,
                "content_digest": content_digest,
                "spec_snapshot": copy.deepcopy(spec_snapshot),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": created_by,
            }
        )

    async def get_versions(self, object_id: str) -> list[dict]:
        """获取版本历史"""
        return copy.deepcopy(self._versions.get(object_id, []))

    async def save_dependency(
        self,
        source_id: str,
        source_version: str,
        target_id: str,
        target_version: str,
        dependency_type: str,
    ) -> None:
        """保存依赖关系"""
        # 检查是否已存在
        for dep in self._dependencies:
            if (
                dep["source_id"] == source_id
                and dep["source_version"] == source_version
                and dep["target_id"] == target_id
                and dep["target_version"] == target_version
                and dep["dependency_type"] == dependency_type
            ):
                return  # 已存在，跳过

        self._dependencies.append(
            {
                "source_id": source_id,
                "source_version": source_version,
                "target_id": target_id,
                "target_version": target_version,
                "dependency_type": dependency_type,
            }
        )

    async def get_dependencies(self, id: str, version: str) -> list[dict]:
        """获取依赖关系"""
        return [
            copy.deepcopy(dep)
            for dep in self._dependencies
            if dep["source_id"] == id and dep["source_version"] == version
        ]

    async def save_audit_log(
        self,
        action: str,
        resource_id: str,
        resource_kind: str,
        actor_type: str,
        actor_id: str,
        tenant_id: str = None,
        before_state: dict = None,
        after_state: dict = None,
        details: dict = None,
    ) -> None:
        """保存审计日志"""
        self._audit_logs.append(
            {
                "action": action,
                "resource_id": resource_id,
                "resource_kind": resource_kind,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "before_state": copy.deepcopy(before_state),
                "after_state": copy.deepcopy(after_state),
                "details": copy.deepcopy(details or {}),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def get_audit_logs(
        self, resource_id: str = None, actor_id: str = None, limit: int = 100
    ) -> list[dict]:
        logs = self._audit_logs
        if resource_id:
            logs = [log for log in logs if log["resource_id"] == resource_id]
        if actor_id:
            logs = [log for log in logs if log["actor_id"] == actor_id]
        logs = sorted(logs, key=lambda x: x.get("created_at", ""), reverse=True)
        return copy.deepcopy(logs[:limit])

    def _matches_filter(self, obj: dict, filter: DefinitionFilter) -> bool:
        """检查对象是否匹配过滤器"""
        meta = obj.get("metadata", {})
        status = obj.get("status", {})

        if filter.kind and obj.get("kind") != filter.kind:
            return False
        if filter.namespace and meta.get("namespace") != filter.namespace:
            return False
        if filter.key and meta.get("key") != filter.key:
            return False
        if filter.phase and status.get("phase") != filter.phase:
            return False
        if filter.tenant_id and meta.get("scope", {}).get("tenant_id") != filter.tenant_id:
            return False

        # 标签过滤
        if filter.labels:
            obj_labels = meta.get("labels", {})
            for k, v in filter.labels.items():
                if obj_labels.get(k) != v:
                    return False

        return True
