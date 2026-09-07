# 03: ProductQuestion → ContextPackage

**What to build:** 把单商品 `ProductQuestion`、已授权知识证据和 Agent/Prompt/Policy 配置组装为通过 B0 校验的 `ContextPackage`，并执行租户、权限和预算检查。

**Blocked by:** 01

**Status:** ready-for-agent

## 目标

- 将业务输入转换为可校验的运行上下文快照；
- 校验租户、操作者和单商品范围；
- 对每个来源保留 provenance；
- 超预算时显式失败或转人工，不静默截断。

## 输入 / 输出

- 输入：`ProductQuestion`、已授权知识证据、Agent/Prompt/ContextPolicy/PermissionProfile 配置
- 输出：通过 B0 校验的 `ContextPackage`（来源、优先级、token、provenance、摘要）

## 涉及的契约

- `ContextPackage` 通过 B0 模型校验；
- `ContextPolicy` 的来源、预算、去重、排序和脱敏策略；
- `PermissionProfile` 的只读边界和租户隔离；
- `AgentSpec`、`PromptPackage` 的冻结版本引用。

## 验收标准

- [ ] 给定单商品问题和已授权证据，能生成合法 `ContextPackage`；
- [ ] 每个来源都带 provenance，并记录来源版本、定位和摘要；
- [ ] 问题租户与知识租户不一致时拒绝；
- [ ] 跨商品范围知识被拒绝；
- [ ] token 总量或单来源超预算时显式失败或转人工；
- [ ] 去重和优先级排序行为与 ContextPolicy 一致。

## 拒绝 / 失败验收

- [ ] 权限失败产生拒绝结果和明确原因码，不静默跳过；
- [ ] 上下文超预算失败不是静默截断；
- [ ] 契约校验失败返回可识别错误。

## 明确不包含

- 知识检索本身（属于 02）；
- 回答生成和转人工判定（属于 04）；
- 处置与留痕（属于 05）；
- 完整 RBAC/ABAC 和通用 Tool 执行器；
- 任何业务写操作。