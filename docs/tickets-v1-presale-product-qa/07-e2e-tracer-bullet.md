# 07: 端到端 tracer bullet 主路径测试

**What to build:** 用固定商品资料和确定性替代实现，一次验证从 `ProductQuestion` 到 `AnswerDraft`、人工处置和运行追溯的完整主路径。

**Blocked by:** 04、05、06

**Status:** ready-for-agent

## 目标

建立 V1 唯一最高层业务门禁，证明平台组件真正连成一条业务链路。

## 输入 / 输出

- 输入：内部操作者、租户、单商品问题、固定版本商品资料
- 输出：带证据的 AnswerDraft、处置结果、run_ref 和完整关键事件链

## 涉及的契约

- ProductQuestion、EvidenceItem、ContextPackage、AnswerDraft、HumanDisposition；
- Task、AgentRun、Event、provenance；
- B0 现有模型和状态机。

## 验收标准

- [ ] 固定商品资料 → 单商品问题 → EvidenceItem → ContextPackage → AnswerDraft 全链路可运行；
- [ ] AnswerDraft 包含字段/片段级证据引用；
- [ ] 能执行至少一种接受或编辑处置并留痕；
- [ ] 能通过 run_ref 查询问题、配置、Context、证据、回答和事件；
- [ ] 业务状态和 Task/AgentRun 技术状态分别可断言；
- [ ] 同一固定输入可重复得到可比较结果。

## 拒绝 / 失败验收

- [ ] 任一阶段失败时，端到端结果明确标记失败或转人工；
- [ ] 不能以空回答或缺少证据的成功状态通过测试；
- [ ] 主路径不触发任何消费者发送或业务写操作。

## 明确不包含

- 真实模型、RAG、商品中心或客服系统接入；
- 多 Agent 和复杂 Loop；
- 生产部署和性能压测。