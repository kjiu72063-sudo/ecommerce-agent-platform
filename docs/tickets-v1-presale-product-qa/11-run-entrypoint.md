# 11: 最小可观测运行入口

**What to build:** 提供从一条 `ProductQuestion` 到可追溯 `AnswerDraft` 和处置记录的 prototype 运行命令/入口，便于人工复核和端到端验证。

**Blocked by:** 07

**Status:** ready-for-agent

## 目标

- 用一条命令或一个最小入口运行一次完整问答；
- 输出问题、证据、Context、回答、处置建议和 run_ref；
- 不要求生产 UI，也不接入消费者入口。

## 输入 / 输出

- 输入：租户、操作者、单商品问题、固定商品资料集
- 输出：可打印/可查询的运行结果和 run_ref

## 涉及的契约

- ProductQuestion、EvidenceItem、ContextPackage、AnswerDraft、HumanDisposition；
- Task、AgentRun、Event、provenance 追溯。

## 验收标准

- [ ] 从根目录可执行一次完整问答并看到确定性结果；
- [ ] 输出包含证据引用、置信度信号、人工建议和 run_ref；
- [ ] 能用 run_ref 查询运行基本记录；
- [ ] 失败时输出明确失败或转人工说明；
- [ ] 运行入口只读，不触发任何业务写操作或消费者发送。

## 拒绝 / 失败验收

- [ ] 输入校验失败有明确错误；
- [ ] 输出不会伪造无证据的成功。

## 明确不包含

- 生产 Web UI；
- 完整管理后台；
- 真实客服工作台集成；
- 生产部署。