# JSON Schema 运行对象详解 - Checkpoint, ToolCall, Approval, Artifact, Event

> 创建日期：2026-09-01

---

## 一、Checkpoint（检查点）

### 1.1 作用

保存 AgentRun 或 LangGraph 在可恢复边界上的一致状态。

**关键设计**：
- Checkpoint 不是日志快照
- 是能够安全恢复执行的最小完整状态

### 1.2 核心字段

#### sequence（序号）

```json
"sequence": { "type": "integer", "minimum": 1 }
```

**约束**：同一 Run 内严格单调递增

**为什么需要 sequence？**
- **顺序保证**：确保 Checkpoint 顺序
- **恢复依据**：从哪个 Checkpoint 恢复
- **防篡改**：序号不能跳过

#### side_effect_ledger（副作用账本）

```json
"side_effect_ledger": {
  "type": "array",
  "items": { "$ref": "#/$defs/ObjectRef" }
}
```

**作用**：记录已提交的副作用 ToolCall ID

**为什么需要副作用账本？**
- **防重复执行**：恢复时跳过已执行的副作用
- **一致性保证**：确保副作用不重复
- **审计追踪**：记录所有副作用

#### resume_token_ref（恢复令牌）

```json
"resume_token_ref": { "$ref": "#/$defs/SecretRef" }
```

**作用**：防篡改恢复令牌

**为什么需要恢复令牌？**
- **安全恢复**：防止未授权恢复
- **防篡改**：确保 Checkpoint 未被修改

#### created_reason（创建原因）

```json
"created_reason": {
  "type": "string",
  "enum": ["periodic", "node_end", "approval", "interrupt", "error", "manual"]
}
```

| 原因 | 说明 |
|---|---|
| `periodic` | 定期创建 |
| `node_end` | 节点结束 |
| `approval` | 审批前 |
| `interrupt` | 中断时 |
| `error` | 错误时 |
| `manual` | 手动创建 |

---

## 二、ToolCall（工具调用）

### 2.1 作用

记录一次结构化 Tool 调用的完整生命周期。

### 2.2 核心字段

#### ToolSnapshot（工具快照）

```json
"ToolSnapshot": {
  "tool_ref": { ... },
  "side_effect": "read_only",
  "risk_level": "low"
}
```

**为什么需要快照？**
- **版本锁定**：使用精确版本
- **副作用声明**：明确副作用类型
- **风险评估**：记录风险级别

#### idempotency_key（幂等键）

```json
"idempotency_key": {
  "type": "string",
  "minLength": 8,
  "maxLength": 512
}
```

**约束**：有副作用的 ToolCall 必须有幂等键

**为什么需要幂等键？**
- **防重复执行**：网络重试不会重复执行
- **安全恢复**：从失败中安全恢复

#### permission_decision（权限决策）

```json
"PermissionDecision": {
  "decision": "allow",
  "policy_refs": [...],
  "reason_codes": ["RESOURCE_IN_PROJECT_SCOPE"],
  "constraints": { "allowed_paths": ["src/**"] },
  "request_digest": "sha256:...",
  "decision_digest": "sha256:..."
}
```

**为什么需要记录权限决策？**
- **可审计**：追踪权限决策过程
- **可复现**：保存策略版本和决策理由
- **可追溯**：记录请求和决策摘要

### 2.3 ToolCall 生命周期

```
proposed → validating → scheduled → executing → succeeded/failed
    ↓           ↓
cancelled   denied/waiting_approval
```

**unknown 状态**：
- 调用可能已产生副作用
- 但平台未获得确定回执
- 不能自动重试，必须先对账

---

## 三、Approval（审批）

### 3.1 作用

记录 Human-in-the-loop 或策略审批过程。

### 3.2 核心字段

#### subject_ref（被审批对象）

```json
"subject_ref": { "$ref": "#/$defs/ObjectRef" }
```

**可以是**：
- ToolCall
- Skill 发布
- Agent 变更
- 等等

#### required_approvers（审批规则）

```json
"ApproverRule": {
  "role": "admin",
  "count": 1,
  "separation_of_duties": false
}
```

**职责分离**：
```json
"separation_of_duties": true  // 请求者不能审批自己
```

#### one_time（一次性）

```json
"one_time": true,
"usage_count": 1
```

**约束**：一次性审批使用后必须进入 consumed 状态

**为什么需要一次性审批？**
- **安全控制**：防止重复使用
- **精确授权**：每次操作都需要新审批

### 3.3 Approval 生命周期

```
requested → pending → approved → consumed
    ↓           ↓
expired     rejected/revoked
```

**关键约束**：
- 审批必须绑定输入摘要和资源范围
- 修改参数后原审批失效
- 过期、撤销或已消费审批不得再次使用

---

## 四、Artifact（产物）

### 4.1 作用

描述存储在 Object Storage、Git、文件系统或外部文档系统中的不可变产物。

### 4.2 核心字段

#### artifact_type（产物类型）

```json
"artifact_type": { "type": "string", "pattern": "^[a-z][a-z0-9_-]{1,63}$" }
```

**示例**：
- `document` - 文档
- `code` - 代码
- `image` - 图片
- `video` - 视频
- `context_snapshot` - Context 快照

#### locator（位置）

```json
"ArtifactLocator": {
  "provider": "s3",
  "bucket_or_repository": "my-bucket",
  "object_key": "artifacts/2026/09/01/file.json",
  "version_id": "v1"
}
```

**安全约束**：不能包含签名 URL 或凭证

**为什么不能包含凭证？**
- **安全**：防止凭证泄露
- **可移植**：不同环境使用不同凭证
- **可审计**：凭证单独管理

#### classification（数据分类）

```json
"classification": {
  "type": "string",
  "enum": ["public", "internal", "confidential", "restricted"]
}
```

**加密要求**：
```python
if classification in ["confidential", "restricted"]:
    assert encryption.encrypted == True
```

#### supersedes（替代）

```json
"supersedes": { "$ref": "#/$defs/ArtifactRef" }
```

**作用**：新内容必须创建新 Artifact，通过 supersedes 关联

**为什么不可变？**
- **版本控制**：保留历史版本
- **可追溯**：追踪内容变更
- **安全**：防止内容被篡改

### 4.3 Artifact 生命周期

```
pending_upload → available → quarantined/blocked → archived → deleted
```

**available 状态要求**：
```python
if phase == "available":
    assert content_digest is not None
    assert size_bytes is not None
```

---

## 五、Event（事件）

### 5.1 作用

系统已经发生事实的不可变记录，用于审计、状态投影、异步集成和故障恢复。

**兼容 CloudEvents 规范**

### 5.2 核心字段

#### specversion（规范版本）

```json
"specversion": { "const": "1.0" }
```

**CloudEvents 1.0 兼容**

#### id 与 metadata.id 一致性

```json
"id": { "type": "string", "pattern": "^evt_..." }
```

**约束**：CloudEvents id 必须与 metadata.id 一致

```python
if spec.id != metadata.id:
    raise ValueError("CloudEvents id must equal metadata.id")
```

**为什么需要一致性？**
- **唯一标识**：全局唯一
- **引用一致**：不同地方引用同一事件

#### type（事件类型）

```json
"type": { "type": "string", "pattern": "^[a-z][a-z0-9_.:-]{2,255}$" }
```

**示例**：
- `task.created`
- `agent_run.started`
- `tool_call.succeeded`
- `approval.requested`

#### sequence（序号）

```json
"sequence": { "type": "integer", "minimum": 1 }
```

**约束**：同一聚合对象的 sequence 必须严格递增

**为什么需要 sequence？**
- **顺序保证**：事件顺序
- **投影重建**：从事件重建状态
- **防乱序**：防止事件乱序处理

#### trace（追踪上下文）

```json
"TraceContext": {
  "trace_id": "32位十六进制",
  "span_id": "16位十六进制",
  "parent_span_id": "16位十六进制或null",
  "correlation_id": "corr_..."
}
```

**作用**：
- 分布式追踪
- 关联相关事件
- 故障排查

### 5.3 Event 不可变性

**关键约束**：
- Event 一经写入不可修改
- event_id 全局唯一
- 消费者必须按 event_id 幂等消费

---

## 六、关键设计决策总结

### Checkpoint

1. **副作用账本**：防重复执行
2. **恢复令牌**：安全恢复
3. **不可变**：提交后不能修改

### ToolCall

1. **幂等键**：防重复副作用
2. **权限决策记录**：可审计
3. **unknown 状态**：不确定时不能重试

### Approval

1. **一次性审批**：防重复使用
2. **职责分离**：请求者不能审批自己
3. **输入摘要绑定**：修改后失效

### Artifact

1. **不可变**：内容不可修改
2. **数据分类**：敏感数据必须加密
3. **位置安全**：不能包含凭证

### Event

1. **不可变**：只追加不修改
2. **CloudEvents 兼容**：标准化格式
3. **追踪上下文**：分布式追踪

---

## 七、所有运行对象 Schema 完成！

```
schemas/runtime/
├── task.schema.json
├── agent-run.schema.json
├── checkpoint.schema.json
├── tool-call.schema.json
├── approval.schema.json
├── artifact.schema.json
└── event.schema.json
```

**总计**：17 个 Schema 文件全部完成！
