# CODING STANDARDS（评审用）

> 本文档由**评审 agent** 在 review 时读取，不参与实现。实现侧只依赖自动化门禁
> （ruff / pyright / pytest / pre-commit）。评审不重写代码，只报违反点（文件+行号+理由）。

## 门禁范围
- lint/format：`ruff check/format src`
- 类型：`pyright`（限定 `src/presale` + `src/agent_runtime` + `src/context`）
- 测试：`pytest`（tests/）

## 评审必查规则

1. **幂等/失败清理不变量（`PresaleQaRunner.ask` 及任何状态机）**
   任何改动其重放或失败清理分支，必须：
   - 每次运行后 claim 状态落在 `in_progress` / `succeeded` / `failed` 三者之一，不存在"既非 succeeded 也非 failed、又无法重放"的悬挂状态；
   - 每个清理步骤相互独立（`tracer.fail` 与 `update_status("failed")` 各自独立的 `try/except`），一个失败不得阻止另一个；
   - 必须新增或扩展状态转移矩阵测试（`claim 状态 × draft 是否存在 × trace 是否 attach`），不允许只改实现不加矩阵用例。

2. **不可达代码**
   diff 中不得出现同一代码块 `return` / `raise` 之后的可达语句（例如 `return record` 之后的 `return existing`）。pyright 的 `reportUnreachable` 会拦这类死代码，评审也要肉眼复核新 diff。

3. **跨边界只依赖端口/契约**
   业务模块不得依赖其它业务模块的具体实现；新代码只依赖既有端口（`RetrievalPort` / `GeneratorPort` / Repository 端口）或契约对象。

4. **LoopStrategy 与 Agent 协议变更**
   - 新增 LoopStrategy 必须通过 `Harness.execute` 验证（不直接测试内部实现）；
   - `Agent.run` 签名变更需同步更新所有测试替身（FakeAgent 等），不允许只改实现不改测试；
   - `LoopDecision` 枚举变更需同步更新 `Harness.execute` 的决策分支。

## 流程收敛判据
- 连续 2 轮审计无新增中/高危缺陷、且无新纪律违规 → 视为收敛，**停止审计-修复循环**（改为按需 review）。
- 停止条件只看"新引入"的缺陷；既存已登记的低危/设计限制不计入。
