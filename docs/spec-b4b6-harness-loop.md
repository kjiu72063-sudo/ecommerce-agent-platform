# B4–B6 Harness / Loop / Agent 规格

> 里程碑：最小可观察 Agent 闭环
> 基线：V1 + 外部适配器契约已收敛；领域建模完成（决策 D-B1..B8）
> 词汇：见 `CONTEXT.md`；领域模型：`docs/domain-model-b4b6.md`

## Problem Statement

平台目前只有一个"单次售前问答"业务流（`PresaleQaRunner.ask`）。当平台需要运行更多业务 Agent、或在一次运行内进行多步工具循环时，缺少一个可复用的"执行 Agent + 决策何时停止"的通用层。本轮先做一个最小可观察的闭环，把现有售前问答作为第一个被 Harness 驱动的 Agent，并抽象出可复用的 Harness（执行壳）与 Loop（循环决策）层。

## Solution

引入可复用的 Agent 执行与决策循环层：

- **Harness（执行壳）**：创建一个 `AgentRun`，用可注入的 Agent 实例执行业务步骤，暴露只读工具（`retrieve`），把执行拆成 `AgentStep` 并记录 `ToolCall`/`Event`，返回可观察输出。
- **Loop（循环决策）**：每个 `AgentStep` 后决策 `continue` / `finalize` / `need_human`，受 `max_steps` 约束。
- 首实例：复用现有售前 QA 作为 Agent；`retrieve` 工具复用 `RetrievalPort` 契约（只读）。
- 同步、请求内直连；本轮 `continue` 单步终态（多步重查留待后续加工具）。

## User Stories

1. 作为内部客服运营，我想提交一个售前问题，使其经 Harness 执行并得到一个可观察的终态（输出或转人工），以便我能确定本次运行已完成。
2. 作为客服运营，我想在无证据/证据冲突时看到 `need_human` 终态，以便我知道需要人工复核，而不是误当"系统失败"。
3. 作为客服运营，我想看到本次 `AgentRun` 的步骤数、所用工具与最终决策，以便我能追溯一次运行如何走到终态。
4. 作为平台开发者，我想用一个通用 Harness 驱动不同 Agent 实例，以便新业务 Agent 能复用执行壳与工具注册而不重写。
5. 作为平台开发者，我想用一个可配置的 Loop 决策策略（含 `max_steps`），以便控制一次运行的上限、防止失控。
6. 作为平台开发者，我想让 `retrieve` 只执行只读知识查询，以便本轮不引入有副作用的工具。
7. 作为客服运营，我想同一问题的重复提交保持幂等（同 key 同结果），以便重试不产生重复执行。
8. 作为客服运营，我想 `need_human` 即终态（不继续循环），以便已需人工时不会空转更多步骤。

## Implementation Decisions

- 新增模块（逻辑职责，不指具体文件路径）：
  - `Harness`：持有一个工具集、驱动一个 `AgentRun`、把执行拆成 `AgentStep`、记录 `ToolCall`/`Event`、暴露每步可观察输出。
  - `Loop`：`decide(step, step_count) -> continue | finalize | need_human`，受 `max_steps`（默认 5）约束。
  - `Tool`（`retrieve`）：包装 `RetrievalPort`，只读；调用产生一个 `ToolCall` 记录。
  - Agent 实例：包装现有售前 QA（`PresaleQaRunner`）为一个"单步业务执行 + need_human 信号"的 Agent。
- 分层包装（决策 D-B6）：Harness 在其外层编排一个 `AgentRun`；`PresaleQaRunner.ask` 内部业务流不变。
- 终态语义（D-B2）：`need_human` 即终态；`max_steps` 达到即终态；`finalize` 为正常输出终态。
- 本轮 `continue` 单步终态（D-B4）：决策策略存在 `continue` 分支，但在当前工具集下不触发；多步重查留待后续加工具。
- 幂等（沿用）：同 key 重放返回已持久结果；Harness 复用它所在运行层已有的幂等保证，不另造一套。
- 时序：同步、请求内直连（D-B7）。无外部副作用工具（D-B8）。

## Testing Decisions

- 好测试只测外部行为（`Harness.execute` 的可观察输出），不测内部实现细节。
- 主测试接缝：`Harness.execute(question, agent)` —— 用真实售前 QA 实例 + 可注入 `retrieve` 工具 + 可配置 Loop 驱动，断言：
  - 终态决策正确（matched→finalize；no_evidence/conflict→need_human）；
  - 步数 ≤ max_steps；
  - `retrieve` 工具调用被记录为 `ToolCall`；
  - `need_human` 即终态、不再继续；
  - 同 key 幂等（重放同结果）。
- 复用既有测试先例：`tests/b1/test_external_ports.py`（注入 transport 的契约/集成测试）、`tests/b1/test_idempotency_state.py`（幂等状态断言）。可注入 fake `retrieve` 工具与 fake Loop 策略。
- 失败/降级语义复用 `RetrievalPort` 已定契约（Slice 3：`RetrievalError` / `RETRIEVAL_DEGRADED`）。

## Out of Scope

- 多步工具循环的 `continue` 触发与多工具编排。
- 新增有副作用的工具（下单/改价/写库存）。
- 异步队列/回调。
- 新业务 Agent（除售前问答之外）。
- 真实外部检索/向量库接线（仍沿用可注入 transport，选型留待后续）。

## Further Notes

- `max_steps` 默认 5（决策 D-B5）；是否需要运行时可配置留待 ticket 阶段定。
- 决策信号来源：本轮为 AgentStep 的 `need_human` + 步数计数；置信度驱动留待后续。
- 发布到 issue tracker 时打 `ready-for-agent` 标签。
