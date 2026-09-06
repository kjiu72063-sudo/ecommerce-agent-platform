# JSON Schema 定义对象详解 - agent-spec.schema.json

> 文件位置：`schemas/definitions/agent-spec.schema.json`
> 作用：定义 AgentSpec 资源对象的结构

---

## 一、Schema 结构

```
agent-spec.schema.json
├── $defs/
│   ├── AgentSpecResource      # 顶层资源对象
│   ├── DefinitionMetadata     # 元数据
│   ├── AgentSpecSpec          # 核心规格
│   ├── DefinitionStatus       # 状态
│   ├── Binding                # 绑定配置
│   ├── MemoryPolicy           # 记忆策略
│   ├── ApprovalDefaults       # 审批默认配置
│   └── ConcurrencyPolicy      # 并发策略
└── $ref: #/$defs/AgentSpecResource  # 引用顶层对象
```

---

## 二、顶层资源对象

```json
"AgentSpecResource": {
  "type": "object",
  "properties": {
    "api_version": { "const": "agent-platform/v1alpha1" },
    "kind": { "const": "AgentSpec" },
    "metadata": { "$ref": "#/$defs/DefinitionMetadata" },
    "spec": { "$ref": "#/$defs/AgentSpecSpec" },
    "status": { "$ref": "#/$defs/DefinitionStatus" }
  },
  "required": ["api_version", "kind", "metadata", "spec", "status"],
  "additionalProperties": false
}
```

### 设计要点

#### 1. `const` 约束

```json
"api_version": { "const": "agent-platform/v1alpha1" },
"kind": { "const": "AgentSpec" }
```

**作用**：强制字段值必须是固定值

**为什么这样设计？**
- `api_version`：确保使用正确的 API 版本
- `kind`：确保资源类型正确
- 防止错误地将其他资源当作 AgentSpec

#### 2. 统一资源信封

所有资源对象都遵循相同结构：
```json
{
  "api_version": "...",
  "kind": "...",
  "metadata": { ... },
  "spec": { ... },
  "status": { ... }
}
```

**好处**：
- 统一的处理方式
- 便于通用工具开发
- 类似 Kubernetes 的资源设计

---

## 三、元数据（DefinitionMetadata）

### 3.1 ID 字段

```json
"id": {
  "type": "string",
  "pattern": "^agt_[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
}
```

**约束解析**：
- `^agt_`：必须以 `agt_` 开头（AgentSpec 专用前缀）
- `[0-9a-f]{8}`：8 位十六进制
- `-[0-9a-f]{4}`：4 位十六进制
- `-7`：版本号必须是 7（UUIDv7 标识）
- `[0-9a-f]{3}`：3 位十六进制
- `-[89ab]`：变体标识（必须是 8, 9, a, b 之一）
- `[0-9a-f]{3}-[0-9a-f]{12}`：其余部分

**为什么使用 UUIDv7？**
- **时间有序**：UUIDv7 包含时间戳，按时间排序
- **全局唯一**：几乎不可能冲突
- **分布式安全**：无需中央协调即可生成

### 3.2 Key 字段

```json
"key": {
  "type": "string",
  "pattern": "^[a-z0-9][a-z0-9-]{1,126}[a-z0-9]$",
  "minLength": 3,
  "maxLength": 128
}
```

**有效示例**：
- `programming-agent`
- `presale-consultant`
- `live-clipper`

**无效示例**：
- `Programming-Agent` ❌（大写）
- `-agent` ❌（连字符开头）
- `a` ❌（太短）

**为什么限制 Key 格式？**
- **URL 安全**：可以直接用在 API 路径中
- **跨平台**：Windows/Linux 文件系统都支持
- **可读性**：比 UUID 更容易记忆

### 3.3 Version 字段

```json
"version": {
  "type": "string",
  "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)..."
}
```

**语义版本规则**：
- **主版本**：不兼容的 API 变更
- **次版本**：向后兼容的新功能
- **修订号**：向后兼容的 bug 修复

**示例**：
- `1.0.0`：初始版本
- `1.1.0`：新增功能
- `1.1.1`：bug 修复
- `2.0.0`：不兼容变更

### 3.4 content_digest 字段

```json
"content_digest": {
  "type": "string",
  "pattern": "^sha256:[0-9a-f]{64}$"
}
```

**作用**：验证 spec 内容的完整性

**计算方式**：
```python
import hashlib, json

spec_json = json.dumps(spec, sort_keys=True, separators=(',', ':'))
digest = "sha256:" + hashlib.sha256(spec_json.encode()).hexdigest()
```

**为什么需要摘要？**
- **防篡改**：检测内容是否被修改
- **缓存键**：相同内容 = 相同摘要 = 可以复用
- **变更追踪**：摘要变化 = 内容变化

---

## 四、核心规格（AgentSpecSpec）

### 4.1 purpose 字段

```json
"purpose": {
  "type": "string",
  "minLength": 1,
  "maxLength": 4096
}
```

**作用**：描述 Agent 解决什么问题

**示例**：
```
"purpose": "在受控代码仓库中完成编程任务"
"purpose": "为电商平台用户提供商品售前咨询服务"
```

**为什么必须声明 purpose？**
- 明确 Agent 的职责边界
- 帮助选择合适的 Agent
- 文档和审计需要

### 4.2 goals 和 non_goals 字段

```json
"goals": {
  "type": "array",
  "items": { "type": "string", "minLength": 1 },
  "minItems": 1
},
"non_goals": {
  "type": "array",
  "items": { "type": "string", "minLength": 1 },
  "minItems": 1
}
```

**为什么必须同时声明 goals 和 non_goals？**

```yaml
# goals：Agent 应该做什么
goals:
  - 分析代码库并完成结构化开发任务
  - 运行测试并提供可验证结果

# non_goals：Agent 不应该做什么
non_goals:
  - 未经审批部署生产环境
  - 访问非任务授权仓库
```

**好处**：
- **边界清晰**：防止 Agent 越界
- **安全控制**：明确禁止的操作
- **用户预期**：让用户知道 Agent 能做什么

### 4.3 引用字段

```json
"prompt_package_ref": { "$ref": "#/$defs/ResourceRef" },
"context_policy_ref": { "$ref": "#/$defs/ResourceRef" },
"model_policy_ref": { "$ref": "#/$defs/ResourceRef" },
"loop_profile_ref": { "$ref": "#/$defs/ResourceRef" },
"permission_profile_ref": { "$ref": "#/$defs/ResourceRef" }
```

**5 个必需引用**：
| 引用 | 作用 |
|---|---|
| `prompt_package_ref` | Agent 的固定指令 |
| `context_policy_ref` | Context 组装策略 |
| `model_policy_ref` | 模型选择策略 |
| `loop_profile_ref` | 迭代策略 |
| `permission_profile_ref` | 权限配置 |

**为什么使用 ResourceRef 而不是 ObjectRef？**
- ResourceRef 包含 `version` 和 `digest`
- 精确版本，防止版本漂移
- 摘要校验，防止内容篡改

### 4.4 MemoryPolicy 字段

```json
"MemoryPolicy": {
  "type": "object",
  "properties": {
    "readable_scopes": { "type": "array", "items": { "$ref": "#/$defs/ScopeType" } },
    "writable_scopes": { "type": "array", "items": { "$ref": "#/$defs/ScopeType" } },
    "write_requires_approval": { "type": "boolean" },
    "max_retention_days": { "type": "integer", "minimum": 1 },
    "allow_cross_user": { "const": false },
    "allow_cross_tenant": { "const": false }
  }
}
```

**安全设计**：
```json
"allow_cross_user": { "const": false },    // 硬编码禁止
"allow_cross_tenant": { "const": false }   // 硬编码禁止
```

**为什么硬编码为 false？**
- **数据隔离**：防止用户 A 读取用户 B 的记忆
- **隐私保护**：跨租户数据泄露是严重安全问题
- **合规要求**：多租户系统必须隔离

### 4.5 ApprovalDefaults 字段

```json
"ApprovalDefaults": {
  "type": "object",
  "properties": {
    "external_send": { "type": "boolean" },
    "destructive": { "const": true },
    "privileged": { "const": true },
    "approval_ttl_seconds": { "type": "integer", "exclusiveMinimum": 0 }
  }
}
```

**为什么 destructive 和 privileged 必须审批？**
- `destructive`：删除、覆盖等不可逆操作
- `privileged`：Shell、部署、权限变更等高风险操作
- **必须人工确认**，防止误操作

---

## 五、状态（DefinitionStatus）

```json
"DefinitionStatus": {
  "type": "object",
  "properties": {
    "phase": {
      "type": "string",
      "enum": ["proposed", "draft", "testing", "awaiting_approval", "approved", "active", "deprecated", "blocked", "archived"]
    },
    "observed_revision": { "type": "integer", "minimum": 1 },
    "activated_at": { "type": "string", "format": "date-time" }
  }
}
```

**生命周期流程**：
```
proposed → draft → testing → awaiting_approval → approved → active
                                                         ↓
                                                   deprecated → archived
                                                         ↓
                                                      blocked → active
```

**为什么需要 observed_revision？**
- 乐观并发控制
- 防止覆盖他人的修改
- 类似数据库的版本号

---

## 六、引用其他 Schema

### 6.1 跨文件引用

```json
"Scope": {
  "$ref": "common-types.schema.json#/$defs/Scope"
}
```

**语法解析**：
- `common-types.schema.json`：引用的文件
- `#/$defs/Scope`：文件内的路径

**好处**：
- 定义一次，多处使用
- 修改一处，所有引用生效
- 保持一致性

### 6.2 同文件引用

```json
"metadata": { "$ref": "#/$defs/DefinitionMetadata" }
```

**`#` 表示当前文件**

---

## 七、additionalProperties: false

```json
"additionalProperties": false
```

**作用**：禁止未声明的字段

**为什么这样设计？**
- **防止拼写错误**：如 `tilte` 而不是 `title`
- **严格校验**：确保数据结构完全一致
- **向前兼容**：新版本可以安全添加字段

---

## 八、总结

### 关键设计决策

1. **const 约束**：固定 api_version 和 kind
2. **类型前缀**：ID 必须使用 `agt_` 前缀
3. **语义版本**：支持版本管理和兼容性
4. **内容摘要**：验证数据完整性
5. **强类型引用**：ResourceRef 精确版本
6. **安全硬编码**：跨用户/租户记忆访问禁止
7. **严格模式**：禁止额外字段

### 下一步

接下来我们将创建其他定义对象的 Schema：
- skill-manifest.schema.json
- tool-manifest.schema.json
- prompt-package.schema.json
- model-policy.schema.json
- context-policy.schema.json
- loop-profile.schema.json
- permission-profile.schema.json
