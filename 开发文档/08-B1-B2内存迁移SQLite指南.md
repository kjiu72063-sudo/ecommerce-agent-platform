# B1/B2 从内存原型迁移到 SQLite 指南

## 当前定位

B1、B2 同时保留两种后端：

- `InMemory*Repository`：`in-memory prototype`，适合单元测试、演示和快速开发，进程结束后数据丢失。
- `SQLite*Repository`：第一版本地持久化闭环，适合单机开发、集成测试和验收，不代表生产级数据库方案。

B1/B2 运行时依赖的 B0 契约唯一来源是：

```text
B0-契约基础/contracts/B0_agent_platform_contracts_v0.2.0/agent-platform-contracts-v0.2.0
```

`B0-契约基础/从零实现/` 仅作为历史/教学对照，不应被运行时代码或测试重新引用。

## B1 迁移方式

```python
from registry import RegistryService, SQLiteDefinitionRepository

repo = SQLiteDefinitionRepository("b1_registry.sqlite3")
service = RegistryService(repo)
```

SQLite 后端自动创建以下表：

- `definitions`：当前定义对象快照；
- `definition_versions`：版本历史；
- `definition_dependencies`：精确版本依赖；
- `audit_logs`：审计日志。

`RegistryService.register_definition()` 使用 Repository 的事务上下文，注册对象、保存版本、写入依赖和审计日志要么全部提交，要么全部回滚。

## B2 迁移方式

B2 的 Task、Run、Event 必须共享同一个 `SQLiteRuntimeStore`：

```python
from runtime.sqlite_repositories import (
    SQLiteRuntimeStore, SQLiteTaskRepository, SQLiteEventRepository,
)

store = SQLiteRuntimeStore("b2_runtime.sqlite3")
tasks = SQLiteTaskRepository(store=store)
events = SQLiteEventRepository(store=store)
```

TaskService 检测到 Task/Event 仓储共享同一个 Store 后，会把状态更新和对应事件写入放在同一个事务中。事件失败时，Task 状态不会提前提交。

SQLite Event 表通过 `(subject_id, sequence)` 唯一约束防止同一主体的序号重复。

## 测试要求

迁移后至少执行：

```text
B1：内存仓储测试 + SQLite 重启恢复测试 + 注册失败回滚测试
B2：内存 Task 测试 + SQLite 事件流测试 + Event 写入失败回滚测试
```

回滚测试应验证数据库重新打开后没有半成品数据或错误状态。

## 当前限制与升级预留

1. SQLite 后端使用 Python 标准库同步 `sqlite3`，通过异步 Repository 接口暴露；高并发生产环境应替换为 SQLAlchemy Async/asyncpg 等实现。
2. 当前事务边界是单进程、单数据库连接范围；跨进程消息投递、Transactional Outbox 和分布式一致性属于后续版本。
3. B2 Checkpoint Service/API 尚未实现；不能将当前 Task/Event 持久化误称为完整恢复能力。
4. B1 已保存直接依赖，但递归解析、循环检测和拓扑排序仍待后续实现。
5. 替换数据库时应保持 `DefinitionRepository`、`TaskRepository`、`EventRepository` 和共享 Store/事务语义不变，上层 Service 不应依赖 SQLite 细节。
