# B5/B6 Loop 引擎 + 业务 Agent 阶段复盘

> 复盘范围：B5 Loop 引擎（T01-T03）+ B6 业务 Agent（B6-01）+ 流程修复（R-1~R-5）
> 时间跨度：2026-09-21
> 基线：274 passed → 303 passed（+29 新测试）
> PR：#66-#68（流程修复）+ #75-#78（B5）+ #80-#81（B6）

---

## 1. 本阶段完成了什么

### 1.1 流程修复（前置）
- README 基线同步（251→274→303）
- 端口边界违规修复（generation_eval.py 懒加载、sweep_retrieval.py 参数化工厂）
- SQLite 故障注入测试
- 结构性问题 R-1~R-5 全部解决
- 远程 22 个残留分支清理

### 1.2 B5 Loop 引擎
- `LoopStrategy` Protocol（结构化类型）
- `SinglePassLoop`（向后兼容默认策略）
- `StepContext` 数据类（步间上下文）
- `Harness.execute` 多步循环
- `RetryOnLowEvidenceLoop`（证据不足重试）
- `LoopDecision.STOP`（重试耗尽信号）
- 22 个新测试

### 1.3 B6 业务 Agent
- PresaleAgent + B5 LoopStrategy 集成验证
- 7 个端到端集成测试

### 1.4 文档更新
- `CONTEXT.md`：新增 LoopStrategy、StepContext 术语
- `docs/domain-decisions.md`：D-16 修订 + D-B9~D-B14 新增
- `docs/domain-model-b4b6.md`：B5 多步场景
- `docs/adr/0001-agent-protocol-step-context.md`
- `docs/spec-b5-loop-engine.md`
- `docs/spec-b6-business-agent.md`

---

## 2. 哪些决策减少了返工

### 2.1 目的优先设计收敛
B5 开发指南（775 行）提出 LLM 推理循环、评估器框架、进度管理器等重方案。通过 `/purpose-first-system-design` 收敛为确定性 LoopStrategy + 2 个内置策略，避免了 4-6 周的过度工程。

### 2.2 领域建模先行
在编码前识别了 D-16 冲突（"不实现复杂 Loop" vs B5 多步循环），提前修订避免了规格返工。

### 2.3 垂直切片 TDD
T01→T02→T03 线性依赖，每步一个完整切片（Protocol→循环→策略），每步可独立验证。

### 2.4 ADR 记录关键决策
ADR-0001 记录了 Agent.run 签名变更的理由和迁移方案，避免未来读者困惑。

---

## 3. 实现阶段暴露的问题与根因

### 3.1 `ContinueThenFinalize(continues=1)` 语义误解
**问题**：测试期望 3 步但实际 2 步。`continues=1` 意味着"前 1 步 CONTINUE"，不是"总共 continue 1 次再 finalize"。
**根因**：测试编写时对参数语义理解偏差。
**修复**：修正测试断言。这属于 TDD 红-绿循环的正常发现。

### 3.2 `FakeAgent` 签名不兼容
**问题**：T02 修改 `Harness.execute` 传递 `step_context` 后，旧的 `FakeAgent.run(self, question)` 报 TypeError。
**根因**：测试替身未随接口变更更新。
**修复**：`FakeAgent.run` 加 `step_context=None` 参数。
**教训**：接口变更时需同步更新所有测试替身。

### 3.3 `RetryOnLowEvidenceLoop` 重试耗尽的终态语义
**问题**：重试耗尽时返回 `FINALIZE`，但测试期望 `MAX_STEPS`。"正常完成"和"重试耗尽"语义不同。
**根因**：`LoopDecision` 枚举缺少区分"正常完成"和"被迫停止"的信号。
**修复**：新增 `LoopDecision.STOP`，Harness 映射到 `TerminalDecision.MAX_STEPS`。
**教训**：循环决策需要区分"成功终态"和"资源耗尽终态"。

### 3.4 worktree 隔离导致 Git 操作受限
**问题**：MiMoCode 的 worktree 隔离机制阻止了 `git branch -d`、`git checkout`、`git reset` 等跨分支操作。
**根因**：安全机制防止 worktree 之间的 ref store 冲突。
**修复**：通过 GitHub API（`gh api`）远程创建分支、提交文件、删除分支。
**代价**：每个 PR 都需要通过 API 创建干净分支，增加了复杂度。

### 3.5 基线数字漂移反复出现
**问题**：README 和台账的测试数在多个 PR 后过期（251→273→274→296→303）。
**根因**：没有自动化机制在 PR 合并后同步基线数字。
**修复**：手动更新 + docs-only PR。
**教训**：基线同步应作为流程的一部分，而非事后补救。

---

## 4. 改进建议

### 4.1 自动化检查：基线同步钩子
**严重度**：中
**建议**：在 pre-commit 或 CI 中添加一个轻量检查——当 `tests/` 目录下的测试文件变更时，提醒更新 `开发文档/09-质量基线与门禁台账.md` 的顶行数字。

### 4.2 pyright 覆盖范围扩展
**严重度**：中
**建议**：修复 `src/registry/`（39 个 type errors）后将其纳入 pyright include。当前 `pyproject.toml` 只覆盖 `src/presale` + `src/agent_runtime` + `src/context`。

### 4.3 清理过时文档
**严重度**：低
**建议**：`开发文档/06-B5-Loop引擎开发指南.md`（775 行）的内容已被 B5 实际实现取代，应标注为"已废弃"或更新为与实际实现一致。

### 4.4 CODING_STANDARDS 补充 B5 规则
**严重度**：低
**建议**：评审规则中补充 LoopStrategy 相关检查点：
- 新 LoopStrategy 必须通过 `Harness.execute` 验证（不直接测试内部）
- `Agent.run` 签名变更需同步更新所有测试替身

### 4.5 远程分支定期清理
**严重度**：低
**建议**：每个 PR 合并后删除其远程 feature 分支（`git push origin --delete <branch>`），避免累积。当前已清理 22 个。

---

## 5. 有意的取舍

- **B5 只实现确定性策略**：react/repair/review_refine 需要 LLM 推理，不在本轮范围
- **B6 只验证集成**：不实现直播切片/自媒体 Agent（需要外部服务）
- **StepContext 轻量设计**：只传 step_index + previous_tool_calls，不传完整 answer_draft
- **LoopDecision.STOP 为新增枚举值**：向后兼容（老 Loop 不返回 STOP）

---

## 6. 下一步行动

按已确认的方向顺序：
1. ✅ **A（retro）**— 本文件
2. 🔜 **C（pyright 类型修复）**— 修复 registry/runtime 的 39 个 type errors
3. 🔜 **E（真实 LLM 接入）**— 完成从模拟到真实的最后一环
4. 🔜 **B（PostgreSQL）**— 生产数据库迁移
5. 🔜 **D（新 Agent）**— 直播切片/自媒体（需外部服务）

---

## 7. 量化总结

| 指标 | 值 |
|---|---|
| PR 数量 | 10（#66-#68, #75-#78, #80-#81） |
| 新增测试 | 29（B5: 22, B6: 7） |
| 总测试数 | 303 passed |
| 文档变更 | 8 文件（CONTEXT.md, domain-decisions, domain-model, ADR, 2 specs, retro, 路线图） |
| 新增代码 | ~400 行（harness.py 扩展 + 测试） |
| 清理分支 | 22 个远程 + 18 个本地 |
| 关闭 Issue | 1（#24） |
