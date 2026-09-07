# 06: 运行追溯（Task / AgentRun / Event / provenance）

**What to build:** 将一次 `ProductQuestion` 的问答过程关联到 `Task`、`AgentRun`、`ContextPackage`、`AnswerDraft` 和关键 `Event`，支持通过 `run_ref` 追溯输入、配置、证据、回答和失败原因。

**Blocked by:** 04

**Status:** ready-for-agent

## 目标

- 创建并关联技术运行对象；
- 冻结实际使用的 Agent/Prompt/Context/Permission/知识版本；
- 记录关键业务和技术事件；
- 让历史运行可解释，不被“当前最新配置”改写。

## 输入 / 输出

- 输入：`ProductQuestion`、ContextPackage、AnswerDraft、运行配置和结果
- 输出：`Task`、`AgentRun`、事件序列、provenance 关联和可查询的 `run_ref`

## 涉及的契约

- B2 `Task` 和 `AgentRun` 生命周期；
- `ContextPackage`、`Artifact`、`Event`、`provenance`；
- AgentSpec、PromptPackage、ContextPolicy、PermissionProfile 和知识来源版本引用。

## 验收标准

- [ ] 一次 ProductQuestion 至少关联一个 Task 和一个 AgentRun；
- [ ] AgentRun 记录实际使用的配置版本和知识来源版本；
- [ ] ContextPackage、AnswerDraft 和关键 Event 都可通过 run_ref 关联；
- [ ] 能追溯提交、检索、上下文组装、生成、失败和处置阶段；
- [ ] 运行失败时仍保留失败事件和失败原因；
- [ ] 修改当前配置后，历史运行仍能解释原始版本。

## 拒绝 / 失败验收

- [ ] 缺少 Task、AgentRun 或 run_ref 时不能声称追溯成功；
- [ ] 事件写入失败不会静默吞掉运行结果；
- [ ] 不允许跨租户查询运行记录。

## 明确不包含

- 完整 Checkpoint 恢复；
- 分布式事件总线；
- Transactional Outbox；
- 生产级多进程一致性；
- 30 天清理执行（属于 10）。