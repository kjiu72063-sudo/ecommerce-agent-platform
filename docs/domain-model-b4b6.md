# B4–B6 领域模型（Harness / Loop / Agent）

> 状态：领域模型已确认（决策 A 分层包装）
> 更新时间：2026-09-22
> 适用范围：可复用的 Agent 执行与决策循环层；本轮驱动只读售前问答
> 词汇表见 `CONTEXT.md`，决策见 `docs/domain-decisions.md`

## 1. 建模范围

本轮只建一条最小、可观察、可失败的 Agent 闭环：

```text
内部客服/运营人员
→ 提交 ProductQuestion（含 key）
→ [Harness] 创建 AgentRun、驱动 Agent 实例
→ [AgentStep] 调用 retrieve 工具（只读）→ 上下文 → 生成草稿
→ [Loop 决策] finalize / need_human / (continue 保留)
→ 输出 AnswerDraft + 决策/步骤 trace
└─ 幂等 / 保留 / 处置 / 装配：沿用既有契约
```

## 2. 聚合与关系

- **Agent**（能力）是 **1 个 AgentRun** 的执行主体；`AgentRun` 已有（Task 的一次执行尝试）。
- **Harness** 是执行壳：持有一个工具集（本轮 `retrieve`）、驱动一个 `AgentRun`、把业务执行拆成 `AgentStep`、记录 `ToolCall`/`Event`、暴露每步可观察输出。
- **Loop** 是决策策略：每 `AgentStep` 后输出 `continue` / `finalize` / `need_human`；受 `max_steps` 约束。
- 关系（分层包装）：Harness 在其外层编排一个 `AgentRun`；`PresaleQaRunner.ask` 的内部业务流保持为一个 `AgentStep`（检索→上下文→生成→处置建议）。

## 3. 不变量

1. 一个 `AgentRun` 由同一租户的同一 `ProductQuestion` 触发；跨租户拒绝（沿用）。
2. `max_steps` 有界；超过即终态。
3. `need_human` 即终态，不再继续循环。
4. `ToolCall` 本轮只允许只读知识查询（沿用边界规则 3）。
5. 决策与步骤是可追溯历史，不通过修改当前状态抹除（沿用 Event/provenance 规则）。
6. 技术失败（如 retrieve 失败）不等于业务转人工（need_human）；二者须可区分、均可观测。

## 4. 边界场景

- **A（matched）**：retrieve 返回证据 → 生成草稿（need_human=false）→ Loop `finalize` → 输出 + AgentRun 完成 + Event 记录 ToolCall/决策。
- **B（无证据）**：retrieve 返回 NO_EVIDENCE → 草稿 need_human=true → Loop `need_human`（终态）→ 转人工；AgentRun 以"需人工"而非"失败"结束。
- **C（多步）**：max_steps=5。策略看到对应信号才 continue：无证据重查、工具 error 重试、review 再精炼、act 继续行动。次数耗尽是 stop，不是再转成 finalize。
- **D（顺序编排）**：售前问答的回答文本可以交给评价分析。任一 Agent 需要人工或步数耗尽，后面的 Agent 不运行；整体终态取这一步，不拼接后续结果。

## 5. 待规格阶段细化（不阻塞方向）

- `max_steps` 达到时的终态 reason 编码；
- `retrieve` 工具调用与 `ToolCall` 的记录字段；
- Loop 决策信号的来源（本轮为 AgentStep 的 need_human + step 计数）；
- Harness 暴露的每步可观察输出的字段集合。

## 6. 进入规格阶段结论

领域方向已收敛（决策 A：分层包装），可以进入 `/to-spec` 把 Harness/Loop 的契约、终态语义与可观察输出写成可验收规格。
