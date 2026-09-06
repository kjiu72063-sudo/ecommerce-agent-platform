# JSON Schema 全部完成总结

> 更新日期：2026-09-01
> 状态：17/17 Schema 文件全部完成 ✅

---

## 完成情况

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
| loop-profile.schema.json | 14 | 迭代策略、停止条件 |
| permission-profile.schema.json | 8 | 权限规则、Deny 优先 |

### 运行对象（schemas/runtime/）- 7/7 ✅

| 文件 | 定义类型数 | 核心知识点 |
|---|---|---|
| task.schema.json | 18 | 幂等键、预算、保留策略 |
| agent-run.schema.json | 20 | 依赖冻结、租约、模型选择 |
| checkpoint.schema.json | 9 | 副作用账本、恢复令牌 |
| tool-call.schema.json | 15 | 幂等键、权限决策 |
| approval.schema.json | 12 | 一次性审批、职责分离 |
| artifact.schema.json | 16 | 不可变、数据分类、加密 |
| event.schema.json | 9 | CloudEvents 兼容、追踪 |

---

## 关键设计决策总结

### 1. 安全设计

```
- Secret 不能进入 Context/Event/Prompt
- 跨租户默认拒绝
- Deny 始终优先
- 默认决策是 deny
- 敏感数据必须加密
```

### 2. 可恢复性

```
- Checkpoint 定期保存
- 副作用账本防重复执行
- 租约管理防止并发
- 恢复令牌防篡改
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

### 5. 幂等控制

```
- Task: tenant + source + idempotency_key
- ToolCall: tool + target_resource + idempotency_key
- Event: consumer + event_id
```

### 6. 不可变性

```
- 定义对象发布后不可修改
- Checkpoint 提交后不可修改
- Event 写入后不可修改
- Artifact 内容不可修改
```

---

## 文件统计

| 类别 | 文件数 | 定义类型总数 |
|---|---|---|
| 公共类型 | 2 | 26 |
| 定义对象 | 8 | 106 |
| 运行对象 | 7 | 99 |
| **总计** | **17** | **231** |

---

## 下一步

JSON Schema 文件全部完成！接下来可以：

1. **创建示例文件** - 15 个有效示例 + 19 个无效示例
2. **创建状态机 JSON** - 6 个状态机定义
3. **创建一致性测试** - 31 项测试
4. **创建导出脚本** - 生成合同包

你想继续哪个方向？
