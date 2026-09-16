# AGENTS.md

导航指针（按需加载，短小精炼）。权威来源见下，正文在此不重复。

## 仓库里的权威文档
- 领域词汇表：`CONTEXT.md`（纯术语，无实现细节）。
- 领域决策：`docs/domain-decisions.md`（D-xx 编号决策）。
- **测试数当前基线**：`开发文档/09-质量基线与门禁台账.md`（其余 README 各处数字以此为准）。
- 设计/规格：`开发文档/10-外部适配器阶段设计.md`、`开发文档/11-外部适配器端口契约.md`、`docs/spec-b4b6-harness-loop.md`。
- 评审规则：`CODING_STANDARDS.md`（评审 agent 读取）。
- 开发流程/门禁/分支 PR 规范：`CONTRIBUTING.md`。

## 关键模块
- presale 业务流：`src/presale/runner.py`（注意其幂等状态机改动的评审规则）。
- 可复用 agent 运行时：`src/agent_runtime/`（Harness/Loop/Agent）。