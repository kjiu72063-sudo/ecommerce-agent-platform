# JSON Schema 创建进度总结

> 更新日期：2026-09-01

---

## 已完成的 Schema 文件

### 公共类型（schemas/common/）

| 文件 | 状态 | 定义类型数 |
|---|---|---|
| common-types.schema.json | ✅ | 24 |
| standard-error.schema.json | ✅ | 2 |

### 定义对象（schemas/definitions/）

| 文件 | 状态 | 定义类型数 | 新知识点 |
|---|---|---|---|
| agent-spec.schema.json | ✅ | 16 | const、类型前缀、语义版本 |
| skill-manifest.schema.json | ✅ | 20 | trigger_examples、沙箱、评估 |

### 运行对象（schemas/runtime/）

| 文件 | 状态 |
|---|---|
| task.schema.json | ⏳ |
| agent-run.schema.json | ⏳ |
| checkpoint.schema.json | ⏳ |
| tool-call.schema.json | ⏳ |
| approval.schema.json | ⏳ |
| artifact.schema.json | ⏳ |
| event.schema.json | ⏳ |

---

## 已讲解的知识点

### 1. 基础约束

| 约束 | 作用 | 示例 |
|---|---|---|
| `type` | 数据类型 | `"string"`, `"integer"` |
| `pattern` | 正则验证 | `"^[a-z][a-z0-9-]{1,63}$"` |
| `enum` | 枚举值 | `["low", "medium", "high"]` |
| `const` | 固定值 | `"agent-platform/v1alpha1"` |
| `minimum` | 最小值（含） | `"minimum": 0` |
| `exclusiveMinimum` | 最小值（不含） | `"exclusiveMinimum": 0` |
| `minLength` | 最小长度 | `"minLength": 3` |
| `maxLength` | 最大长度 | `"maxLength": 128` |
| `minItems` | 数组最小元素 | `"minItems": 1` |

### 2. 对象约束

| 约束 | 作用 |
|---|---|
| `properties` | 定义字段 |
| `required` | 必填字段 |
| `additionalProperties: false` | 禁止额外字段 |

### 3. 引用机制

| 语法 | 作用 |
|---|---|
| `$ref: "#/$defs/Type"` | 同文件引用 |
| `$ref: "file.json#/$defs/Type"` | 跨文件引用 |

### 4. 设计原则

| 原则 | 说明 |
|---|---|
| 强类型 | 每个字段都有明确类型 |
| 正则验证 | 使用 pattern 确保格式 |
| 引用复用 | 通过 $ref 复用定义 |
| 严格模式 | 禁止未知字段 |
| 安全设计 | 沙箱隔离、权限最小化 |

---

## SkillManifest 关键设计

### 1. trigger_examples

```json
{
  "positive": ["应该触发的场景"],
  "negative": ["不应该触发的场景"]
}
```

**作用**：触发判断、评估测试、防止误触发

### 2. 沙箱要求

```json
"has_scripts": true → "sandbox_required": true, "sandbox_profile": "xxx"
```

**原因**：Skill 默认不可信，脚本必须在沙箱中执行

### 3. 评估摘要

```json
"security_passed": true,    // 必须通过安全评估
"regression_passed": true   // 必须通过回归测试
```

**active 状态要求**：必须通过所有评估

### 4. 来源限制

```json
// Hermes 提案只能是 proposed 或 draft
if provenance.type == "hermes_proposal":
    assert status.phase in ["proposed", "draft"]
```

**原因**：AI 生成的技能需要人工审查

---

## 下一步

继续创建剩余的定义对象 Schema：
1. tool-manifest.schema.json
2. prompt-package.schema.json
3. model-policy.schema.json
4. context-policy.schema.json
5. loop-profile.schema.json
6. permission-profile.schema.json
