"""B1 能力注册中心 - 服务层

实现注册中心的核心业务逻辑。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from agent_platform_contracts.models import RESOURCE_MODELS
from agent_platform_contracts.policies import canonical_sha256
from agent_platform_contracts.state_machines import StateTransitionError, transition

from .repository import DefinitionFilter, DefinitionRepository


class RegistryService:
    """注册中心核心服务

    职责：
    1. 注册新的定义对象
    2. 迁移定义对象状态
    3. 解析依赖关系
    4. 查询定义对象
    """

    def __init__(self, repository: DefinitionRepository):
        self.repo = repository

    # ============================================================
    # 注册
    # ============================================================

    async def register_definition(self, kind: str, payload: dict, actor: dict) -> dict:
        """注册新的定义对象

        Args:
            kind: 资源类型（如 "agent-spec", "skill-manifest"）
            payload: 完整的资源对象
            actor: 操作者信息 {"actor_type": "...", "actor_id": "..."}

        Returns:
            dict: {"id": "...", "content_digest": "..."}

        流程：
        1. 使用 Pydantic 模型验证
        2. 计算内容摘要
        3. 检查是否已存在
        4. 持久化
        5. 保存版本历史
        6. 保存依赖关系
        7. 记录审计日志
        """
        # 1. 使用 Pydantic 模型验证
        # 支持 kebab-case（API 输入）和 PascalCase（B0 模型）
        model_class = RESOURCE_MODELS.get(kind)
        if not model_class:
            # 尝试 kebab-case 转换
            kebab_kind = kind.replace("_", "-")
            model_class = RESOURCE_MODELS.get(kebab_kind)
        if not model_class:
            raise ValueError(f"Unknown resource kind: {kind}")

        validated = model_class.model_validate(payload)

        # 2. 计算内容摘要（使用 mode='json' 确保 Decimal 等类型可序列化）
        spec_dict = validated.spec.model_dump(mode="json")
        content_digest = canonical_sha256(spec_dict)

        # 3. 检查是否已存在
        metadata = validated.metadata
        existing = await self.repo.get_by_nkv(metadata.namespace, metadata.key, metadata.version)
        if existing:
            raise ValueError(
                f"Definition already exists: {metadata.namespace}/{metadata.key}/{metadata.version}"
            )

        # 4. 持久化（使用 mode='json' 确保类型可序列化）
        obj_dict = validated.model_dump(mode="json")
        obj_dict["metadata"]["content_digest"] = content_digest
        async with self.repo.transaction():
            obj_id = await self.repo.create(obj_dict)
            await self.repo.save_version(
                object_id=obj_id,
                version=metadata.version,
                revision=metadata.revision,
                content_digest=content_digest,
                spec_snapshot=spec_dict,
                created_by=actor,
            )
            await self._extract_and_save_dependencies(obj_id, metadata.version, spec_dict, kind)
            await self.repo.save_audit_log(
                action="create",
                resource_id=obj_id,
                resource_kind=kind,
                actor_type=actor.get("actor_type", "unknown"),
                actor_id=actor.get("actor_id", "unknown"),
                after_state=obj_dict,
            )

        return {"id": obj_id, "content_digest": content_digest}

    # ============================================================
    # 状态迁移
    # ============================================================

    async def transition_state(
        self, id: str, target_phase: str, reason: str = None, actor: dict = None
    ) -> dict:
        """迁移定义对象状态

        Args:
            id: 对象 ID
            target_phase: 目标阶段
            reason: 迁移原因
            actor: 操作者信息

        Returns:
            dict: {"id": "...", "phase": "..."}

        流程：
        1. 获取当前对象
        2. 验证状态迁移
        3. 更新状态
        4. 记录审计日志
        """
        # 1. 获取当前对象
        obj = await self.repo.get_by_id(id)
        if not obj:
            raise ValueError(f"Definition not found: {id}")

        current_phase = obj["status"]["phase"]

        # 2. 验证状态迁移
        try:
            transition("definition", current_phase, target_phase)
        except StateTransitionError as e:
            raise ValueError(f"Invalid transition: {e}")

        # 3. 更新状态
        new_status = {
            "phase": target_phase,
            "observed_revision": obj["metadata"]["revision"],
            "reason": reason,
        }

        # active 状态需要激活时间
        if target_phase == "active":
            new_status["activated_at"] = datetime.now(timezone.utc).isoformat()

        success = await self.repo.update(id, obj["metadata"]["revision"], {"status": new_status})

        if not success:
            raise ValueError("Concurrent modification detected")

        # 4. 记录审计日志
        if actor:
            await self.repo.save_audit_log(
                action="transition",
                resource_id=id,
                resource_kind=obj["kind"],
                actor_type=actor.get("actor_type", "unknown"),
                actor_id=actor.get("actor_id", "unknown"),
                before_state={"phase": current_phase},
                after_state={"phase": target_phase},
                details={"reason": reason},
            )

        return {"id": id, "phase": target_phase}

    # ============================================================
    # 更新
    # ============================================================

    async def update_definition(self, id: str, payload: dict, actor: dict) -> dict:
        """更新定义对象

        使用乐观并发控制：更新后重新计算 content_digest。
        """
        # 获取当前对象
        obj = await self.repo.get_by_id(id)
        if not obj:
            raise ValueError(f"Definition not found: {id}")

        # 使用 Pydantic 验证新 payload
        kind = obj["kind"].lower().replace("-", "_")
        # 从 RESOURCE_MODELS 查找
        model_class = None
        for key, cls in RESOURCE_MODELS.items():
            if cls.__name__.lower().replace("resource", "") == kind.replace("_", ""):
                model_class = cls
                break

        if not model_class:
            # 使用 kind 字符串查找
            kind_map = {
                "agentspec": "agent-spec",
                "skillmanifest": "skill-manifest",
                "toolmanifest": "tool-manifest",
                "promptpackage": "prompt-package",
                "modelpolicy": "model-policy",
                "contextpolicy": "context-policy",
                "loopprofile": "loop-profile",
                "permissionprofile": "permission-profile",
            }
            model_class = RESOURCE_MODELS.get(kind_map.get(kind, kind))

        if not model_class:
            raise ValueError(f"Cannot find model for kind: {obj['kind']}")

        validated = model_class.model_validate(payload)

        # 计算新的 content_digest
        spec_dict = validated.spec.model_dump(mode="json")
        new_digest = canonical_sha256(spec_dict)

        # 更新对象
        new_metadata = obj["metadata"].copy()
        new_metadata["content_digest"] = new_digest

        async with self.repo.transaction():
            success = await self.repo.update(
                id, obj["metadata"]["revision"], {"spec": spec_dict, "metadata": new_metadata}
            )
            if not success:
                raise ValueError("Concurrent modification detected")
            await self.repo.save_version(
                object_id=id,
                version=obj["metadata"]["version"],
                revision=obj["metadata"]["revision"] + 1,
                content_digest=new_digest,
                spec_snapshot=spec_dict,
                created_by=actor,
            )

        # 记录审计日志
        await self.repo.save_audit_log(
            action="update",
            resource_id=id,
            resource_kind=obj["kind"],
            actor_type=actor.get("actor_type", "unknown"),
            actor_id=actor.get("actor_id", "unknown"),
            after_state={"content_digest": new_digest},
        )

        return {"id": id, "content_digest": new_digest}

    # ============================================================
    # 删除
    # ============================================================

    async def delete_definition(self, id: str, actor: dict) -> bool:
        """删除定义对象

        只有 draft 状态的对象可以删除。
        """
        obj = await self.repo.get_by_id(id)
        if not obj:
            raise ValueError(f"Definition not found: {id}")

        phase = obj["status"]["phase"]
        if phase != "draft":
            raise ValueError(
                f"Cannot delete object in '{phase}' state. Only 'draft' objects can be deleted."
            )

        success = await self.repo.delete(id)

        if success:
            await self.repo.save_audit_log(
                action="delete",
                resource_id=id,
                resource_kind=obj["kind"],
                actor_type=actor.get("actor_type", "unknown"),
                actor_id=actor.get("actor_id", "unknown"),
                before_state={"phase": phase},
            )

        return success

    # ============================================================
    # 查询
    # ============================================================

    async def get_definition(self, id: str) -> Optional[dict]:
        """获取定义对象"""
        return await self.repo.get_by_id(id)

    async def list_definitions(
        self, filter: DefinitionFilter, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """查询定义对象列表"""
        return await self.repo.list_by_filter(filter, limit, offset)

    async def resolve_definition(self, id: str, version: str, purpose: str = "new_run") -> dict:
        """解析定义对象（用于 AgentRun 启动）

        规则：
        - 新 Run 只能解析 active 状态
        - 恢复 Run 可以解析 active 和 deprecated 状态
        """
        from agent_platform_contracts.policies import definition_is_resolvable

        obj = await self.repo.get_by_id(id)
        if not obj:
            raise ValueError(f"Definition not found: {id}")

        if obj["metadata"]["version"] != version:
            raise ValueError(
                f"Version mismatch: expected {version}, got {obj['metadata']['version']}"
            )

        # 验证对象是否处于可解析状态
        phase = obj["status"]["phase"]
        if not definition_is_resolvable(definition_phase=phase, purpose=purpose):
            raise ValueError(f"Definition in '{phase}' state is not resolvable for '{purpose}'")

        return obj

    # ============================================================
    # 依赖解析
    # ============================================================

    async def resolve_dependency_graph(
        self, id: str, version: str, purpose: str = "new_run"
    ) -> dict:
        """递归解析以 (id, version) 为根的依赖图。"""
        from .dependency_resolver import DependencyResolver

        return await DependencyResolver(self.repo).resolve(id, version, purpose)

    async def _extract_and_save_dependencies(
        self, source_id: str, source_version: str, spec: dict, kind: str
    ) -> None:
        """提取并保存依赖关系；引用必须显式携带版本。"""
        ref_fields = {
            "prompt_package_ref": "prompt",
            "context_policy_ref": "context",
            "model_policy_ref": "model",
            "loop_profile_ref": "loop",
            "permission_profile_ref": "permission",
        }
        for field_name, dep_type in ref_fields.items():
            ref = spec.get(field_name)
            if ref and "id" in ref:
                await self._save_dependency_checked(source_id, source_version, ref, dep_type)
        for ref_list_name, dep_type in [
            ("startup_skill_refs", "skill"),
            ("startup_tool_refs", "tool"),
            ("required_tools", "tool"),
            ("required_skills", "skill"),
        ]:
            ref_list = spec.get(ref_list_name, [])
            for ref in ref_list:
                actual_ref = ref.get("tool_ref") or ref.get("skill_ref") or ref
                if actual_ref and "id" in actual_ref:
                    await self._save_dependency_checked(
                        source_id, source_version, actual_ref, dep_type
                    )

    async def _save_dependency_checked(
        self, source_id: str, source_version: str, ref: dict, dependency_type: str
    ) -> None:
        """依赖引用必须显式携带版本；目标存在性与递归解析由后续 DependencyResolver 处理。"""
        if not ref.get("version"):
            raise ValueError(
                f"Dependency {dependency_type} reference '{ref.get('id')}' is missing 'version'"
            )
        await self.repo.save_dependency(
            source_id=source_id,
            source_version=source_version,
            target_id=ref["id"],
            target_version=ref.get("version"),
            dependency_type=dependency_type,
        )
