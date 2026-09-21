# B6 业务 Agent — 目的优先系统设计

## 设计结论

- **是否可以进入实现**：**有条件** — 需要先收敛 B6 的范围，现有指南过度设计
- **当前最大风险**：指南提出的 3 个 Agent（售前/直播切片/自媒体）需要 ASR、视频处理、图像生成等外部服务，超出当前"单进程本地闭环"边界
- **需要先解决的一个问题**：B6 的真实增量是什么？现有 `PresaleAgent` + `PresaleQaRunner` 已是完整业务 Agent，B6 能提供的增量是与 B5 LoopStrategy 的集成验证

## 目的与边界

- **目的**：将现有 PresaleAgent 作为 B6 首个业务 Agent 范例，验证 B0-B5 全栈集成（Agent Protocol + Harness + LoopStrategy + RuntimeFactory），为后续 Agent 提供可复制的模板
- **目标用户**：平台开发者（参考范例创建新 Agent）
- **成功判据**：PresaleAgent 能通过 Harness + RetryOnLowEvidenceLoop 驱动，多步循环端到端可观察
- **做什么**：
  1. 将 PresaleAgent 适配为标准 B5 Agent（已通过 T01 完成）
  2. 验证 PresaleAgent + RetryOnLowEvidenceLoop 端到端场景
  3. 编写集成测试：单步命中 + 多步重试 + 需人工 + 异常
  4. 更新路线图和交付物清单
- **不做什么**：
  - 不实现直播切片 Agent（需要 ASR/视频处理）
  - 不实现自媒体运营 Agent（需要图像/文本生成）
  - 不引入 ASR、视频处理、图像生成等外部服务
  - 不实现复杂 Skill 触发机制
  - 不实现 AgentSpec JSON Schema 配置加载（当前 PresaleAgent 是硬编码的）
  - 不接入真实 LLM（仍为确定性/模拟）
- **不承诺**：
  - 不承诺直播切片/自媒体 Agent 的时间表
  - 不承诺 AgentSpec 配置化（当前为代码直连）

## 核心数据管道

```text
ProductQuestion
→ [RuntimeFactory] 创建 PresaleAgent + RetryOnLowEvidenceLoop
→ [Harness.execute] 驱动多步循环
→ [PresaleAgent.run] → PresaleQaRunner.ask
→ [retrieve] → [context] → [generate] → [disposition]
→ [Loop.decide] → CONTINUE / FINALIZE / NEED_HUMAN / STOP
→ 输出 AnswerDraft + AgentOutcome
```

## 契约摘要

| 段 | 输入 | 输出 | 不变量 | 失败行为 |
|---|---|---|---|---|
| RuntimeFactory.create_b6_agent() | database, sources, env | (Agent, LoopStrategy) | 租户隔离、幂等 | 配置缺失→明确错误 |
| Harness.execute(q, agent) | question, agent | AgentOutcome | max_steps 有界 | Agent 异常→向上 |
| AgentOutcome | — | terminal + steps + answer_draft | terminal 三选一 | — |

## 最小闭环与验收

- **端到端路径**：
  1. 创建 RuntimeFactory（SQLite + 确定性检索）
  2. 创建 PresaleAgent + RetryOnLowEvidenceLoop
  3. 提交 ProductQuestion → Harness.execute → 验证 terminal + answer_draft
  4. 单步命中（证据匹配→FINALIZE）
  5. 多步重试（无证据→CONTINUE→有证据→FINALIZE）
  6. 需人工（冲突→NEED_HUMAN）
- **验收条件**：集成测试覆盖以上路径，现有 296 测试不变

## 进入编码前门禁

- [x] 目的和成功判据一句话可说清
- [x] 做什么/不做什么/不承诺明确
- [x] 核心管道和失败出口已表示
- [x] 每段有输入/输出/不变量
- [x] 无高风险事项
- [x] 验收标准可执行

**结论：可以进入 /to-tickets。**
