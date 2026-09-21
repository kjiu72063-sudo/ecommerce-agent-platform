# RAG 评估与调优 + SQLite e2e + B4 Harness 阶段复盘

> 复盘范围：PR #56–#65（RAG eval/tuning）、PR #37–#45（外部适配器）、PR #21–#35（B4 Harness）
> 基线：`8cb1d3c`（#55 之前）
> 当前质量基线：273 passed, 4 skipped
> 更新时间：2026-09-21

---

## 1. 本阶段完成了什么

### 1.1 外部适配器（PR #37–#45）
- **Slice 1**（#35/#36）：抽象 `RetrievalPort`/`GeneratorPort`，现有确定性实现作为默认
- **Slice 2**（#37/#38）：OpenAI 兼容 `GeneratorPort` 适配器（同步 HTTP、超时/重试、密钥装配）
- **Slice 3**（#45）：`ExternalRetrieval` 适配器 + transport 注入 + 失败降级
- **Slice 4**（#46–#49）：Qdrant 向量检索 + 确定性 embedding 兜底 + UUID point id 修复
- **Hybrid RAG**（#47–#51）：Milvus 稠密 + BM25 词法 + RRF 融合 + cross-encoder reranker

### 1.2 RAG 评估与调优（PR #52–#65）
- **评估框架**（#52）：可量化的检索评估（MRR/hit@k/precision@k），真实语义 embedding
- **Reranker**（#53）：cross-encoder reranker for hybrid retrieval
- **调参**（#54/#55）：sweep hybrid retrieval params（pool/RRF/reranker）
- **生成评估**（#57–#59）：LLM-as-judge faithfulness eval + 对抗 guard（evidence-insufficient/severed）
- **Corrective-RAG**（#62）：低置信度检索自动升级为人工复核
- **规模化**（#60/#63）：stress-test "1.0" scores + 100+ 真实查询 golden 数据集
- **SQLite e2e**（#64）：`runtime.create_sqlite()` 端到端持久化闭环
- **基线改善**（#65）：MRR=0.9955，验证检索质量

### 1.3 B4 Harness（PR #21–#35）
- `Harness` + `Loop` + `Agent` 协议 + `PresaleAgent` 适配器
- Loop 支持 `continue`/`finalize`/`need_human`，受 `max_steps=5` 有界约束
- Harness SQLite 跨实例重放一致
- `accept` 与技术终态分离

---

## 2. 哪些决策减少了返工

### 2.1 逐环替换策略
先接 LLM 生成环（不改变证据形状）→ 验证最小闭环 → 再接外部检索环。每一步只替换一个外部依赖，出问题可快速定位。

### 2.2 端口-适配器双实现验证
每个端口保持 InMemory + SQLite 两个适配器，验证 seam 真实。`create_sqlite` 装配一次性组装所有 SQLite 端口，runner 代码零改动。

### 2.3 确定性 embedding 兜底
外部 embedding 不可用时自动降级为确定性 embedding，避免 CI 和开发环境因外部服务不可用而阻塞。

### 2.4 评估先行
先建评估框架（MRR/hit@k），再做调参。避免盲目优化没有量化指标支撑。最终 MRR 从初跑 0.936 改善到 0.9955。

---

## 3. 实现阶段暴露的问题与根因

### 3.1 `generation_eval.py` 模块级耦合具体适配器（MEDIUM）
模块级 `from .openai_generator import OpenAICompatibleGenerator, default_transport`，导致 eval 函数无法在不加载 OpenAI 适配器的情况下使用，尽管核心函数已是 duck-typed（接受 `Any`）。

**根因**：`main()` 作为二级 composition root 直接组装适配器，未复用 `runtime.py` 的 composition root。

**处理决定**：列入修复项（P1），将 import 移入 `main()` 懒加载。

### 3.2 `scripts/sweep_retrieval.py` 深度耦合 7 个具体适配器类（HIGH）
脚本直接 import `BM25Index`、`MilvusDense`、`hybrid_transport` 等内部组件，绕过端口契约组装变体。

**根因**：sweep 需要在不同超参数下重建适配器，现有工厂函数不支持参数化。

**处理决定**：列入修复项（P2），提取 `hybrid_retriever_from_params()` 参数化工厂。

### 3.3 SQLite e2e 缺少故障注入测试（MEDIUM）
`test_sqlite_end_to_end.py` 只覆盖 happy path。所有现有失败注入用 InMemory mock，未验证 `sqlite3.OperationalError` 等真实 SQLite 异常下的清理行为。

**根因**：e2e 测试聚焦于"正确路径跨实例一致性"，故障注入留给了单元测试层（已用 mock 覆盖）。但 SQLite adapter 的异常类型与 mock 不同。

**处理决定**：列入修复项（P2），补充 SQLite adapter 故障注入测试。

### 3.4 生成评估重复 composition root（MEDIUM）
`generation_eval.py:530` 重复组装 `OpenAICompatibleGenerator`，与 `runtime.py:openai_generator_from_env()` 逻辑重叠。

**根因**：评估脚本独立开发，未接入统一装配层。

**处理决定**：列入修复项（P1），复用 `runtime.py` 或接受 `GeneratorPort` 参数。

### 3.5 README 基线数字漂移（已修复）
README 写 251 passed，实际 273。违反台账规则"README 以台账为准"。

**根因**：PR #64/#65 合并时未同步更新 README。

**处理决定**：已在 PR #66 修复（`5851d36`），已合并。

---

## 4. 评审发现汇总

### Rule 1：幂等/失败清理不变量
| 严重度 | 数量 | 结论 |
|---|---|---|
| HIGH | 0 | — |
| MEDIUM | 1 | SQLite 故障注入测试缺失 |
| LOW | 3 | 均为设计正确、测试已覆盖的观察项 |

状态矩阵 16 种场景全覆盖，无悬挂状态。

### Rule 2：不可达代码
| 严重度 | 数量 |
|---|---|
| 任何 | **0** |

全部通过，零死代码。

### Rule 3：跨边界端口依赖
| 严重度 | 数量 | 位置 |
|---|---|---|
| HIGH | 1 | `scripts/sweep_retrieval.py`（7 个具体导入） |
| MEDIUM | 3 | `generation_eval.py:30`, `generation_eval.py:530`, `generate_realistic_golden.py:23` |
| LOW | 3 | `eval_regression.py:20`, `hybrid_retrieval.py` 层内复用（可接受） |

`runner.py` 和 `runtime.py` 干净，应作为其他文件的参考模式。

---

## 5. 修复行动项

| 优先级 | 行动 | 对应 Finding |
|---|---|---|
| P1 | `generation_eval.py:30` — `OpenAICompatibleGenerator`/`default_transport` import 移入 `main()` 懒加载 | Rule 3 MEDIUM |
| P1 | `generation_eval.py:530` — 复用 `runtime.py` composition root 或接受 `GeneratorPort` 参数 | Rule 3 MEDIUM |
| P2 | `scripts/sweep_retrieval.py` — 提取 `hybrid_retriever_from_params()` 参数化工厂 | Rule 3 HIGH |
| P2 | `test_sqlite_end_to_end.py` — 补充 SQLite adapter 故障注入测试 | Rule 1 MEDIUM |
| P3 | `scripts/generate_realistic_golden.py:23` — `default_transport` 改为通过 composition root 获取 | Rule 3 MEDIUM |
| P3 | `scripts/eval_regression.py:20` — 复用 `runtime.py` 入口 | Rule 3 LOW |

---

## 6. 有意的范围取舍

- 评估脚本（`scripts/`）的端口耦合为已知取舍——工具脚本是 composition root，不是业务模块，但应尽量复用 `runtime.py` 的装配
- `generation_eval.py` 的 `except Exception` 宽捕获是评估循环的设计选择（per-question 故障不阻塞全量评估），有 `# noqa: BLE001` 注释
- Hybrid RAG 的层内适配器组合（`hybrid_retrieval.py` 引用 `external_retrieval.py`）属于基础设施工厂模式，不违反业务边界
- `Loop.CONTINUE` 分支结构性存在但不触发——这是 B5 的领地，不在当前 Harness 最小闭环范围内

---

## 7. 下一阶段门禁

进入下一步前必须保持：

```bash
uv run pytest -q               # 273+ passed
uv run ruff check src
uv run ruff format --check src
uv run pyright
```

以及既有不变量：
- 幂等/租户隔离/30 天保留/Corrective-RAG escalation 行为不变
- InMemory 与 SQLite 两套适配器下主路径一致
- MRR ≥ 0.99（golden 数据集 100+ 查询）

---

## 8. 下一阶段方向

按路线图当前位置：

```text
B0 ✅ → B1 ✅ → B2 ✅ → B3 ✅ → 外部适配器 ✅ → B4 Harness ✅
                                                          ↓
                                              B5 Loop 引擎（推荐优先）
```

推荐顺序：
1. 修复本 retro 行动项（P1 + P2）
2. `/purpose-first-system-design` → B5 Loop 引擎（明确多步循环策略边界）
3. `/domain-modeling` → `/to-spec` → `/to-tickets` → 进入 B5 实现
