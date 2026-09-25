# 电商 AI Agent 生态系统

这是一个已经开发到 B6 的多智能体平台基础项目，不是从零开始的生产系统。当前内容包含契约资产、可复用执行层、两个业务 Agent、本地 SQLite 与 PostgreSQL 双适配器、测试、实现文档和教学/历史材料。

## 当前阶段

| 阶段 | 内容 | 当前状态 |
|---|---|---|
| B0 | Agent Platform 契约、JSON Schema、Pydantic 模型、状态机和示例 | 已纳入根级包；发布收敛仍在进行 |
| B1 | 能力注册中心、依赖解析、内存/SQLite 仓储、FastAPI 原型 | 本地闭环；未承诺生产部署 |
| B1 售前 QA（V1 切片） | 确定性检索→上下文→回答→处置 的只读售前问答；租户隔离、幂等状态机、SQLite/PostgreSQL 持久化、30 天保留、B1 定义装配 | 已交付 `src/presale` |
| B2 | Task、AgentRun、Event、Checkpoint 和 SQLite 持久化 | 本地闭环；未承诺分布式一致性 |
| B3 | 确定性 Context 组装、去重、排序和预算校验 | 最小闭环 |
| B4–B6 | Harness、5 种 Loop、PresaleAgent、ReviewAnalyzerAgent、AgentCoordinator | 已交付 `src/agent_runtime`、`src/review_agent` |

## 环境初始化

要求 Python 3.11–3.13 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --extra test --extra quality
```

PostgreSQL 适配器与迁移工具额外需要 `uv sync --extra postgres`。所有命令从项目根目录执行，不需要手工设置 `PYTHONPATH`。

## 测试与质量门禁

```bash
uv run pytest -q            # CI 强制
uv run ruff check src       # CI 强制
uv run ruff format --check src                          # CI 强制
uv run pyright              # CI 强制（src/presale + agent_runtime + context + registry + runtime）
uv run pre-commit run --all-files   # 本地钩子，非 CI 强制
```

当前基线以 `开发文档/09-质量基线与门禁台账.md` 顶行为准（2026-09-22：361 passed）。CI 通过 GitHub Actions（`.github/workflows/ci.yml`）在 `main` 与每个 PR 上运行门禁（ruff check/format src + pyright + pytest + 基线同步），并有两个集成 job：Milvus Hybrid 检索回归门禁、PostgreSQL 适配器集成。仓库已公开，`main` 启用分支保护：直接/强制推送与删除被禁（含管理员）、必须走 PR、要求 CI 通过、强制线性历史。测试规范入口位于 `tests/b1`、`tests/b2`、`tests/b3`。

## 快速演示（本地 Web UI）

```bash
docker compose up -d    # 起 Milvus（口语化问题命中的关键；一次性 make index-milvus 建索引）
make demo               # 自动检测 Milvus/LLM 配置并启动
```

浏览器打开 **http://127.0.0.1:8000/** ：选商品 → 点示例问题（或自由输入）→ 看答案、检索状态、引用的商品知识字段与耗时。`make demo` 会检测 Milvus(19530) 自动启用 hybrid 检索、检测 `PRESALE_LLM_*` 决定真实生成或确定性模板（未配也能完整走通）。演示数据在 `src/presale/data/demo_examples.json`（11 个商品 × 2 个口语化问题）。

## 运行 QA 服务

同步售前问答服务（FastAPI）。配置经环境变量（见 `.env.example`）：

```bash
export PRESALE_CATALOG=./catalog.json        # 商品知识（JSON 数组）
# 可选：真实 LLM / 外部检索 / 持久化
export PRESALE_LLM_BASE_URL=...; export PRESALE_LLM_MODEL=...; export PRESALE_LLM_API_KEY=...
# export PRESALE_RETRIEVAL_BASE_URL=...
# export PRESALE_DB=./presale.sqlite3          # SQLite
# export PRESALE_PG_DSN=postgresql://presale:presale@127.0.0.1:5432/presale
presale-qa-api            # 默认 127.0.0.1:8000（可用 PRESALE_QA_HOST/PRESALE_QA_PORT 改）
```

`PRESALE_PG_DSN` 优先于 `PRESALE_DB`。端点：`POST /api/v1/presale/qa`（body: question/product_id/tenant_id/idempotency_key）→ 返回 `format_outcome`（终态 + 答案 + 证据）+ `evidence`（含 locator/content 预览）/`confidence_signal`/`reason_codes`；`POST .../qa/stream`（SSE：evidence→token→done，`session_id` 承载多轮上下文，前端打字机）；`GET .../qa/history?limit=` 最近问答（内存，演示态）；`POST .../qa/feedback`（run_ref + up/down）；`GET .../qa/config`（当前 LLM/检索模式）；`POST /api/v1/review/analyze`（body: text[, product_id] → 情感/关键词，第二业务 Agent）；`GET /api/v1/presale/qa/health`；`GET /api/v1/presale/qa/ready`（配置了 PostgreSQL 时探测连接）。

## 外部检索（Qdrant，可选）

向量库用**本地 Qdrant（Docker）**，embedding 复用 LLM 提供方 `/embeddings` 或独立。步骤（基础设施统一用 `docker compose`/Makefile，见 `deploy/README.md`）：

1. 起服务：`docker compose up -d`（含 Qdrant + Milvus）
2. 索引：

   ```bash
   make index-qdrant   # = PRESALE_QDRANT_URL=http://localhost:6333 PRESALE_EMBEDDING=deterministic presale-index ./catalog.json
   ```

3. 运行 QA 服务时设 `PRESALE_QDRANT_URL` 即用 Qdrant 检索（否则确定性）。

搜索按 `tenant_id`/`product_id` 过滤，跨租户不泄漏；外部检索失败可降级（`RETRIEVAL_DEGRADED`）或显式报错。

## 外部检索（Hybrid RAG，RAG 阶段 1，可选）

稠密（bge-large-zh-v1.5 → Milvus）+ 词法（BM25）+ RRF 融合。见 `开发文档/12-RAG架构方案.md` 与 `deploy/README.md`。

```bash
docker compose up -d            # 起 Milvus（连同 etcd；本仓库用本地文件存储，不依赖 MinIO）
make models                     # 一次性：装 sentence-transformers（本地 bge；可跳过/用确定性）
make index-milvus               # catalog.json → Milvus（可用 PRESALE_EMBEDDING=deterministic 先验证管道）
# 运行 QA 服务时设 PRESALE_MILVUS_URI 即用 Hybrid 检索
```

BM25 为进程内（CJK 字级分词）；Milvus 稠密点按 `tenant_id`/`product_id` 过滤。

## 评估

`presale-eval` 是统一入口（retrieval / generation / end-to-end / compare）。CI 的 Milvus job 用确定性嵌入跑检索，并以 `--compare-batch` + `--fail-on-regression --rank-tolerance 3 --floor-mrr 0.65 --floor-hit1 0.45` 对照 `tests/fixtures/retrieval_golden_snapshot.json`：逐题带内抖动不拦、召回丢失（rank→None）必拦、汇总指标跌破 floor 也拦，检索质量回退不能合并。

## 目录边界

```text
src/
├── agent_platform_contracts/  # B0 唯一运行时包和契约资产
├── registry/                  # B1 能力注册中心（Tool/Skill/Prompt CRUD + 依赖解析）
├── runtime/                   # B2 状态与持久化（Task/AgentRun/Event/Checkpoint）
├── context/                   # B3 Context 引擎（组装/去重/预算校验）
├── agent_runtime/             # Harness、Loop 策略、AgentCoordinator（非 B2 runtime）
├── review_agent/              # ReviewAnalyzerAgent（评价分析，结果须人工审核）
└── presale/                   # 售前商品问答（幂等/SQLite/PostgreSQL/RAG/装配）

tests/                         # 根级规范测试（tests/b1, tests/b2, tests/b3）
B0-契约基础/contracts/          # B0 契约包来源与交付材料
B0-契约基础/从零实现/            # 历史/教学实现，不是运行时权威来源
开发文档/                       # 设计、实现和阶段指南
```

`B0-契约基础/contracts/...` 中的版本化契约包是当前权威来源；根级 `src/agent_platform_contracts` 是其 monorepo 安装布局。契约资产通过 `agent_platform_contracts.assets_api.asset_path()` 访问，不应依赖源码绝对路径。

## 工程约束

- 契约优先：实现必须遵守 B0 模型、Schema 和状态机。
- 测试驱动：变更先补测试，再修改实现。
- 只读边界：V1 工具只做知识查询，不执行改价、下单、库存写入、支付或站外触达。
- 无证据必须转人工；评价分析结果是推荐，始终需要人工审核。
- 本地边界：默认单进程 SQLite。PostgreSQL 适配器已交付并进 CI，但不承诺消息队列、分布式事务或多进程一致性。
- 不把 `B0-契约基础/从零实现/` 当作新代码依赖；它用于教学、历史追溯和对照。

## 贡献与维护

- 开发流程、门禁与分支/PR 规范见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
- 后台维护（30 天保留归档）的调度入口（HTTP 端点 + CLI）见 [`开发文档/09-质量基线与门禁台账.md`](开发文档/09-质量基线与门禁台账.md)。
- SQLite → PostgreSQL 迁移见 [`deploy/README.md`](deploy/README.md) 的 PostgreSQL 一节。
