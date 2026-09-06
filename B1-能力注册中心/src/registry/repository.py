"""B1 能力注册中心 - 数据访问接口

定义 Repository 接口，分离数据访问逻辑。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from contextlib import asynccontextmanager


@dataclass
class DefinitionFilter:
    """定义对象查询过滤器"""
    kind: Optional[str] = None          # 资源类型
    namespace: Optional[str] = None     # 命名空间
    key: Optional[str] = None           # 标识符
    phase: Optional[str] = None         # 生命周期阶段
    tenant_id: Optional[str] = None     # 租户 ID
    labels: dict[str, str] = field(default_factory=dict)  # 标签过滤


class DefinitionRepository(ABC):
    @asynccontextmanager
    async def transaction(self):
        """事务边界；内存实现为 no-op，持久化实现覆盖。"""
        yield self

    """定义对象仓储接口
    
    所有数据访问都通过这个接口，不直接操作数据库。
    好处：
    1. 可以切换数据库（PostgreSQL → MySQL）
    2. 可以添加缓存层
    3. 便于单元测试（Mock）
    """
    
    @abstractmethod
    async def create(self, obj: dict) -> str:
        """创建定义对象
        
        Args:
            obj: 完整的资源对象（包含 api_version, kind, metadata, spec, status）
        
        Returns:
            str: 创建的对象 ID
        
        Raises:
            DuplicateError: 如果 namespace + key + version 已存在
        """
        pass
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[dict]:
        """按 ID 获取定义对象
        
        Args:
            id: 对象 ID（如 agt_0198f6d0-...）
        
        Returns:
            dict 或 None
        """
        pass
    
    @abstractmethod
    async def get_by_nkv(self, namespace: str, key: str, version: str) -> Optional[dict]:
        """按 namespace + key + version 获取定义对象
        
        Args:
            namespace: 命名空间
            key: 标识符
            version: 版本号
        
        Returns:
            dict 或 None
        """
        pass
    
    @abstractmethod
    async def update(self, id: str, expected_revision: int, updates: dict) -> bool:
        """乐观并发更新
        
        Args:
            id: 对象 ID
            expected_revision: 期望的修订号（如果已被其他人修改，更新失败）
            updates: 要更新的字段
        
        Returns:
            bool: 更新是否成功
        
        设计要点：
        - 使用 revision 实现乐观并发控制
        - 更新时检查 revision 是否匹配
        - 成功后 revision 自动递增
        """
        pass
    
    @abstractmethod
    async def list_by_filter(self, filter: DefinitionFilter, limit: int = 100, offset: int = 0) -> list[dict]:
        """按过滤器查询定义对象列表
        
        Args:
            filter: 查询过滤器
            limit: 最大返回数量
            offset: 偏移量
        
        Returns:
            list[dict]: 对象列表
        """
        pass
    
    @abstractmethod
    async def count_by_filter(self, filter: DefinitionFilter) -> int:
        """按过滤器统计数量
        
        Args:
            filter: 查询过滤器
        
        Returns:
            int: 对象数量
        """
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """删除定义对象
        
        Args:
            id: 对象 ID
        
        Returns:
            bool: 删除是否成功
        
        注意：
        - 只有 draft 状态的对象可以删除
        - active 状态的对象不能删除，只能 deprecated
        """
        pass
    
    @abstractmethod
    async def save_version(self, object_id: str, version: str, revision: int, 
                          content_digest: str, spec_snapshot: dict, created_by: dict) -> None:
        """保存版本历史
        
        Args:
            object_id: 对象 ID
            version: 版本号
            revision: 修订号
            content_digest: 内容摘要
            spec_snapshot: spec 快照
            created_by: 创建者
        """
        pass
    
    @abstractmethod
    async def get_versions(self, object_id: str) -> list[dict]:
        """获取对象的版本历史
        
        Args:
            object_id: 对象 ID
        
        Returns:
            list[dict]: 版本历史列表
        """
        pass
    
    @abstractmethod
    async def save_dependency(self, source_id: str, source_version: str,
                             target_id: str, target_version: str, dependency_type: str) -> None:
        """保存依赖关系
        
        Args:
            source_id: 源对象 ID
            source_version: 源对象版本
            target_id: 目标对象 ID
            target_version: 目标对象版本
            dependency_type: 依赖类型（prompt/context/model/loop/permission/skill/tool）
        """
        pass
    
    @abstractmethod
    async def get_dependencies(self, id: str, version: str) -> list[dict]:
        """获取对象的依赖关系
        
        Args:
            id: 对象 ID
            version: 对象版本
        
        Returns:
            list[dict]: 依赖列表
        """
        pass
    
    async def get_audit_logs(self, resource_id: str = None, actor_id: str = None, limit: int = 100) -> list[dict]:
        """查询审计日志；具体仓储可提供高效实现。"""
        return []

    @abstractmethod
    async def save_audit_log(self, action: str, resource_id: str, resource_kind: str,
                            actor_type: str, actor_id: str, tenant_id: str = None,
                            before_state: dict = None, after_state: dict = None,
                            details: dict = None) -> None:
        """保存审计日志
        
        Args:
            action: 操作类型（create/update/transition/delete）
            resource_id: 资源 ID
            resource_kind: 资源类型
            actor_type: 操作者类型
            actor_id: 操作者 ID
            tenant_id: 租户 ID
            before_state: 变更前状态
            after_state: 变更后状态
            details: 变更详情
        """
        pass
