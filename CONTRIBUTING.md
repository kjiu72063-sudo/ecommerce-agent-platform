# 贡献指南（CONTRIBUTING）

本项目采用 **staged 工程化流程**：任何业务代码都不得"想清楚前直接写"。每个阶段有明确入口、退出条件与产出物，门禁在合并前强制执行。本文件把这条链路固化成团队可一致重跑的标准。

## 1. 开发流程（阶段化）

开发严格按下列 skill 阶段推进；**上一阶段未通过 gate，不得进入下一阶段**。每个阶段结束时做一次小型回顾（`/retro`），把决策记入 `开发文档/00-项目总览与开发路线图.md` 的决策日志。

| 阶段 | Skill | 入口 | 退出条件 / 产出物 |
|---|---|---|---|
| 系统设计 | `/purpose-first-system-design` | 收到新需求 | 明确首要用户、首要目标与目标路径；写入设计文档 |
| 领域建模 | `/domain-modeling` | 设计获批 | 边界、实体、聚合与不变量；`domain-decisions.md` |
| 规格 | `/to-spec` | 领域建模通过 | 可验收的规格文档（错误码/状态机/契约） |
| 拆票 | `/to-tickets` | 规格定稿 | 可独立验收的 ticket 列表 |
| 原型 | `/prototype` | 票已拆 | 可运行的最小路径（不落生产契约） |
| 测试驱动 | `/tdd` | 原型确认 | 每个 ticket 先写失败测试再实现；红→绿→重构 |
| 规格实现 | `/implement-spec` | tdd 绿 | 实现满足规格并全绿 |
| 代码评审 | `/code-review` | 实现全绿 | 评审无阻塞项；发现阻塞先修再评 |
| 复盘 | `/retro` | 评审通过 | 阶段复盘记录，沉淀经验与待办 |

> 决策规则：能由实现者自己确认的决策自行决定；无法确认的，向决策者弹选项后再定。

## 2. 门禁（Gate）

合并到 `main` 前必须通过以下全部检查。**CI 在 `main` 与每个 PR 上强制执行前四条，并校验质量台账顶行与实测测试数一致**（ruff check/format src + pyright + pytest + `scripts/check_baseline.py`）；`pre-commit` 是本地便捷钩子，非 CI 强制：

```bash
uv run pytest -q            # 全量测试（tests/）          <- CI 强制
uv run ruff check src       # lint（仅 src 为门禁范围）   <- CI 强制
uv run ruff format --check src                          <- CI 强制
uv run pyright              # 类型（src/presale+agent_runtime）<- CI 强制
uv run pre-commit run --all-files   # 本地钩子，非 CI 强制
python scripts/check_baseline.py            # CI 强制：台账顶行 == pytest 通过数
```

另有两个不阻塞语法门禁、但阻断合并的集成 job：

- **检索回归**：Milvus job 用确定性嵌入跑 `presale-eval --mode retrieval`，再 `--compare --fail-on-regression` 对照 `tests/fixtures/retrieval_golden_snapshot.json`。排序或召回回退即失败。
- **PostgreSQL**：`postgres-integration` job 拉起 `postgres:15-alpine`，设置 `PRESALE_PG_DSN` 后跑 `tests/b1/test_postgres_integration.py`。未设置该变量时，这组测试在本地全量 pytest 中跳过。

- **契约优先**：实现必须遵守 B0 契约模型、JSON Schema 与状态机。
- **测试先行**：先补测试再改实现；覆盖错误路径与跨租户/并发等安全语义。
- **门禁纪律（平台强制）**：仓库已公开，`main` 启用 branch protection——直接推送/强制推送/删除被禁（含管理员）、必须走 PR、要求 `lint + format + typecheck + test` CI 通过、强制线性历史。因此合并纪律由平台硬性执行，不再是人工核对。合并前仍请确认该 PR 的 CI `pass`；`pending/queued` 时等待，未通过不能合并（平台会拦截）。
- **已知例外（历史）**：2026-09-13 PR #9/#10 曾因免费层 runner 排队过久、在 CI 尚未跑完时被合并（事后 CI 均通过）。这是 branch protection 启用前的一次纪律记录，现在平台已无法再出现该情形。

## 3. 分支、提交与 PR

- 分支命名：`feature/<主题>`（例：`feature/presale-governance-gaps`）。
- 提交信息遵循 Conventional Commits：`feat:` `fix:` `docs:` `refactor:` `test:`。
- 合并方式：`main` 使用 **squash merge**，保持主历史线性。
- 流程：切分支 → 改代码 + 补测试 → 本地 gate 全绿 → 推送 → 建 PR → 等 CI 通过 → 合并 → 删分支。
- 未走 PR 的本地堆积不算"已交付"：功能只有在合并进 `main` 后才视为完成。

## 4. 维护/后台任务

后台维护操作（当前为 30 天保留归档）有两个真实调度入口，二选一或并用：

- **HTTP 端点**（供 cron/APScheduler/k8s CronJob 触发）：
  `POST /api/v1/presale/maintenance/retention/archive?tenant_id=<租户>&database=<sqlite路径>`
- **CLI**：`uv run python -m presale.cli --archive-expired --db <sqlite路径> --tenant <租户>`

两者共用 `src/presale/maintenance.archive_expired_sqlite`，行为一致。详见 `开发文档/09-质量基线与门禁台账.md`。

## 5. 本地边界

默认运行形态是单进程本地内存/SQLite。Harness、Loop 与两个业务 Agent 已交付；PostgreSQL 只覆盖 presale 六个端口，不承诺消息队列、分布式事务或多进程一致性。
