"""B1 依赖解析器 - 递归解析定义对象之间的依赖图。

按 authoritative B0 的生命周期规则解析依赖：
- 目标对象必须已存在；
- 引用版本必须与目标当前版本精确匹配；
- 目标必须处于可解析状态（new_run=active；resume_run=active/deprecated）；
- 递归探测目标自身的依赖，检测循环依赖，并输出拓扑序。
"""

from __future__ import annotations

from typing import Any

from agent_platform_contracts.policies import definition_is_resolvable

from .repository import DefinitionRepository


class DependencyResolveError(Exception):
    """依赖解析失败（目标缺失、版本不匹配或状态不可解析）。"""


class DependencyCycleError(DependencyResolveError):
    """检测到循环依赖。"""


class DependencyResolver:
    """在 DefinitionRepository 之上执行递归依赖解析。"""

    def __init__(self, repository: DefinitionRepository):
        self.repo = repository

    async def resolve(
        self, root_id: str, root_version: str, purpose: str = "new_run"
    ) -> dict[str, Any]:
        """解析以 (root_id, root_version) 为根的依赖图。

        返回：
            root: 根对象 ID
            root_version: 根对象版本
            nodes: 所有已解析对象（含根），按访问顺序去重
            edges: 遍历到的全部依赖记录
            topological_order: 深度优先后序的拓扑序（依赖在前）
        """
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        async def visit(object_id: str, version: str) -> None:
            obj = await self.repo.get_by_id(object_id)
            if not obj:
                raise DependencyResolveError(f"Dependency target not found: {object_id}")
            if obj["metadata"]["version"] != version:
                raise DependencyResolveError(
                    f"Version mismatch for {object_id}: referenced '{version}', "
                    f"actual '{obj['metadata']['version']}'"
                )
            phase = obj["status"]["phase"]
            if not definition_is_resolvable(definition_phase=phase, purpose=purpose):
                raise DependencyResolveError(
                    f"Definition {object_id} in '{phase}' is not resolvable for '{purpose}'"
                )

            if object_id in visiting:
                raise DependencyCycleError(f"Circular dependency detected involving '{object_id}'")
            if object_id in visited:
                return

            visiting.add(object_id)
            dependencies = await self.repo.get_dependencies(object_id, version)
            for dep in dependencies:
                edges.append(dep)
                await visit(dep["target_id"], dep["target_version"])
            visiting.discard(object_id)
            visited.add(object_id)
            order.append(object_id)
            nodes[object_id] = obj

        await visit(root_id, root_version)
        return {
            "root": root_id,
            "root_version": root_version,
            "nodes": list(nodes.values()),
            "edges": edges,
            "topological_order": order,
        }
