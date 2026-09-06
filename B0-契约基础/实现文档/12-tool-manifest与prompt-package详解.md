# JSON Schema 定义对象详解 - tool-manifest 与 prompt-package

> 创建日期：2026-09-01

---

## 一、ToolManifest 详解

### 1.1 什么是 Tool？

**Tool（工具）** 是具有结构化输入输出的原子可执行能力。

**类比**：
- AgentSpec ≈ 岗位
- Skill ≈ 技能
- Tool ≈ 具体的工具/设备

**示例**：
- RAG 检索工具
- ASR 转写工具
- 视频剪辑工具
- 文件读写工具

### 1.2 核心字段

#### provider（提供者）

```json
"provider": {
  "type": "string",
  "pattern": "^[a-z][a-z0-9_-]{1,63}$"
}
```

**示例**：
- `github` - GitHub API
- `slack` - Slack API
- `internal` - 内部服务
- `openai` - OpenAI API

#### capability（能力名称）

```json
"capability": {
  "type": "string",
  "pattern": "^[a-z][a-z0-9_.:-]{2,127}$"
}
```

**命名规范**：
- 使用点号分隔层级
- 如 `repository.read`, `file.write`, `video.cut`

**示例**：
- `knowledge.search` - 知识检索
- `speech.to_text` - 语音转文字
- `image.generate` - 图片生成

#### transport（传输协议）

```json
"transport": {
  "type": "string",
  "enum": ["local", "http", "grpc", "mcp", "openclaw"]
}
```

| 协议 | 说明 | 适用场景 |
|---|---|---|
| `local` | 本地执行 | 沙箱中的脚本 |
| `http` | HTTP REST API | 大多数 Web 服务 |
| `grpc` | gRPC 协议 | 高性能内部服务 |
| `mcp` | MCP 协议 | 模型上下文协议 |
| `openclaw` | OpenClaw 协议 | OpenClaw 平台 |

#### side_effect（副作用分类）

```json
"side_effect": {
  "type": "string",
  "enum": ["read_only", "local_write", "external_write", "external_send", "destructive", "privileged"]
}
```

| 级别 | 说明 | 默认审批 | 示例 |
|---|---|---|---|
| `read_only` | 只读 | 无 | 查询信息 |
| `local_write` | 本地写入 | 按策略 | 写入本地文件 |
| `external_write` | 外部写入 | 条件审批 | 写入数据库 |
| `external_send` | 外部发送 | 默认审批 | 发送消息 |
| `destructive` | 破坏性 | 强制审批 | 删除数据 |
| `privileged` | 特权 | 强制审批 | Shell、部署 |

**关键设计**：
```json
// 有副作用必须支持幂等
if side_effect != "read_only":
    assert idempotency.supported == true

// 破坏性和特权操作必须审批
if side_effect in ["destructive", "privileged"]:
    assert approval_requirement.mode == "always"
```

#### idempotency（幂等策略）

```json
"idempotency": {
  "type": "object",
  "properties": {
    "supported": { "type": "boolean" },
    "key_scope": { "enum": ["none", "tool_target", "tenant_tool_target"] },
    "duplicate_semantics": { "enum": ["reject", "return_original", "reconcile", "not_applicable"] }
  }
}
```

**幂等键作用域**：

| 作用域 | 说明 | 示例 |
|---|---|---|
| `none` | 不支持幂等 | 只读操作 |
| `tool_target` | 工具+目标 | 同一文件只写一次 |
| `tenant_tool_target` | 租户+工具+目标 | 租户级别幂等 |

**重复调用语义**：

| 语义 | 说明 |
|---|---|
| `reject` | 拒绝重复调用 |
| `return_original` | 返回原始结果 |
| `reconcile` | 调和重复 |
| `not_applicable` | 不适用 |

**为什么需要幂等？**
- **防止重复副作用**：网络重试不会重复执行
- **安全恢复**：可以从失败中安全恢复
- **一致性保证**：多次调用结果一致

#### execution_location（执行位置）

```json
"execution_location": {
  "type": "string",
  "enum": ["cloud", "local", "sandbox", "device", "gpu"]
}
```

| 位置 | 说明 | 适用场景 |
|---|---|---|
| `cloud` | 云端执行 | 大多数 API |
| `local` | 本地执行 | 可信代码 |
| `sandbox` | 沙箱执行 | 不可信代码 |
| `device` | 设备执行 | IoT 设备 |
| `gpu` | GPU 执行 | AI 推理 |

#### approval_requirement（审批要求）

```json
"approval_requirement": {
  "type": "object",
  "properties": {
    "mode": { "enum": ["none", "conditional", "always"] },
    "conditions": { "type": "array" }
  }
}
```

| 模式 | 说明 | 示例 |
|---|---|---|
| `none` | 无需审批 | 只读操作 |
| `conditional` | 条件审批 | 特定路径写入 |
| `always` | 必须审批 | 删除、部署 |

#### health_contract（健康检查契约）

```json
"health_contract": {
  "type": "object",
  "properties": {
    "healthcheck_key": { "type": "string" },
    "interval_seconds": { "type": "integer" },
    "unhealthy_after_failures": { "type": "integer" }
  }
}
```

**作用**：
- 定期检查工具是否可用
- 连续失败 N 次后标记为不健康
- 防止调用不可用的工具

---

## 二、PromptPackage 详解

### 2.1 什么是 Prompt？

**Prompt（提示）** 是给模型的指令，告诉模型应该如何行动。

**类比**：
- Prompt ≈ 岗位说明书
- 定义了身份、职责、行为规范

### 2.2 分层设计

```json
"PromptLayer": {
  "type": "string",
  "enum": ["safety", "identity", "domain", "behavior", "output_contract", "error_policy"]
}
```

| 层级 | 说明 | 优先级 | 示例 |
|---|---|---|---|
| `safety` | 安全规则 | 最高 | "不得泄露机密" |
| `identity` | 身份定义 | 高 | "你是客服助手" |
| `domain` | 领域规则 | 中 | "商品知识如下" |
| `behavior` | 行为规范 | 中 | "回答要友好" |
| `output_contract` | 输出格式 | 低 | "返回 JSON" |
| `error_policy` | 错误处理 | 低 | "失败时询问用户" |

**为什么分层？**
- **优先级控制**：安全规则不能被覆盖
- **模块化**：不同层级可以独立更新
- **可组合**：可以复用通用层级

### 2.3 核心字段

#### fragments（片段）

```json
"fragments": {
  "type": "array",
  "items": {
    "type": "object",
    "properties": {
      "name": { "type": "string" },
      "layer": { "$ref": "#/$defs/PromptLayer" },
      "order": { "type": "integer", "minimum": 0 },
      "content": { "type": "string", "maxLength": 20000 }
    }
  },
  "minItems": 1
}
```

**关键约束**：
- `order` 必须唯一（不能有两个片段顺序相同）
- 必须有至少一个 `safety` 层级的片段

**示例**：
```json
"fragments": [
  {
    "name": "safety-rules",
    "layer": "safety",
    "order": 0,
    "content": "你必须遵守以下安全规则：\n1. 不得泄露机密\n2. 不得执行危险操作"
  },
  {
    "name": "identity",
    "layer": "identity",
    "order": 1,
    "content": "你是电商平台的客服助手"
  }
]
```

**为什么需要 safety 片段？**
- **不可绕过**：安全规则必须存在
- **最高优先级**：不能被其他片段覆盖
- **合规要求**：安全是底线

#### variables_schema_ref（变量 Schema）

```json
"variables_schema_ref": {
  "$ref": "#/$defs/SchemaRef"
}
```

**作用**：定义允许注入的变量

**示例**：
```json
{
  "id": "sch_prompt_variables",
  "version": "1.0.0",
  "digest": "sha256:..."
}
```

**变量注入示例**：
```
"你好，{user_name}！欢迎来到{store_name}。"
```

**为什么需要变量 Schema？**
- **白名单化**：只允许定义的变量
- **类型安全**：变量有类型约束
- **防注入**：防止恶意变量

#### model_compatibility（模型兼容性）

```json
"model_compatibility": {
  "type": "object",
  "properties": {
    "required_capabilities": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["tool_calling", "vision", "long_context", "structured_output", "reasoning"]
      }
    },
    "provider_allowlist": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    }
  }
}
```

**模型能力**：

| 能力 | 说明 |
|---|---|
| `tool_calling` | 工具调用能力 |
| `vision` | 视觉理解能力 |
| `long_context` | 长上下文支持 |
| `structured_output` | 结构化输出 |
| `reasoning` | 推理能力 |

**为什么需要兼容性声明？**
- **前置检查**：运行前验证模型是否满足
- **自动选择**：根据能力选择合适的模型
- **防止错误**：避免不兼容的模型组合

#### max_static_tokens（静态 Token 上限）

```json
"max_static_tokens": {
  "type": "integer",
  "exclusiveMinimum": 0
}
```

**作用**：限制固定 Prompt 的 Token 数量

**为什么需要限制？**
- **成本控制**：Token 越多，成本越高
- **上下文空间**：为动态内容留出空间
- **性能**：太长的 Prompt 会增加延迟

#### change_summary（变更说明）

```json
"change_summary": {
  "type": "string",
  "minLength": 1,
  "maxLength": 4096
}
```

**作用**：记录版本变更内容

**示例**：
```json
"change_summary": "v1.1.0: 新增安全规则，优化输出格式"
```

**为什么需要变更说明？**
- **版本追踪**：了解每次变更的内容
- **审计**：满足合规要求
- **协作**：团队成员了解变更

---

## 三、关键设计对比

### 3.1 Tool vs Skill

| 特性 | Tool | Skill |
|---|---|---|
| 定义 | 原子能力 | 程序性知识 |
| 结构 | 单一调用 | 多步骤流程 |
| 输入输出 | 严格 Schema | 灵活 |
| 副作用 | 明确声明 | 通过 Tool 间接 |
| 示例 | RAG 检索 | 代码审查流程 |

### 3.2 Prompt vs Skill

| 特性 | Prompt | Skill |
|---|---|---|
| 内容 | 固定指令 | 程序性知识 |
| 变更频率 | 低 | 中 |
| 版本管理 | 严格 | 严格 |
| 评估 | 回归测试 | 触发+输出评估 |

---

## 四、关键设计决策总结

### ToolManifest

1. **副作用分类**：6 级分类，明确审批要求
2. **幂等控制**：有副作用必须支持幂等
3. **沙箱隔离**：不可信代码必须在沙箱执行
4. **健康检查**：定期检查工具可用性

### PromptPackage

1. **分层设计**：安全规则不可绕过
2. **变量白名单**：防止注入攻击
3. **模型兼容性**：前置检查能力
4. **变更追踪**：版本化管理

---

## 五、下一步

继续创建剩余的定义对象 Schema：
- model-policy.schema.json
- context-policy.schema.json
- loop-profile.schema.json
- permission-profile.schema.json
