# 第四步：models.py 公共类型详解

> 已完成：元数据、引用类型、预算、错误、生命周期状态

---

## 已添加的类型

### 1. 元数据类型

#### DefinitionMetadata（定义对象元数据）

```python
class DefinitionMetadata(StrictModel):
    id: ResourceId              # 如 agt_0198f6d0-...
    key: Key                    # 如 "programming-agent"
    namespace: Namespace        # 如 "ecommerce"
    version: SemVer             # 如 "1.0.0"
    revision: int               # 乐观并发修订号，从 1 开始
    scope: Scope                # 作用域
    labels: dict                # 标签（可选）
    annotations: dict           # 注解（可选）
    content_digest: Digest      # sha256:...
    created_at: AwareDatetime   # 创建时间（必须带时区）
    created_by: ActorRef        # 创建者
```

**关键设计**：
- `revision` 用于乐观并发控制（更新时检查版本）
- `content_digest` 用于验证内容完整性
- `labels` 用于查询过滤，`annotations` 用于扩展信息

#### RuntimeMetadata（运行对象元数据）

```python
class RuntimeMetadata(StrictModel):
    id: ResourceId              # 如 tsk_0198f6d0-...
    revision: int               # 乐观并发修订号
    scope: Scope                # 作用域
    created_at: AwareDatetime   # 创建时间
    created_by: ActorRef        # 创建者
    updated_at: AwareDatetime | None  # 更新时间（可选）
```

**与 DefinitionMetadata 的区别**：
- 运行对象没有 `key`、`namespace`、`version`、`content_digest`
- 运行对象有 `updated_at` 字段

### 2. 引用类型

#### ResourceRef（资源引用）

```python
class ResourceRef(StrictModel):
    kind: ResourceKind    # 如 "AgentSpec"
    id: ResourceId        # 如 "agt_0198f6d0-..."
    version: SemVer       # 如 "1.0.0"
    digest: Digest        # 如 "sha256:abc123..."
```

**验证规则**：
- `id` 前缀必须与 `kind` 匹配（如 AgentSpec 必须用 `agt_`）
- 只能引用定义对象（不能引用运行对象）

**使用场景**：
- AgentSpec 引用 PromptPackage
- AgentRun 引用 AgentSpec

#### ObjectRef（对象引用）

```python
class ObjectRef(StrictModel):
    kind: ResourceKind    # 如 "Task"
    id: ResourceId        # 如 "tsk_0198f6d0-..."
```

**与 ResourceRef 的区别**：
- 没有 `version` 和 `digest`
- 可以引用运行对象

**使用场景**：
- AgentRun 引用 Task
- Checkpoint 引用 AgentRun

#### SchemaRef（Schema 引用）

```python
class SchemaRef(StrictModel):
    id: SchemaId          # 如 "sch_programming_task"
    version: SemVer       # 如 "1.0.0"
    digest: Digest        # 如 "sha256:abc123..."
```

**使用场景**：
- AgentSpec 引用输入/输出 Schema

#### ArtifactRef（产物引用）

```python
class ArtifactRef(StrictModel):
    kind: Literal["Artifact"] = "Artifact"
    id: ResourceId        # 如 "art_0198f6d0-..."
    digest: Digest        # 如 "sha256:abc123..."
```

**使用场景**：
- 引用大文件（文档、代码、图片、视频）

#### SecretRef（密钥引用）

```python
class SecretRef(StrictModel):
    provider: str         # 如 "vault"
    key: str              # 如 "tenants/ten_default/github"
    version: int | str    # 如 4
    field: str            # 如 "token"
```

**关键设计**：
- **不存储实际密钥**，只存储引用
- 密钥只能在 Harness 或 Tool Runtime 中解析
- 密钥不得进入 Prompt、Context、Event 或日志

### 3. 预算与使用量

#### Budget（预算）

```python
class Budget(StrictModel):
    max_wall_time_seconds: int      # 最大执行时间（秒）
    max_model_input_tokens: int     # 最大输入 Token
    max_model_output_tokens: int    # 最大输出 Token
    max_model_tokens: int           # 最大总 Token
    max_cost_usd: Decimal           # 最大费用（美元）
    max_tool_calls: int             # 最大工具调用次数
    max_iterations: int             # 最大迭代次数
```

**验证规则**：
- `max_model_input_tokens` 不能超过 `max_model_tokens`
- `max_model_output_tokens` 不能超过 `max_model_tokens`
- 输入 + 输出不能超过总 Token

#### Usage（使用量）

```python
class Usage(StrictModel):
    wall_time_seconds: float        # 实际执行时间
    model_input_tokens: int         # 实际输入 Token
    model_output_tokens: int        # 实际输出 Token
    model_tokens: int               # 实际总 Token
    cost_usd: Decimal               # 实际费用
    tool_calls: int                 # 实际工具调用次数
    iterations: int                 # 实际迭代次数
    price_snapshot_ref: PriceSnapshotRef  # 价格快照
```

**验证规则**：
- `model_tokens` 必须等于 `model_input_tokens + model_output_tokens`

### 4. 错误模型

#### StandardError（标准错误）

```python
class StandardError(StrictModel):
    code: str              # 如 "TOOL_TIMEOUT"
    category: ErrorCategory  # 如 "tool"
    message: str           # 如 "Tool execution exceeded timeout"
    retryable: bool        # 是否可重试
    safe_to_retry: bool    # 重试是否安全（不会重复副作用）
    severity: ErrorSeverity  # 如 "error"
    details: dict          # 详细信息
    cause_ref: str | None  # 原因事件 ID
    occurred_at: AwareDatetime  # 发生时间
```

**关键设计**：
- `retryable` 只表示可能重试
- `safe_to_retry` 表示重试不会产生重复副作用
- 自动重试必须同时为 `true`

#### 错误分类（12种）

| 分类 | 说明 |
|---|---|
| `validation` | Schema 或契约错误 |
| `authentication` | 身份认证失败 |
| `authorization` | 权限拒绝 |
| `approval` | 审批拒绝 |
| `budget` | 预算超限 |
| `model` | 模型调用失败 |
| `tool` | 工具调用失败 |
| `dependency` | 依赖服务失败 |
| `conflict` | 版本或状态冲突 |
| `cancelled` | 取消 |
| `timeout` | 超时 |
| `internal` | 未分类错误 |

### 5. 生命周期状态

#### DefinitionPhase（定义对象状态）

```
proposed → draft → testing → awaiting_approval → approved → active
                                                           ↓
                                                     deprecated → archived
                                                           ↓
                                                        blocked → active（重新评估）
```

| 状态 | 说明 | 是否可用于生产 |
|---|---|---|
| `proposed` | 已提出 | ❌ |
| `draft` | 草稿 | ❌ |
| `testing` | 测试中 | 仅测试环境 |
| `awaiting_approval` | 等待审批 | ❌ |
| `approved` | 已批准 | 仅 Staging |
| `active` | 活跃 | ✅ |
| `deprecated` | 已弃用 | 旧 Run 可继续 |
| `blocked` | 已阻塞 | ❌ |
| `archived` | 已归档 | ❌ |

---

## 下一步

接下来我们将添加 15 个核心资源对象模型。
