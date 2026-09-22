# AGENTS.md

导航指针（按需加载，短小精炼）。权威来源见下，正文在此不重复。

## 仓库里的权威文档
- 领域词汇表：`CONTEXT.md`（纯术语，无实现细节）。
- 领域决策：`docs/domain-decisions.md`（D-xx 编号决策）。
- **测试数当前基线**：`开发文档/09-质量基线与门禁台账.md`（其余 README 各处数字以此为准）。
- 设计/规格：`docs/spec-b5-loop-engine.md`、`docs/spec-b6-business-agent.md`、`docs/spec-b4b6-harness-loop.md`。
- 评估框架：`src/presale/adapters/eval_framework.py`（`presale-eval` CLI，复用 retrieval_eval/generation_eval）。
- 评审规则：`CODING_STANDARDS.md`（评审 agent 读取）。
- 开发流程/门禁/分支 PR 规范：`CONTRIBUTING.md`。
- 复盘记录：`docs/retro-*.md`（每个阶段完成后更新）。

## 关键模块
- presale 业务流：`src/presale/runner.py`（注意其幂等状态机改动的评审规则）。
- 可复用 agent 运行时：`src/agent_runtime/`（Harness/Loop/Agent）。
- 持久化适配器：`src/presale/adapters/sqlite.py` + `postgres.py`（同一端口集，双适配器）。
- 业务 Agent 实例：`src/review_agent/`（ReviewAnalyzerAgent 模板）。