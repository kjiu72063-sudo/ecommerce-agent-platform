# JSON Schema 创建进度总结

> 更新日期：2026-09-01

---

## 已完成的 Schema 文件

### 公共类型（schemas/common/）- 2/2 完成

| 文件 | 状态 | 定义类型数 |
|---|---|---|
| common-types.schema.json | ✅ | 24 |
| standard-error.schema.json | ✅ | 2 |

### 定义对象（schemas/definitions/）- 4/8 完成

| 文件 | 状态 | 定义类型数 | 核心知识点 |
|---|---|---|---|
| agent-spec.schema.json | ✅ | 16 | Agent 定义、引用、预算 |
| skill-manifest.schema.json | ✅ | 20 | 触发示例、沙箱、评估 |
| tool-manifest.schema.json | ✅ | 19 | 副作用、幂等、审批 |
| prompt-package.schema.json | ✅ | 11 | 分层、变量、兼容性 |
| model-policy.schema.json | ⏳ | - | - |
| context-policy.schema.json | ⏳ | - | - |
| loop-profile.schema.json | ⏳ | - | - |
| permission-profile.schema.json | ⏳ | - | - |

### 运行对象（schemas/runtime/）- 0/7 待创建

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

## 新学到的知识点

### ToolManifest

| 字段 | 作用 | 关键设计 |
|---|---|---|
| `provider` | 提供者 | 如 github, slack |
| `capability` | 能力名称 | 如 repository.read |
| `transport` | 传输协议 | local/http/grpc/mcp/openclaw |
| `side_effect` | 副作用 | 6 级分类，明确审批 |
| `idempotency` | 幂等策略 | 有副作用必须支持 |
| `execution_location` | 执行位置 | 沙箱隔离 |
| `approval_requirement` | 审批要求 | 破坏性必须审批 |
| `health_contract` | 健康检查 | 定期检查可用性 |

### PromptPackage

| 字段 | 作用 | 关键设计 |
|---|---|---|
| `fragments` | 片段 | 有序、分层 |
| `PromptLayer` | 层级 | safety/identity/domain/behavior/output_contract/error_policy |
| `variables_schema_ref` | 变量 Schema | 白名单化，防注入 |
| `model_compatibility` | 模型兼容性 | 前置检查能力 |
| `max_static_tokens` | Token 上限 | 成本控制 |
| `change_summary` | 变更说明 | 版本追踪 |

---

## 关键设计决策

### 1. Tool 副作用分级

```
read_only → local_write → external_write → external_send → destructive → privileged
   无审批       按策略         条件审批         默认审批        强制审批      强制审批
```

### 2. 幂等控制

```json
// 有副作用必须支持幂等
if side_effect != "read_only":
    assert idempotency.supported == true
```

### 3. Prompt 分层

```
safety (最高) → identity → domain → behavior → output_contract → error_policy (最低)
```

**安全规则不可绕过，必须存在 safety 片段**

### 4. 模型兼容性

```json
{
  "required_capabilities": ["tool_calling", "structured_output"],
  "provider_allowlist": ["openai", "anthropic"]
}
```

**运行前验证模型是否满足要求**

---

## 下一步

继续创建剩余的定义对象 Schema：
1. model-policy.schema.json
2. context-policy.schema.json
3. loop-profile.schema.json
4. permission-profile.schema.json
