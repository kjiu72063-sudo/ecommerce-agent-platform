# JSON Schema 定义对象完成总结

> 更新日期：2026-09-01
> 状态：定义对象 Schema 全部完成

---

## 已完成的 Schema 文件

### 公共类型（schemas/common/）- 2/2 ✅

| 文件 | 定义类型数 |
|---|---|
| common-types.schema.json | 24 |
| standard-error.schema.json | 2 |

### 定义对象（schemas/definitions/）- 8/8 ✅

| 文件 | 定义类型数 | 核心知识点 |
|---|---|---|
| agent-spec.schema.json | 16 | Agent 定义、引用、预算 |
| skill-manifest.schema.json | 20 | 触发示例、沙箱、评估 |
| tool-manifest.schema.json | 19 | 副作用、幂等、审批 |
| prompt-package.schema.json | 11 | 分层、变量、兼容性 |
| model-policy.schema.json | 11 | 路由、回退、熔断器 |
| context-policy.schema.json | 17 | Token 预算、脱敏、压缩 |
| loop-profile.schema.json | 14 | 迭代策略、停止条件、Checkpoint |
| permission-profile.schema.json | 8 | 权限规则、Deny 优先 |

### 运行对象（schemas/runtime/）- 0/7 ⏳

| 文件 | 状态 |
|---|---|
| task.schema.json | 待创建 |
| agent-run.schema.json | 待创建 |
| checkpoint.schema.json | 待创建 |
| tool-call.schema.json | 待创建 |
| approval.schema.json | 待创建 |
| artifact.schema.json | 待创建 |
| event.schema.json | 待创建 |

---

## 新学到的知识点

### ModelPolicy

| 设计 | 说明 |
|---|---|
| **数据分类** | public/internal/confidential/restricted |
| **回退链** | 主模型失败时自动切换 |
| **熔断器** | 防止级联故障 |
| **供应商白名单** | 限制可用的模型供应商 |

### ContextPolicy

| 设计 | 说明 |
|---|---|
| **Token 预算** | 总预算 + 分来源预算 |
| **脱敏策略** | Secret 必须脱敏 |
| **压缩策略** | 超出预算时压缩 |
| **来源规则** | allow/deny 控制可见性 |

### LoopProfile

| 设计 | 说明 |
|---|---|
| **迭代策略** | single_pass/react/repair/ralph/review_refine |
| **停止条件** | 成功/失败/预算/人工/验证器 |
| **Checkpoint** | 可恢复性保障 |
| **回滚策略** | 补偿动作处理副作用 |

### PermissionProfile

| 设计 | 说明 |
|---|---|
| **Deny 优先** | 任何 deny 最终就是 deny |
| **默认拒绝** | default_decision: deny |
| **跨租户隔离** | cross_tenant_default: deny |
| **权限规则** | allow/deny/require_approval |

---

## 关键设计决策总结

### 1. 安全设计

```
- Secret 不能进入 Context
- 跨租户默认拒绝
- Deny 始终优先
- 默认决策是 deny
```

### 2. 可恢复性

```
- Checkpoint 定期保存
- 回滚策略处理副作用
- 租约管理防止并发
```

### 3. 成本控制

```
- Token 预算限制
- 预算超限必须停止
- 费用估算记录价格快照
```

### 4. 高可用

```
- 回退链支持多模型
- 熔断器防止级联故障
- 健康检查监控可用性
```

---

## 下一步

创建运行对象 Schema：
1. task.schema.json
2. agent-run.schema.json
3. checkpoint.schema.json
4. tool-call.schema.json
5. approval.schema.json
6. artifact.schema.json
7. event.schema.json
