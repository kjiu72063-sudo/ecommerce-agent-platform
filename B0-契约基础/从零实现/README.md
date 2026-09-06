# Agent Platform B0 Contracts

> 合同包版本：`0.2.0`  
> API 版本：`agent-platform/v1alpha1`  
> 当前状态：`approved`（已于 2026-09-01 通过评审）

---

## 概述

本目录保留 B0 契约的早期“从零实现”与教学材料。它将 B0 设计文档中的对象、状态机、版本、权限、幂等、租约和安全约束落实为 JSON Schema、Pydantic v2 模型、示例及一致性测试。

> **运行时定位**：本目录用于教学、历史追溯和契约演进对照，不是当前 monorepo 的运行时权威来源。新代码和新测试不得从本目录导入模块或注入其 `src/` 路径。当前权威契约包位于 `B0-契约基础/contracts/B0_agent_platform_contracts_v0.2.0/`，根级安装包位于 `src/agent_platform_contracts/`。

## 目录结构

```
从零实现/
├── src/                              # Python 源代码
│   └── agent_platform_contracts/
│       ├── __init__.py             # 包初始化
│       ├── models.py               # Pydantic 数据模型
│       ├── state_machines.py       # 状态机定义
│       └── policies.py             # 策略函数
├── schemas/                          # JSON Schema 文件
│   ├── common/                     # 公共类型（2 个）
│   ├── definitions/                # 定义对象（8 个）
│   └── runtime/                    # 运行对象（7 个）
├── examples/                         # 示例文件
│   ├── valid/                      # 有效示例（15 个）
│   └── invalid/                    # 无效示例（6 个）
├── state-machines/                   # 状态机 JSON（6 个）
├── conformance/                      # 一致性测试
│   ├── run.py                      # 测试运行器
│   └── test_contracts.py           # 测试用例（19 项）
├── scripts/                          # 工具脚本
│   └── export_contracts.py         # 导出脚本
├── pyproject.toml                    # 项目配置
└── requirements-dev.txt              # 开发依赖
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements-dev.txt
```

### 2. 运行测试

```bash
python conformance/run.py
```

预期输出：
```
Ran 19 tests in 0.316s

OK
```

### 3. 导出合同

```bash
python scripts/export_contracts.py
```

预期输出：
```
=== B0 契约包导出 ===

清单已生成: contract-manifest.json

摘要:
  Schema 文件: 17
  示例文件: 21
  状态机文件: 6
  总文件数: 44

导出完成！
```

## 核心组件

### 1. 15 个资源模型

**定义对象（8个）**：
- AgentSpec - Agent 定义
- SkillManifest - 技能清单
- ToolManifest - 工具清单
- PromptPackage - Prompt 包
- ModelPolicy - 模型策略
- ContextPolicy - Context 策略
- LoopProfile - Loop 配置
- PermissionProfile - 权限配置

**运行对象（7个）**：
- Task - 任务
- AgentRun - Agent 运行
- Checkpoint - 检查点
- ToolCall - 工具调用
- Approval - 审批
- Artifact - 产物
- Event - 事件

### 2. 6 个状态机

- definition - 定义对象生命周期
- task - 任务状态流转
- agent-run - Agent 运行状态
- tool-call - 工具调用状态
- approval - 审批状态
- artifact - 产物状态

### 3. 策略函数

- `canonical_json` - 规范化 JSON
- `canonical_sha256` - SHA-256 摘要
- `combine_permission_decisions` - 权限决策合并
- `can_auto_retry` - 自动重试检查
- `lease_allows_commit` - 租约提交检查
- `definition_is_resolvable` - 定义对象解析检查

## 关键设计决策

### 1. 统一资源信封

```json
{
  "api_version": "agent-platform/v1alpha1",
  "kind": "AgentSpec",
  "metadata": { ... },
  "spec": { ... },
  "status": { ... }
}
```

### 2. 强类型 ID

```
agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411
↑ 前缀    ↑ UUIDv7
```

### 3. 精确引用

```json
{
  "kind": "PromptPackage",
  "id": "prm_0198f6d0-...",
  "version": "1.0.0",
  "digest": "sha256:..."
}
```

### 4. 安全设计

- Deny 优先
- 跨租户默认拒绝
- Secret 不能进入 Context
- 高风险操作必须审批

### 5. 幂等控制

- Task: tenant + source + idempotency_key
- ToolCall: tool + target_resource + idempotency_key

## 文档

详细的实现文档位于 `实现文档/` 目录：

| 文档 | 内容 |
|---|---|
| 00-B0契约包实现总览.md | 文件夹结构说明 |
| 01-项目配置文件说明.md | 配置文件详解 |
| 02-models基础部分说明.md | 常量、类型别名详解 |
| 03-models基础部分详解.md | 公共类型详解 |
| 04-models公共类型详解.md | Metadata、引用、预算详解 |
| 05-定义对象模型详解.md | AgentSpec、SkillManifest 详解 |
| 06-实现完成总结.md | 核心代码完成总结 |
| 07-JSON-Schema基础详解.md | JSON Schema 基础知识 |
| 08-agent-spec-Schema详解.md | AgentSpec Schema 详解 |
| 09-JSON-Schema创建进度.md | Schema 创建进度 |
| 10-skill-manifest-Schema详解.md | SkillManifest Schema 详解 |
| 11-Schema创建进度总结.md | Schema 进度总结 |
| 12-tool-manifest与prompt-package详解.md | Tool 和 Prompt 详解 |
| 13-Schema创建进度总结.md | 定义对象 Schema 完成 |
| 14-ModelPolicy-ContextPolicy-LoopProfile-PermissionProfile详解.md | 策略对象详解 |
| 15-定义对象Schema完成总结.md | 定义对象完成 |
| 16-Task与AgentRun详解.md | 运行对象详解 |
| 17-运行对象Schema进度.md | 运行对象进度 |
| 18-Checkpoint-ToolCall-Approval-Artifact-Event详解.md | 运行对象详解 |
| 19-JSON-Schema全部完成总结.md | Schema 全部完成 |
| 20-task示例详解.md | Task 示例详解 |
| 21-示例文件创建进度.md | 示例文件进度 |
| 22-有效示例完成总结.md | 有效示例完成 |
| 23-无效示例与状态机完成总结.md | 无效示例和状态机 |
| 24-一致性测试完成总结.md | 一致性测试完成 |

## 技术栈

- **语言**：Python 3.11+
- **数据模型**：Pydantic v2
- **Schema**：JSON Schema Draft 2020-12
- **测试**：unittest

## 下一步

B0 契约包完成后，可以开始 B1 能力注册中心开发：

1. 数据库设计
2. Repository 层
3. 服务层
4. API 层
5. 测试

## 许可证

MIT License
