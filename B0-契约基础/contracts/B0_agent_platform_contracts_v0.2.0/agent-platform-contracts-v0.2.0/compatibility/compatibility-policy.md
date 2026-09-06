# B0 Schema 兼容与演进策略

## 三种版本

| 版本 | 示例 | 作用 |
|---|---|---|
| API Version | `agent-platform/v1alpha1` | Schema 方言和整体兼容边界 |
| Definition Version | `1.2.0` | 单个定义资源的 Semantic Versioning |
| Contract Package Version | `0.2.0` | 本合同包整体发布版本 |

运行资源不使用 Semantic Versioning；运行状态由 `revision`、Event Sequence 和状态机管理。

`0.1.0` 与 `0.2.0` 均为未批准的 `review_candidate`。本次字段重命名和必填字段增加用于修正评审中发现的契约歧义，`0.2.0` 明确替代 `0.1.0` 候选包，不承诺候选包之间的运行数据兼容。进入 `approved` 后，所有变更必须严格按下表执行。

## 兼容判定

| 变化 | 兼容性 | 版本动作 |
|---|---|---|
| 新增可选字段 | 向后兼容 | Minor |
| 新增必填字段 | 不兼容 | API Version 或 Major |
| 删除字段 | 不兼容 | API Version 或 Major |
| 字段重命名 | 不兼容 | API Version 或 Major |
| 收紧长度、正则或数值范围 | 不兼容 | API Version 或 Major |
| 放宽约束 | 通常向后兼容 | Minor，仍需安全评审 |
| 枚举新增值 | 条件兼容 | 消费者能处理未知值时为 Minor，否则 Major |
| 字段语义改变 | 不兼容 | Major |
| 权限扩大 | 安全敏感变更 | 至少 Minor，并重新审批 |
| Tool 副作用等级提高 | 不兼容 | Major，并重新审批 |
| Prompt 行为不变的文字修正 | 兼容 | Patch |

## 禁止规则

- 不允许原地修改已经发布的定义版本；
- 不允许把 `latest` 写入 AgentRun 依赖快照；
- 不允许迁移覆盖历史 Task、Run、Checkpoint、ToolCall、Approval、Artifact 或 Event；
- 不允许因 Runtime 升级改变历史成本；
- 不允许因 Skill 或 Tool 新版本上线改变运行中 Run 的解析结果；
- 不允许覆写或删除 AgentRun 已记录的动态依赖激活与模型选择历史；
- 不允许把 ModelPolicy 回退链之外的模型切换伪装为同 Run Fallback；
- 不允许静默扩大权限或降低副作用等级。

## 兼容性验证流程

```text
生成旧版与新版 Schema
→ 计算结构差异
→ 按规则分类 Breaking / Compatible / Security-sensitive
→ 运行旧版有效示例
→ 运行新版有效和无效示例
→ 运行跨版本恢复测试
→ 人工评审权限与副作用变化
→ 发布新版本
```

跨版本自动差异工具属于后续实现，但不得改变本策略中的判定规则。
