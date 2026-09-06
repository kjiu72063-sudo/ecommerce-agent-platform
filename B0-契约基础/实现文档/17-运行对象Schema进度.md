# JSON Schema 运行对象进度总结

> 更新日期：2026-09-01

---

## 已完成的 Schema 文件

### 公共类型（schemas/common/）- 2/2 ✅

| 文件 | 定义类型数 |
|---|---|
| common-types.schema.json | 24 |
| standard-error.schema.json | 2 |

### 定义对象（schemas/definitions/）- 8/8 ✅

| 文件 | 定义类型数 |
|---|---|
| agent-spec.schema.json | 16 |
| skill-manifest.schema.json | 20 |
| tool-manifest.schema.json | 19 |
| prompt-package.schema.json | 11 |
| model-policy.schema.json | 11 |
| context-policy.schema.json | 17 |
| loop-profile.schema.json | 14 |
| permission-profile.schema.json | 8 |

### 运行对象（schemas/runtime/）- 2/7

| 文件 | 状态 | 定义类型数 |
|---|---|---|
| task.schema.json | ✅ | 18 |
| agent-run.schema.json | ✅ | 20 |
| checkpoint.schema.json | ⏳ | - |
| tool-call.schema.json | ⏳ | - |
| approval.schema.json | ⏳ | - |
| artifact.schema.json | ⏳ | - |
| event.schema.json | ⏳ | - |

---

## 新学到的知识点

### Task

| 字段 | 作用 | 关键设计 |
|---|---|---|
| `intent` | 结构化意图 | 路由依据 |
| `source` | 任务来源 | openclaw/api/cron/webhook/ui/system |
| `idempotency_key` | 幂等键 | 防止重复创建 |
| `budget` | 预算 | 成本控制 |
| `retention_policy` | 保留策略 | 数据生命周期 |

### AgentRun

| 字段 | 作用 | 关键设计 |
|---|---|---|
| `attempt` | 尝试次数 | task + attempt 唯一 |
| `agent_snapshot` | Agent 快照 | 不可变版本 |
| `resolved_dependencies` | 已解析依赖 | 运行期间不变 |
| `dynamic_dependency_activations` | 动态激活 | 按需加载，首次冻结 |
| `model_selection_history` | 模型选择历史 | 回退追踪 |
| `lease` | 租约 | 并发控制 |

---

## 关键设计决策

### 1. 依赖冻结

```
启动时：
  - 解析所有基础依赖
  - 冻结精确版本和摘要
  - 保存到 resolved_dependencies

运行时：
  - 按需激活技能/工具
  - 首次使用前冻结
  - 追加到 dynamic_dependency_activations
```

### 2. 租约机制

```
Worker 获取租约 → 定期心跳 → 租约过期停止
     ↓
Fencing Token 防止过期提交
```

### 3. 模型选择历史

```
initial → fallback → fallback → ...
   ↓
当前选择必须等于最后一条
路由不能重复访问
```

### 4. 幂等控制

```
Task: tenant + source + idempotency_key
AgentRun: task + attempt
```

---

## 下一步

继续创建剩余的运行对象 Schema：
1. checkpoint.schema.json
2. tool-call.schema.json
3. approval.schema.json
4. artifact.schema.json
5. event.schema.json
