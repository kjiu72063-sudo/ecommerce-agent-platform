# B5 Loop 引擎规格

> 状态：待实现
> 基线：274 passed（2026-09-21）
> 领域模型：`docs/domain-model-b4b6.md`（B5 更新）
> 领域决策：`docs/domain-decisions.md`（D-B9~D-B14）
> ADR：`docs/adr/0001-agent-protocol-step-context.md`

---

## Problem Statement

平台开发者无法配置 Agent 的迭代策略。当前 `Loop.decide` 只支持单步终态（FINALIZE），CONTINUE 分支结构性存在但永不触发。当 Agent 需要在"证据不足"时重试检索、或在多步工具循环中累积信息时，Harness 无法驱动多步执行。平台需要一个可注入的 LoopStrategy 协议和一个具体的多步策略实现，为未来非确定性 Agent（B6）提供架构就绪性。

---

## Solution

将 Loop 从具体类升级为可注入的 `LoopStrategy` Protocol，提供两个内置策略：
- `SinglePassLoop`（默认，向后兼容：每步 FINALIZE）
- `RetryOnLowEvidenceLoop`（证据不足时 CONTINUE，有证据时 FINALIZE）

扩展 `Agent.run` 签名以接受可选的 `StepContext`，使 Agent 能根据步间信息调整行为。Harness.execute 驱动多步循环，每步记录 AgentStep + ToolCall，全程可观察。

---

## User Stories

1. 作为平台开发者，我想注入一个 LoopStrategy 到 Harness，以便不同 Agent 使用不同的迭代决策逻辑。
2. 作为平台开发者，我想使用 SinglePassLoop 作为默认策略，以便现有单步 Agent（PresaleAgent）行为不变。
3. 作为平台开发者，我想使用 RetryOnLowEvidenceLoop 让 Agent 在检索无证据时自动重试，以便提高证据命中率。
4. 作为平台开发者，我想确保 need_human 即终态（任何策略下），以便已需人工时不会空转更多步骤。
5. 作为平台开发者，我想确保 max_steps 是硬上限，以便任何策略都不能无限循环。
6. 作为平台开发者，我想在 AgentStep 中看到每步的 tool_calls，以便我能追溯一次多步运行如何走到终态。
7. 作为平台开发者，我想通过 StepContext 知道上一步的 tool_calls 摘要，以便 Agent 能根据历史调整行为。
8. 作为平台开发者，我想在 MAX_STEPS 终态时获得最后一步的 answer_draft，以便调用方知道"重试耗尽"的结果。
9. 作为平台开发者，我想让单步 Agent 忽略 step_context 而不报错，以便现有 Agent 实现零迁移成本。
10. 作为平台开发者，我想在 Harness.execute 完成后才更新幂等 claim，以便多步循环的中间步骤不产生不完整的持久化状态。
11. 作为平台开发者，我想让 Agent 异常直接向上传播（不被 Loop 捕获），以便异常处理由 runner 的 _mark_failed 统一清理。
12. 作为内部客服运营，我想看到多步运行的完整步骤 trace，以便我能理解系统为什么重试以及最终结论。
13. 作为平台开发者，我想通过 `format_outcome` 观察多步结果，以便在 API/CLI 中展示步骤详情。
14. 作为平台开发者，我想确保 SinglePassLoop 的行为与当前默认 Loop 完全一致，以便现有 274 个测试无需修改。
15. 作为平台开发者，我想让 LoopStrategy 的 decide 方法是纯函数（无副作用），以便策略可独立测试。
16. 作为平台开发者，我想在 RetryOnLowEvidenceLoop 中配置最大重试次数，以便不同场景有不同的重试容忍度。
17. 作为平台开发者，我想确保多步循环中每一步都产生独立的 AgentStep 记录，以便每步的 tool_calls 和 need_human 状态可独立审计。

---

## Implementation Decisions

### 1. LoopStrategy Protocol

Loop 从具体类变为 Protocol。任何实现 `decide(step: AgentStep) -> LoopDecision` 的类都可以作为策略注入。

```python
class LoopStrategy(Protocol):
    def decide(self, step: AgentStep) -> LoopDecision: ...
```

现有 `Loop` 类重命名为 `SinglePassLoop` 并实现此协议。为向后兼容，保留 `Loop = SinglePassLoop` 别名。

### 2. StepContext

新增 `StepContext` 数据类，作为 Agent.run 的可选第二参数：

```python
@dataclass
class StepContext:
    step_index: int
    previous_tool_calls: list[dict[str, Any]]
```

`step_index` 从 1 开始（与 AgentStep.index 对齐）。第 1 步调用时 `step_context=None`。

### 3. Agent.run 签名扩展

```python
class Agent(Protocol):
    async def run(self, question: Any, step_context: StepContext | None = None) -> AgentRunResult: ...
```

单步 Agent 加 `step_context=None` 默认参数即可，行为不变（D-B10/ADR-0001）。

### 4. SinglePassLoop

行为与当前 `Loop` 完全一致：`need_human` → NEED_HUMAN，否则 → FINALIZE。无 CONTINUE。

### 5. RetryOnLowEvidenceLoop

决策逻辑：
- `step.need_human == True` → `NEED_HUMAN`
- 步骤有 tool_calls 且至少一个 tool_call 的 `status` 为 `"matched"` → `FINALIZE`
- `step.index >= max_retries + 1` → `FINALIZE`（重试次数用尽，强制终态）
- 其他 → `CONTINUE`

`max_retries` 默认 2（加上首次共 3 次机会）。策略是确定性的：不引入 LLM 推理，仅基于 AgentStep 信号决策。

**信号来源**：从 `step.tool_calls` 中读取 retrieve 的 `status` 字段（`"matched"` / `"no_evidence"` / `"conflict"` / `"out_of_scope"`）。这些字段已由 `PresaleAgent._retrieve_tool_call` 填充。

### 6. Harness.execute 多步循环

修改 `Harness.execute` 的 for 循环，传递 `StepContext` 给 `agent.run`：

```python
for i in range(self._max_steps):
    ctx = StepContext(step_index=i + 1, previous_tool_calls=...) if i > 0 else None
    last = await agent.run(question, step_context=ctx)
    # ... 记录 AgentStep, 调用 loop.decide
```

### 7. MAX_STEPS 终态输出

当 for 循环耗尽（`else` 分支），`terminal = TerminalDecision.MAX_STEPS`。输出 `last.answer_draft`（最后一步的结果），与 NEED_HUMAN 语义类似但 terminal 字段不同（D-B11）。

### 8. 幂等与异常

- 幂等 claim 只在整个 execute 完成后由 runner 更新，不在 Harness 内管理（D-B12）
- Agent 异常不被 Harness/Loop 捕获，直接向上传播（D-B13）

### 9. format_outcome 扩展

`format_outcome` 已支持 steps 列表输出，多步场景无需修改。

---

## Testing Decisions

**测试原则**：只测 `Harness.execute` 的外部可观测输出（`AgentOutcome`），不测内部实现细节。

**测试接缝**：`Harness.execute(question, agent)` — 用 `FakeAgent`（可配置返回序列）+ 可注入 LoopStrategy。

**优先复用的现有测试模式**：`tests/b1/test_loop.py` 中的 `FakeAgent`、`AlwaysContinueLoop`、`ContinueThenFinalizeLoop`。

**测试矩阵**：

| # | 场景 | LoopStrategy | FakeAgent 行为 | 期望 terminal | 期望 steps 数 |
|---|---|---|---|---|---|
| T01 | 单步命中（向后兼容） | SinglePassLoop | need_human=False | FINALIZE | 1 |
| T02 | 单步 need_human | SinglePassLoop | need_human=True | NEED_HUMAN | 1 |
| T03 | SinglePassLoop 无 CONTINUE | SinglePassLoop | 每步 need_human=False | FINALIZE | 1 |
| T04 | RetryOnLow 有证据立即终态 | RetryOnLowEvidenceLoop | need_human=False, status="matched" | FINALIZE | 1 |
| T05 | RetryOnLow 无证据→CONTINUE→命中 | RetryOnLowEvidenceLoop | step1: no_evidence, step2: matched | FINALIZE | 2 |
| T06 | RetryOnLow 无证据→MAX_STEPS | RetryOnLowEvidenceLoop(max_retries=2) | 每步 no_evidence | MAX_STEPS | 3 |
| T07 | RetryOnLow need_human 即终态 | RetryOnLowEvidenceLoop | step1: no_evidence, step2: need_human=True | NEED_HUMAN | 2 |
| T08 | max_steps 硬上限 | AlwaysContinueLoop | 每步正常 | MAX_STEPS | 5 |
| T09 | StepContext 传递验证 | RetryOnLowEvidenceLoop | 记录 step_context | FINALIZE | 2 |
| T10 | Agent 异常向上传播 | Any | step2 抛异常 | raise | — |
| T11 | 幂等：单步 vs 多步结果一致 | SinglePassLoop vs RetryOnLow | 相同 question | 同 run_ref | — |
| T12 | 现有 274 测试不变 | 默认 | — | — | — |

**不新增接缝**：所有测试通过 `Harness.execute` 观察 `AgentOutcome`。

---

## Out of Scope

- LLM 推理循环的策略（react/repair/review_refine）— 需要模型调用，不在 B5 范围
- 评估器框架（Evaluator）— B6+ 关注点
- 进度管理器（ProgressManager）/ Checkpoint 恢复 — 售前 QA 是同步请求内完成
- 预算控制（token/cost/wall_time）— 仅 max_steps
- 异步队列 / 回调 — 保持同步（D-B7）
- 有副作用的工具 — 仍只限 retrieve（D-B8）
- 多 Agent 协作 — 每个 Harness 只驱动一个 Agent
- 运行时热切换策略 — 策略在构造时注入（D-B9）
- 改变 PresaleQaRunner.ask 内部业务流 — 分层包装（D-B6）

---

## Further Notes

- **B5 对 presale 的实际功能增量有限**：当前 presale 检索是确定性的，同一 question 在第 N+1 步重复检索结果相同。RetryOnLowEvidenceLoop 的真正价值是为 B6 非确定性 Agent 提供架构就绪性。
- **向后兼容是硬约束**：现有 274 个测试必须全部不变通过。SinglePassLoop 的行为必须与当前 Loop 完全一致。
- **LoopStrategy 命名**：保留 `Loop` 作为 `SinglePassLoop` 的别名，避免现有 import 断裂。
- 发布到 issue tracker 时打 `ready-for-agent` 标签。
