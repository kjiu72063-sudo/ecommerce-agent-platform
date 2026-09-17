# 电商 AI Agent 生态系统

这是一个已经开发到 B3 阶段的多智能体平台基础项目，不是从零开始的生产系统。当前内容包含契约资产、基础设施原型、本地 SQLite 闭环、测试、实现文档和教学/历史材料。

## 当前阶段

| 阶段 | 内容 | 当前状态 |
|---|---|---|
| B0 | Agent Platform 契约、JSON Schema、Pydantic 模型、状态机和示例 | 已纳入根级包；发布收敛仍在进行 |
| B1 | 能力注册中心、依赖解析、内存/SQLite 仓储、FastAPI 原型 | 本地闭环；未承诺生产部署 |
| B1 售前 QA（V1 切片） | 确定性检索→上下文→回答→处置 的只读售前问答；租户隔离、幂等状态机、SQLite 持久化、30 天保留、B1 定义装配 | 已交付 `src/presale` |
| B2 | Task、AgentRun、Event、Checkpoint 和 SQLite 持久化 | 本地闭环；未承诺分布式一致性 |
| B3 | 确定性 Context 组装、去重、排序和预算校验 | 最小闭环 |
| B4–B6 | Harness、Loop、业务 Agent | 尚未实现 |

## 环境初始化

要求 Python 3.11–3.13 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --extra test --extra quality
```

所有命令从项目根目录执行，不需要手工设置 `PYTHONPATH`。

## 测试与质量门禁

```bash
uv run pytest -q            # CI 强制
uv run ruff check src       # CI 强制
uv run ruff format --check src                          # CI 强制
uv run pyright              # CI 强制（src/presale + src/agent_runtime）
uv run pre-commit run --all-files   # 本地钩子，非 CI 强制
```

当前基线：全量测试 242 passed（以 `开发文档/09-质量基线与门禁台账.md` 的带日期台账为准）。CI 通过 GitHub Actions（`.github/workflows/ci.yml`）在 `main` 与每个 PR 上运行门禁（ruff check/format src + pyright + pytest）并带 `concurrency` 取消旧 run。仓库已公开，`main` 启用分支保护：直接/强制推送与删除被禁（含管理员）、必须走 PR、要求 CI 通过、强制线性历史——合并纪律由平台强制。测试规范入口位于 `tests/b1`、`tests/b2`、`tests/b3`；旧 B 目录中的测试保留作阶段迁移参考，不再作为根级默认收集入口。

## 目录边界

```text
src/
├── agent_platform_contracts/  # B0 唯一运行时包和契约资产
├── registry/                  # B1 能力注册中心
├── runtime/                   # B2 状态与持久化
├── context/                   # B3 Context 引擎
└── presale/                   # B1 售前商品问答 V1 切片（幂等/SQLite/生产装配）

tests/                         # 根级规范测试
B0-契约基础/contracts/          # B0 契约包来源与交付材料
B0-契约基础/从零实现/            # 历史/教学实现，不是运行时权威来源
开发文档/                       # 设计、实现和阶段指南
```

`B0-契约基础/contracts/...` 中的版本化契约包是当前权威来源；根级 `src/agent_platform_contracts` 是其 monorepo 安装布局。契约资产通过 `agent_platform_contracts.assets_api.asset_path()` 访问，不应依赖源码绝对路径。

## 工程约束

- 契约优先：实现必须遵守 B0 模型、Schema 和状态机。
- 测试驱动：变更先补测试，再修改实现。
- 阶段隔离：B4 之前不引入模型调用、完整 Harness 或 Loop 策略。
- 本地边界：当前只承诺单进程本地内存/SQLite 闭环，不承诺 PostgreSQL、消息队列、分布式事务或多进程一致性。
- 不把 `B0-契约基础/从零实现/` 当作新代码依赖；它用于教学、历史追溯和对照。

## 贡献与维护

- 开发流程、门禁与分支/PR 规范见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
- 后台维护（30 天保留归档）的调度入口（HTTP 端点 + CLI）见 [`开发文档/09-质量基线与门禁台账.md`](开发文档/09-质量基线与门禁台账.md)。

