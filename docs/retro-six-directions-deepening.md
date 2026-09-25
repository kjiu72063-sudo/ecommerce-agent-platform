# 六方向深化阶段复盘（C 类型修复 / E 真实LLM / B PostgreSQL / D 新Agent / F 评估框架）

> 复盘范围：六方向深化（PR #82–#106）
> 时间跨度：2026-09-21 ~ 2026-09-22
> 基线：251 passed → 334 passed（+83 测试）
> PR：#82/#83（A retro+标准）、#85（C）、#89/#91（E）、#96（B）、#101（D）、#105/#106（F）

---

## 1. 本阶段完成了什么

| 方向 | PR | 交付物 |
|---|---|---|
| A 复盘 | #82/#83 | B5/B6 retro + CODING_STANDARDS 新增 Rule 4 |
| C 类型修复 | #85 | registry/ 26 + runtime/ 13 = 39 个 pyright 错误清零，纳入 pyright include |
| E 真实LLM | #89/#91 | create_openai_agent 失败路径 + create_sqlite 全装配/幂等/失败测试 |
| B PostgreSQL | #96 | PostgresPresaleStore + 6 个 PostgreSQL 适配器 + create_postgres() + docker-compose |
| D 新Agent | #101 | ReviewAnalyzerAgent（retrieve_knowledge + analyze_review 双工具） |
| F 评估框架 | #105/#106 | presale-eval 统一入口 + --output/--compare + compare_reports 纯函数 |

---

## 2. 哪些决策减少了返工

### 2.1 目的优先设计逐个收敛
六个方向均先过 `/purpose-first-system-design` 门禁，明确"做什么/不做什么"，避免过度工程：
- E 收敛为"复用既有 OpenAICompatibleGenerator + 集成测试"，而非重写 LLM 适配器
- B 明确"只做 presale 6 端口，不迁移 runtime/registry"，把范围钉死
- F 明确"复用 retrieval_eval/generation_eval，不新增指标"，避免第四套割裂工具

### 2.2 端口-适配器模式让 PostgreSQL 落地干净
B 阶段完全复用 presale 端口（ports.py），6 个 Postgres 适配器与 SQLite 适配器平级，零业务层改动——验证了"两个适配器才是真 seam"的判断。

### 2.3 基线同步脚本提前就位
`check_baseline.py` 在 E 阶段后加入 CI，后续 D/F 阶段每次合并且测试数变化都会被 CI 拦截（出现过 2 次 ledger 漂移被自动发现）。

---

## 3. 实现阶段暴露的问题与根因

### 3.1 FakeRetriever 需返回 golden 期望的 locator（F）
测试 mrr==1.0 失败，根因是 FakeRetriever 返回固定 locator，与 golden 的 expected 不匹配。修正为按 query 映射 expected locator。
**教训**：评估类测试的 fake 必须与 golden 集对齐，否则测的是假行为。

### 3.2 rank 丢失被误判为 improved（F-02 真 bug）
`compare_reports` 初版把"rank 从有到 None"（recall 丢失）归为 improved，应归 regressed。被 F-02 的红测试抓住修正。
**教训**：对比逻辑边界（有→无 / 无→有）必须用测试矩阵钉死，不能靠直觉。

**后续（PR #127，2026-09-24）**：同一 `compare_reports` 还有一个更隐蔽的假绿——检索报告字段是 `per_query`（行内 query 为裸文本）而快照键是 `tenant/product::query`，`_as_per_question` 只读 `per_question` 导致 fall-through，**`regressed` 恒为 0，检索回退门禁从未真正生效**。由 #126 的 CI 失败产物核验暴露；修复为 `_row_key` 复合键 + 同时读 `per_query` + skip 聚合 dict。
**教训**：门禁自身的"绿"也要有用例证明它能变红——仅测"无回退时 exit 0"不够，必须有"有回退时 exit 1"的红测试对准真实报告字段结构。

### 3.3 本地缺 rank-bm25 导致 3 个 hybrid 测试假失败（F）
本地 `uv sync` 未装 test extra，`test_hybrid_retrieval` 3 例失败，CI 却通过（CI 装全依赖）。最初误判为"预存失败"，实为本地环境问题。
**教训**：CI 通过但本地失败时，先核对依赖同步（`uv sync --extra test`），不要默认"预存失败"。

### 3.4 asyncpg JSONB 返回 str 而非 dict（B）
Postgres 适配器初版 `model_validate(row["content"])` 在 asyncpg 返回 JSONB 字符串时报错，需 `_parse_jsonb` 统一处理 str/dict。
**教训**：asyncpg JSONB 的类型行为与 sqlite3 不同，跨数据库适配器需显式序列化契约。

### 3.5 AnswerDraft 合约约束新 Agent（D）
ReviewAnalyzerAgent 初版构造"无证据但 need_human=False"的 draft 被合约拦截（answers without evidence must require human review）。修正为分析类回答始终 need_human。
**教训**：领域不变量（evidence↔need_human）是跨 Agent 的硬约束，新 Agent 必须遵守而非绕过。

---

## 4. 改进建议

| 严重度 | 建议 | 说明 |
|---|---|---|
| 中 | 本地依赖同步纳入习惯 | 新增依赖/extra 后先 `uv sync --extra test --extra quality` 再跑测试 |

上表中的评估回归门禁、三种剩余 Loop、多 Agent 协作已分别由方向 2（PR #108）、方向 3（PR #109）、方向 4（PR #112）落地，不再作为待办。

---

## 5. 量化总结

| 指标 | 值 |
|---|---|
| PR 数量 | 11（#82–#106） |
| 新增测试 | +83（251 → 334） |
| 新增代码 | eval_framework(≈290 行)、postgres.py(≈400 行)、review_agent(≈130 行)、39 处类型修复 |
| 外部依赖 | asyncpg（postgres extra） |
| 文档 | retro×1、spec×2（B5/B6）、ADR×1、CODING_STANDARDS Rule 4 |
| 清理 | 22+ 残留远程分支 |
