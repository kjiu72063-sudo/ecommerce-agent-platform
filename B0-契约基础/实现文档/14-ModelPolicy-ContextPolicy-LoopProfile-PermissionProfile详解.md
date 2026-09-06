# JSON Schema 定义对象详解 - ModelPolicy, ContextPolicy, LoopProfile, PermissionProfile

> 创建日期：2026-09-01

---

## 一、ModelPolicy（模型策略）

### 1.1 作用

定义任务选择模型、回退、预算、隐私和能力约束。

### 1.2 核心字段

#### ModelRoute（模型路由）

```json
"ModelRoute": {
  "route_id": "openai-gpt4",
  "provider": "openai",
  "model": "gpt-4-turbo",
  "priority": 100,
  "required_capabilities": ["tool_calling", "structured_output"],
  "conditions": { "task_type": "complex" }
}
```

**字段说明**：
| 字段 | 作用 |
|---|---|
| `route_id` | 路由唯一标识 |
| `provider` | 模型供应商 |
| `model` | 模型名称 |
| `priority` | 优先级（越高越优先） |
| `required_capabilities` | 必需能力 |
| `conditions` | 匹配条件 |

#### DataClassificationRule（数据分类规则）

```json
"DataClassificationRule": {
  "classification": "confidential",
  "allowed_providers": ["anthropic", "local"],
  "require_local": false
}
```

**数据分类级别**：
| 级别 | 说明 | 允许的供应商 |
|---|---|---|
| `public` | 公开数据 | 所有 |
| `internal` | 内部数据 | 受限 |
| `confidential` | 机密数据 | 严格受限 |
| `restricted` | 受限数据 | 仅本地 |

**为什么需要数据分类？**
- **合规要求**：敏感数据不能发送到未授权供应商
- **隐私保护**：防止数据泄露
- **安全策略**：高敏感数据必须本地处理

#### FallbackStep（回退步骤）

```json
"FallbackStep": {
  "route_id": "anthropic-claude",
  "on_error_codes": ["RATE_LIMITED", "TIMEOUT", "MODEL_ERROR"]
}
```

**回退链设计**：
```
主模型 (GPT-4) → 失败 → 回退模型 1 (Claude) → 失败 → 回退模型 2 (本地模型)
```

**为什么需要回退链？**
- **高可用**：主模型失败时有备选
- **成本优化**：不同任务使用不同模型
- **性能优化**：根据错误类型选择回退

#### CircuitBreaker（熔断器）

```json
"CircuitBreaker": {
  "failure_threshold": 5,
  "window_seconds": 60,
  "open_seconds": 300
}
```

**熔断器状态**：
```
closed (正常) → 失败次数达到阈值 → open (熔断) → 等待时间到 → half-open (半开) → 成功 → closed
```

**为什么需要熔断器？**
- **快速失败**：避免持续调用不可用服务
- **自动恢复**：一段时间后尝试恢复
- **保护系统**：防止级联故障

---

## 二、ContextPolicy（Context 策略）

### 2.1 作用

定义一次模型调用可以看到哪些信息、如何筛选、排序、压缩、脱敏和控制 Token。

### 2.2 Context 来源

```json
"ContextSourceType": {
  "enum": ["task", "agent_spec", "prompt", "thread", "memory", 
           "project_state", "skill", "tool_schema", "knowledge", 
           "artifact", "tool_result", "graph_state", "approval"]
}
```

| 来源 | 说明 | 优先级 |
|---|---|---|
| `task` | 当前任务 | 最高 |
| `agent_spec` | Agent 定义 | 高 |
| `prompt` | 固定指令 | 高 |
| `thread` | 对话历史 | 中 |
| `memory` | 长期记忆 | 中 |
| `skill` | 技能信息 | 中 |
| `tool_schema` | 工具定义 | 中 |
| `knowledge` | 知识库 | 低 |

### 2.3 核心字段

#### ContextTokenBudget（Token 预算）

```json
"ContextTokenBudget": {
  "total_tokens": 8000,
  "reserved_output_tokens": 2000,
  "per_source": {
    "task": 500,
    "agent_spec": 300,
    "prompt": 2000,
    "rag_knowledge": 3000,
    "memory": 500
  }
}
```

**约束**：
```
reserved_output_tokens < total_tokens
sum(per_source.values()) <= total_tokens - reserved_output_tokens
```

**为什么需要 Token 预算？**
- **成本控制**：Token 越多，成本越高
- **上下文限制**：模型有 Token 上限
- **优先级管理**：重要信息优先

#### RedactionPolicy（脱敏策略）

```json
"RedactionPolicy": {
  "redact_secrets": true,      // 必须脱敏 Secret
  "pii_mode": "mask",          // PII 脱敏模式
  "restricted_data_mode": "deny"  // 受限数据处理
}
```

**脱敏模式**：
| 模式 | 说明 | 示例 |
|---|---|---|
| `none` | 不脱敏 | 不处理 PII |
| `mask` | 遮罩 | `138****8888` |
| `remove` | 移除 | 完全删除 |

**为什么必须脱敏？**
- **隐私保护**：防止 PII 泄露
- **安全要求**：Secret 不能进入 Context
- **合规要求**：满足数据保护法规

#### CompactionPolicy（压缩策略）

```json
"CompactionPolicy": {
  "strategy": "extractive",
  "target_ratio": 0.7,
  "preserve_provenance": true
}
```

**压缩策略**：
| 策略 | 说明 |
|---|---|
| `extractive` | 抽取式：保留关键句子 |
| `abstractive` | 摘要式：生成摘要 |
| `hybrid` | 混合式：两者结合 |

**为什么需要压缩？**
- **Token 限制**：超出预算时必须压缩
- **信息密度**：保留关键信息，去除冗余
- **来源保留**：`preserve_provenance: true` 保留来源信息

---

## 三、LoopProfile（Loop 配置）

### 3.1 作用

定义 Agent Run 如何进行有界迭代，包括行动、观察、验证、修正、暂停和停止。

### 3.2 迭代策略

```json
"LoopStrategy": {
  "enum": ["single_pass", "react", "repair", "ralph", "review_refine"]
}
```

| 策略 | 说明 | 适用场景 |
|---|---|---|
| `single_pass` | 单次执行 | 简单问答 |
| `react` | 观察-行动循环 | 工具调用 |
| `repair` | 失败后修复 | 代码生成 |
| `ralph` | 外部验证器 | 需要外部评估 |
| `review_refine` | 审查-改进 | 内容生成 |

**React 策略流程**：
```
观察 (Observe) → 推理 (Think) → 行动 (Act) → 评估 (Evaluate) → 循环或停止
```

### 3.3 核心字段

#### StopCondition（停止条件）

```json
"StopCondition": {
  "condition_type": "success",
  "expression": "output.quality > 0.8"
}
```

**条件类型**：
| 类型 | 说明 |
|---|---|
| `success` | 成功条件 |
| `failure` | 失败条件 |
| `budget` | 预算条件 |
| `human_stop` | 人工停止 |
| `validator` | 验证器条件 |

**为什么必须有停止条件？**
- **防止无限循环**：必须有明确的退出条件
- **资源保护**：防止耗尽预算
- **可控性**：人工可以随时停止

#### CheckpointPolicy（Checkpoint 策略）

```json
"CheckpointPolicy": {
  "interval_iterations": 5,
  "on_tool_side_effect": true,
  "on_human_interrupt": true,
  "on_node_end": true
}
```

**Checkpoint 时机**：
- 每 N 次迭代
- 工具产生副作用后
- 人工中断时
- 节点结束时

**为什么需要 Checkpoint？**
- **可恢复**：失败后可以从 Checkpoint 恢复
- **审计**：记录执行过程
- **调试**：便于排查问题

#### RollbackPolicy（回滚策略）

```json
"RollbackPolicy": {
  "strategy": "compensating_action",
  "compensation_tool_refs": [...]
}
```

**回滚策略**：
| 策略 | 说明 |
|---|---|
| `none` | 不回滚 |
| `compensating_action` | 执行补偿动作 |
| `manual` | 人工回滚 |

**为什么需要回滚？**
- **副作用处理**：失败时撤销已执行的操作
- **一致性**：保证系统状态一致
- **可恢复性**：从错误中恢复

---

## 四、PermissionProfile（权限配置）

### 4.1 作用

定义 Agent、Skill、Tool 和 Task 的最大可用权限。

### 4.2 权限模型

**RBAC + ABAC + Capability**：
- **RBAC**：基于角色的访问控制
- **ABAC**：基于属性的访问控制
- **Capability**：能力声明

### 4.3 核心字段

#### PermissionRule（权限规则）

```json
"PermissionRule": {
  "effect": "allow",
  "actions": ["repository.read", "repository.write"],
  "resources": ["project:prj_demo/repository:*"],
  "conditions": {
    "environment": ["development", "sandbox"]
  }
}
```

**权限效果**：
| 效果 | 说明 | 优先级 |
|---|---|---|
| `allow` | 允许 | 最低 |
| `deny` | 拒绝 | 最高 |
| `require_approval` | 需要审批 | 中 |

**Deny 优先原则**：
```python
# 任何一层 deny，最终结果就是 deny
final_decision = combine_permission_decisions(["allow", "require_approval", "deny"])
# 结果：deny
```

**为什么 Deny 优先？**
- **安全第一**：宁可拒绝，不能误放
- **明确性**：显式拒绝优先于隐式允许
- **可审计**：便于追踪权限决策

#### 硬编码约束

```json
"default_decision": { "const": "deny" },
"deny_precedence": { "const": true },
"cross_tenant_default": { "const": "deny" }
```

**为什么硬编码？**
- **安全底线**：默认拒绝，不能修改
- **跨租户隔离**：防止数据泄露
- **Deny 优先**：始终生效

---

## 五、关键设计决策总结

### ModelPolicy

1. **数据分类**：敏感数据必须本地处理
2. **回退链**：高可用设计
3. **熔断器**：防止级联故障

### ContextPolicy

1. **Token 预算**：成本控制
2. **脱敏策略**：隐私保护
3. **压缩策略**：信息密度优化

### LoopProfile

1. **迭代策略**：支持多种执行模式
2. **停止条件**：防止无限循环
3. **Checkpoint**：可恢复性

### PermissionProfile

1. **Deny 优先**：安全第一
2. **跨租户隔离**：防止数据泄露
3. **默认拒绝**：最小权限原则

---

## 六、定义对象 Schema 完成！

所有 8 个定义对象 Schema 已创建完成：

```
schemas/definitions/
├── agent-spec.schema.json
├── skill-manifest.schema.json
├── tool-manifest.schema.json
├── prompt-package.schema.json
├── model-policy.schema.json
├── context-policy.schema.json
├── loop-profile.schema.json
└── permission-profile.schema.json
```

下一步：创建运行对象 Schema
