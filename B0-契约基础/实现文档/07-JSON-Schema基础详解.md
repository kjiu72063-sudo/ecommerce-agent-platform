# JSON Schema 基础详解 - common-types.schema.json

> 文件位置：`schemas/common/common-types.schema.json`
> 作用：定义所有资源对象共享的基础类型

---

## 一、Schema 文件头部

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "common-types.schema.json",
  "title": "Common Types",
  "x-contract-version": "0.2.0"
}
```

### 字段解释

| 字段 | 作用 | 为什么这样设计 |
|---|---|---|
| `$schema` | 声明使用的 JSON Schema 版本 | 使用 2020-12 最新标准，支持更多特性 |
| `$id` | Schema 的唯一标识符 | 便于引用和版本管理 |
| `title` | 人类可读标题 | 文档和工具显示 |
| `x-contract-version` | 契约版本号 | 自定义扩展字段，用于版本追踪 |

---

## 二、基础类型定义

### 2.1 语义版本（SemVer）

```json
"SemVer": {
  "type": "string",
  "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?$"
}
```

**约束说明**：
- `type: "string"`：必须是字符串
- `pattern`：正则表达式验证格式

**正则解析**：
```
^                    # 开始
(0|[1-9]\\d*)        # 主版本号：0 或 1-999
\\.                  # 点号
(0|[1-9]\\d*)        # 次版本号
\\.                  # 点号
(0|[1-9]\\d*)        # 修订号
(?:-...)?            # 可选的预发布标签，如 -beta.1
(?:+...)?            # 可选的构建元数据，如 +build.123
$                    # 结束
```

**有效示例**：
- `1.0.0` ✅
- `2.1.3-beta.1` ✅
- `0.0.1` ✅

**无效示例**：
- `01.0.0` ❌（前导零）
- `1.0` ❌（缺少修订号）
- `1.0.0.0` ❌（多余段）

**为什么使用语义版本？**
- **主版本**：不兼容的 API 变更
- **次版本**：向后兼容的新功能
- **修订号**：向后兼容的 bug 修复

---

### 2.2 内容摘要（Digest）

```json
"Digest": {
  "type": "string",
  "pattern": "^sha256:[0-9a-f]{64}$"
}
```

**约束说明**：
- 必须以 `sha256:` 开头
- 后跟 64 位十六进制字符

**有效示例**：
- `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`

**为什么使用 SHA-256？**
- **唯一性**：不同内容几乎不可能产生相同摘要
- **不可逆**：无法从摘要反推内容
- **确定性**：相同内容总是产生相同摘要
- **用途**：验证数据完整性、检测变更

---

### 2.3 资源 ID（ResourceId）

```json
"ResourceId": {
  "type": "string",
  "pattern": "^(?:ten|usr|prj|agt|skl|tol|prm|mpo|cpo|lop|pep|tsk|run|ckp|tcl|apr|art|evt)_[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
}
```

**约束说明**：
- 类型前缀 + 下划线 + UUIDv7

**前缀列表**：
| 前缀 | 资源类型 |
|---|---|
| `ten_` | Tenant（租户） |
| `usr_` | User（用户） |
| `prj_` | Project（项目） |
| `agt_` | AgentSpec |
| `skl_` | SkillManifest |
| `tol_` | ToolManifest |
| `prm_` | PromptPackage |
| `mpo_` | ModelPolicy |
| `cpo_` | ContextPolicy |
| `lop_` | LoopProfile |
| `pep_` | PermissionProfile |
| `tsk_` | Task |
| `run_` | AgentRun |
| `ckp_` | Checkpoint |
| `tcl_` | ToolCall |
| `apr_` | Approval |
| `art_` | Artifact |
| `evt_` | Event |

**UUIDv7 特点**：
- 版本号必须是 `7`
- 时间戳在前，保证时间有序
- 随机部分保证唯一性

**为什么使用类型前缀？**
- **快速识别**：一眼看出资源类型
- **防止冲突**：不同资源类型不会混淆
- **便于调试**：日志中直接看出资源类型

---

### 2.4 标识符（Key）

```json
"Key": {
  "type": "string",
  "pattern": "^[a-z0-9][a-z0-9-]{1,126}[a-z0-9]$",
  "minLength": 3,
  "maxLength": 128
}
```

**约束说明**：
- 只能包含小写字母、数字、连字符
- 不能以连字符开头或结尾
- 长度 3-128 字符

**有效示例**：
- `programming-agent`
- `code-review-skill`
- `rag-search-tool`

**无效示例**：
- `Programming-Agent` ❌（大写）
- `-agent` ❌（连字符开头）
- `a` ❌（太短）

**为什么限制 Key 格式？**
- **URL 安全**：可以直接用在 URL 中
- **跨平台兼容**：Windows/Linux 都支持
- **避免歧义**：统一小写避免大小写混淆

---

## 三、作用域与引用类型

### 3.1 作用域（Scope）

```json
"Scope": {
  "type": "object",
  "properties": {
    "type": { "$ref": "#/$defs/ScopeType" },
    "tenant_id": { "$ref": "#/$defs/ResourceId" },
    "user_id": { "$ref": "#/$defs/ResourceId" },
    "project_id": { "$ref": "#/$defs/ResourceId" },
    "session_id": { ... }
  },
  "required": ["type"],
  "additionalProperties": false
}
```

**作用域层级**：
```
system (系统级)
  └── tenant (租户级)
        └── user (用户级)
              └── project (项目级)
                    └── session (会话级)
```

**为什么需要作用域？**
- **权限隔离**：不同租户数据隔离
- **资源可见性**：控制谁能访问什么
- **多租户支持**：一套系统服务多个租户

### 3.2 资源引用（ResourceRef）

```json
"ResourceRef": {
  "type": "object",
  "properties": {
    "kind": { "$ref": "#/$defs/ResourceKind" },
    "id": { "$ref": "#/$defs/ResourceId" },
    "version": { "$ref": "#/$defs/SemVer" },
    "digest": { "$ref": "#/$defs/Digest" }
  },
  "required": ["kind", "id", "version", "digest"],
  "additionalProperties": false
}
```

**为什么 ResourceRef 包含 4 个字段？**
- `kind`：明确资源类型
- `id`：唯一标识
- `version`：精确版本，防止版本漂移
- `digest`：内容摘要，防止篡改

**与 ObjectRef 的区别**：
- `ResourceRef`：用于定义对象（有版本）
- `ObjectRef`：用于运行对象（无版本）

---

## 四、预算与使用量

### 4.1 预算（Budget）

```json
"Budget": {
  "type": "object",
  "properties": {
    "max_wall_time_seconds": { "type": "integer", "exclusiveMinimum": 0 },
    "max_model_input_tokens": { "type": "integer", "minimum": 0 },
    "max_model_output_tokens": { "type": "integer", "minimum": 0 },
    "max_model_tokens": { "type": "integer", "exclusiveMinimum": 0 },
    "max_cost_usd": { "type": "string", "pattern": "^\\d+(\\.\\d+)?$" },
    "max_tool_calls": { "type": "integer", "minimum": 0 },
    "max_iterations": { "type": "integer", "exclusiveMinimum": 0 }
  },
  "required": [...]
}
```

**约束说明**：
- `exclusiveMinimum: 0`：必须大于 0（不包含 0）
- `minimum: 0`：可以等于 0

**为什么费用用字符串？**
- JSON 的 number 类型有精度限制
- 字符串可以精确表示任意精度的小数
- 避免浮点数计算误差

---

## 五、错误模型

### 5.1 标准错误（StandardError）

```json
"StandardError": {
  "type": "object",
  "properties": {
    "code": { "pattern": "^[A-Z][A-Z0-9_]{2,127}$" },
    "category": { "enum": [...] },
    "retryable": { "type": "boolean" },
    "safe_to_retry": { "type": "boolean" }
  }
}
```

**错误码格式**：
- 全大写 + 下划线
- 如 `TOOL_TIMEOUT`, `PERMISSION_DENIED`

**retryable vs safe_to_retry**：
- `retryable`：错误可能是暂时的，可以重试
- `safe_to_retry`：重试不会产生重复副作用
- 自动重试必须同时为 `true`

---

## 六、引用其他 Schema

### `$ref` 语法

```json
"tenant_id": { "$ref": "#/$defs/ResourceId" }
```

**解释**：
- `$ref`：引用其他定义
- `#`：当前文档
- `/$defs/ResourceId`：指向 `$defs` 下的 `ResourceId` 定义

**好处**：
- **复用**：定义一次，多处使用
- **一致性**：保证所有地方使用相同类型
- **维护**：修改一处，所有引用生效

---

## 七、additionalProperties: false

```json
"additionalProperties": false
```

**作用**：禁止未声明的额外字段

**为什么这样设计？**
- **防止拼写错误**：如 `tilte` 而不是 `title`
- **严格校验**：确保数据结构完全一致
- **向前兼容**：新版本可以安全添加字段

---

## 八、总结

### 关键设计原则

1. **强类型**：每个字段都有明确的类型约束
2. **正则验证**：使用 pattern 确保格式正确
3. **引用复用**：通过 `$ref` 复用类型定义
4. **严格模式**：`additionalProperties: false` 防止未知字段
5. **可读性**：使用 `description` 说明每个字段的用途

### 下一步

接下来我们将创建 `standard-error.schema.json`，然后开始创建定义对象的 Schema。
