# ADR-0001: Agent 协议签名扩展（StepContext）

> 状态：已接受
> 日期：2026-09-21
> 决策者：领域建模阶段
> 关联决策：D-B10

## 上下文

B4 建立的 `Agent` Protocol 签名为：

```python
class Agent(Protocol):
    async def run(self, question: Any) -> AgentRunResult: ...
```

B5 激活 CONTINUE 分支后，Agent 可能被多次调用（多步循环）。如果 Agent 不知道"上一步发生了什么"，第 N+1 步会重复第 N 步的逻辑——对确定性的 presale QA，这意味着完全相同的结果。

## 决策

**将 Agent.run 签名扩展为**：

```python
class Agent(Protocol):
    async def run(self, question: Any, step_context: StepContext | None = None) -> AgentRunResult: ...
```

`StepContext` 包含 `step_index: int` 和 `previous_tool_calls: list[dict]`。

单步 Agent（如当前 PresaleAgent）忽略 `step_context` 参数，行为不变。

## 理由

- **替代方案 A：Harness 通过 Agent 内部状态管理步间信息** — 耦合 Harness 与 Agent 内部实现，违反 Protocol 边界
- **替代方案 B：不传步间信息，Agent 自行管理** — Agent 需要维护跨步状态，增加复杂度，且 Harness 无法观察步间状态
- **选择方案 C（当前）：显式参数传递** — 最小侵入，Agent 自主决定是否使用，单步 Agent 零影响

## 后果

- **正面**：Agent Protocol 的步间语义显式化；单步 Agent 零迁移成本
- **负面**：所有 Agent 实现者需了解 step_context 参数（虽然可以忽略）；现有 FakeAgent 测试需加 `**kwargs` 或显式参数
- **迁移**：`PresaleAgent.run` 不改签名（Python 允许调用者传多余参数给不接收的函数...不对，这会报 TypeError）

**修正**：`PresaleAgent.run` 必须接受 `step_context` 参数（即使是 `**kwargs` 模式），否则 Harness 传参会报错。最小迁移：

```python
async def run(self, question, step_context=None):  # 添加默认参数
    ...
```
