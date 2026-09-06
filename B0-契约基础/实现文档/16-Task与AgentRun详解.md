# JSON Schema 运行对象详解 - Task 与 AgentRun

> 创建日期：2026-09-01

---

## 一、Task（任务）

### 1.1 什么是 Task？

**Task** 是平台接收的可调度工作单元，描述用户希望达成的目标、输入、约束、优先级、预算和期望产物。

**类比**：
- Task ≈ 工单/需求单
- 用户提交一个任务，平台调度执行

### 1.2 核心字段

#### intent（意图）

```json
"intent": {
  "type": "string",
  "pattern": "^[a-z][a-z0-9_.:-]{2,127}$"
}
```

**示例**：
- `development.implement_feature` - 实现功能
- `ecommerce.presale_consultation` - 售前咨询
- `content.generate_article` - 生成文章

**为什么需要 intent？**
- **路由依据**：根据意图选择合适的 Agent
- **分类统计**：按意图统计任务量
- **权限控制**：不同意图不同权限

#### source（来源）

```json
"TaskSource": {
  "type": { "enum": ["openclaw", "api", "cron", "webhook", "ui", "system"] }
}
```

| 来源 | 说明 |
|---|---|
| `openclaw` | OpenClaw 平台 |
| `api` | API 调用 |
| `cron` | 定时任务 |
| `webhook` | Webhook 触发 |
| `ui` | 用户界面 |
| `system` | 系统内部 |

#### payload（负载）

```json
"payload": {
  "description": "经过 Schema 校验的输入"
}
```

**可以是**：
- 内联 JSON 对象
- ArtifactRef（大文件引用）

**为什么支持两种形式？**
- 小数据内联，减少引用开销
- 大数据引用，避免嵌入核心对象

#### idempotency_key（幂等键）

```json
"idempotency_key": {
  "type": "string",
  "minLength": 8,
  "maxLength": 512
}
```

**作用域**：`tenant + source + idempotency_key`

**为什么需要幂等键？**
- **防止重复创建**：相同请求不会创建两个 Task
- **安全重试**：网络失败可以安全重试
- **去重**：防止用户重复提交

**示例**：
```json
"idempotency_key": "openclaw:feishu:message-12345"
```

#### budget（预算）

```json
"budget": {
  "$ref": "#/$defs/Budget"
}
```

**预算字段**：
```json
{
  "max_wall_time_seconds": 7200,  // 最大执行时间
  "max_model_tokens": 800000,     // 最大 Token
  "max_cost_usd": "30",           // 最大费用
  "max_tool_calls": 100,          // 最大工具调用
  "max_iterations": 20            // 最大迭代
}
```

**为什么需要预算？**
- **成本控制**：防止无限消耗
- **资源保护**：保护系统资源
- **用户预期**：让用户知道消耗上限

#### retention_policy（保留策略）

```json
"RetentionPolicy": {
  "retain_days": 90,
  "delete_after": "2026-12-01T00:00:00Z",
  "legal_hold": false
}
```

| 字段 | 作用 |
|---|---|
| `retain_days` | 保留天数 |
| `delete_after` | 删除时间 |
| `legal_hold` | 法律保留（不能删除） |

### 1.3 Task 生命周期

```
created → validated → queued → running → succeeded/failed/cancelled/expired
```

| 状态 | 说明 | 下一步 |
|---|---|---|
| `created` | 已创建 | validated/cancelled/expired |
| `validated` | 已验证 | queued/failed |
| `queued` | 已排队 | running/suspended |
| `running` | 运行中 | succeeded/failed |
| `succeeded` | 成功 | 终态 |
| `failed` | 失败 | 终态 |
| `cancelled` | 取消 | 终态 |
| `expired` | 过期 | 终态 |

**为什么需要 validated 状态？**
- Schema 校验
- 权限检查
- 预算验证

---

## 二、AgentRun（Agent 运行）

### 2.1 什么是 AgentRun？

**AgentRun** 是 AgentSpec 针对某个 Task 的一次任务级执行实例。

**类比**：
- Task ≈ 工单
- AgentRun ≈ 工单的执行记录

**一个 Task 可以有多个 AgentRun**：
- 重试
- 人工恢复
- 模型切换（超出回退链）

### 2.2 核心字段

#### attempt（尝试次数）

```json
"attempt": {
  "type": "integer",
  "minimum": 1
}
```

**唯一键**：`task + attempt`

**为什么需要 attempt？**
- **重试追踪**：记录第几次尝试
- **唯一性**：同一任务不能有两个相同 attempt 的 Run
- **恢复支持**：失败后可以创建新 attempt

#### agent_snapshot（Agent 快照）

```json
"agent_snapshot": {
  "$ref": "#/$defs/ResourceRef"
}
```

**包含**：
- AgentSpec ID
- Version
- Digest

**为什么需要快照？**
- **不可变**：AgentSpec 更新不影响已启动的 Run
- **可追溯**：知道使用了哪个版本的 Agent
- **可恢复**：恢复时使用相同版本

#### resolved_dependencies（已解析依赖）

```json
"ResolvedDependencies": {
  "prompt_package_ref": { ... },
  "context_policy_ref": { ... },
  "model_policy_ref": { ... },
  "loop_profile_ref": { ... },
  "permission_profile_ref": { ... },
  "startup_skill_refs": [...],
  "startup_tool_refs": [...],
  "price_snapshot_ref": { ... },
  "schema_version": "1.0.0",
  "runtime_version": "1.0.0"
}
```

**为什么需要冻结依赖？**
- **一致性**：运行期间依赖不变
- **可恢复**：恢复时使用相同依赖
- **可审计**：知道使用了哪些版本

#### dynamic_dependency_activations（动态依赖激活）

```json
"DynamicDependencyActivation": {
  "sequence": 1,
  "resource_ref": { ... },
  "activated_at": "2026-09-01T12:00:00Z",
  "activation_reason": "User requested code review",
  "source_skill_ref": { ... },
  "permission_decision_digest": "sha256:...",
  "event_ref": { ... }
}
```

**关键约束**：
- `sequence` 必须连续递增（1, 2, 3...）
- 记录只能追加，不能覆盖或重排

**为什么需要动态激活？**
- **按需加载**：不是所有技能都需要预先加载
- **冻结记录**：首次使用前必须冻结
- **审计追踪**：记录激活原因和时间

#### model_selection_history（模型选择历史）

```json
"ModelSelectionRecord": {
  "sequence": 1,
  "route_id": "openai-gpt4",
  "provider": "openai",
  "model": "gpt-4-turbo",
  "selected_at": "2026-09-01T12:00:00Z",
  "selection_reason": "initial",
  "trigger_error_code": null,
  "price_snapshot_ref": { ... },
  "event_ref": { ... }
}
```

**选择原因**：
| 原因 | 说明 |
|---|---|
| `initial` | 初始选择 |
| `fallback` | 回退选择 |

**关键约束**：
- 第一条必须是 `initial`
- 后续必须是 `fallback`
- 路由不能重复访问
- `current_model_selection` 必须等于最后一条

**为什么需要模型选择历史？**
- **回退追踪**：记录回退原因
- **成本核算**：不同模型不同价格
- **故障分析**：分析模型可用性

#### lease（租约）

```json
"Lease": {
  "lease_id": "lease_...",
  "worker_ref": { ... },
  "acquired_at": "2026-09-01T12:00:00Z",
  "heartbeat_at": "2026-09-01T12:01:00Z",
  "expires_at": "2026-09-01T12:05:00Z",
  "fencing_token": 42
}
```

**租约机制**：
1. Worker 获取租约
2. 定期发送心跳续租
3. 租约过期后停止执行
4. Fencing Token 防止过期 Worker 提交

**为什么需要租约？**
- **并发控制**：同一 Run 只能在一个 Worker 执行
- **故障检测**：心跳超时表示 Worker 故障
- **安全提交**：Fencing Token 防止过期提交

### 2.3 AgentRun 生命周期

```
created → resolving → ready → running → succeeded/failed/cancelled/timed_out
```

| 状态 | 说明 |
|---|---|
| `created` | 已创建 |
| `resolving` | 解析依赖中 |
| `ready` | 就绪 |
| `running` | 运行中 |
| `waiting_tool` | 等待工具 |
| `waiting_approval` | 等待审批 |
| `checkpointed` | 已检查点 |
| `suspended` | 挂起 |
| `succeeded` | 成功 |
| `failed` | 失败 |
| `cancelled` | 取消 |
| `timed_out` | 超时 |

**executing 状态需要 lease**：
```json
if phase in ["running", "waiting_tool"]:
    assert lease != null
```

---

## 三、关键设计对比

### Task vs AgentRun

| 特性 | Task | AgentRun |
|---|---|---|
| 本质 | 工作单元 | 执行实例 |
| 数量 | 1 个 | 可以多个 |
| 状态 | 调度状态 | 执行状态 |
| 依赖 | 声明依赖 | 冻结依赖 |
| 预算 | 总预算 | 分配预算 |

### 启动解析 vs 动态激活

| 特性 | 启动解析 | 动态激活 |
|---|---|---|
| 时机 | Run 启动时 | 运行时按需 |
| 内容 | 基础依赖 | 技能/工具 |
| 记录 | resolved_dependencies | dynamic_dependency_activations |
| 变更 | 不可变 | 只追加 |

---

## 四、关键设计决策总结

### Task

1. **幂等键**：防止重复创建
2. **预算控制**：成本保护
3. **保留策略**：数据生命周期
4. **来源追踪**：记录任务来源

### AgentRun

1. **依赖冻结**：运行期间不变
2. **动态激活**：按需加载，首次冻结
3. **模型选择历史**：回退追踪
4. **租约机制**：并发控制
5. **Fencing Token**：防止过期提交

---

## 五、下一步

继续创建剩余的运行对象 Schema：
- checkpoint.schema.json
- tool-call.schema.json
- approval.schema.json
- artifact.schema.json
- event.schema.json
