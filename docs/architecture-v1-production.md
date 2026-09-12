# V1 售前商品问答 —— 生产化架构设计

> 状态：架构设计（生产化阶段）
> 依据：V1 已跑通的内存原型、docs/domain-model.md、docs/spec-v1-presale-product-qa.md、docs/retro-v1-presale-qa.md
> 更新时间：2026-09-08
> 原则：本阶段不写业务实现代码，只确定模块边界、持久化端口和依赖方向。

## 1. 目标

把已证明的 V1 tracer bullet 从"内存 + 确定性替代实现"演进到"可持久化、可替换实现、依赖方向清晰"的生产化形状，同时不扩大业务范围（仍是只读、带依据、可转人工的售前商品问答）。

```text
ProductQuestion
→ 确定性/真实知识检索
→ EvidenceItem
→ ContextPackage
→ AnswerDraft
→ HumanDisposition
→ 可持久化 run trace 追溯
```

## 2. 核心判断：presale 是业务模块，B0–B3 是平台模块

V1 已经证明：`ProductQuestion`、`EvidenceItem`、`AnswerDraft`、`HumanDisposition` 是**业务对象**，不属于 B0 定义的平台资源（AgentSpec、Task、AgentRun 等）。

因此生产化架构的核心不是"把业务对象塞进 B0 模型"，而是：

- **业务侧**：定义并持久化自己的业务对象；
- **平台侧**：作为可替换的服务被 presale 依赖，而非 presale 反向侵入平台。

这条判断决定了下面的模块边界和端口设计。

## 3. 模块边界

### 3.1 稳定边界（业务契约，不随实现变化）

```text
presale.contracts    ProductQuestion / AnswerDraft / EvidenceRef
presale.knowledge    KnowledgeSource / EvidenceItem / RetrievalStatus
presale.context      ContextPackage 组装入口（委托 B3）
presale.answer       AnswerDraft 生成入口
presale.disposition  HumanDisposition 入口
presale.runner       PresaleQaRunner 应用门面
presale.trace        PresaleRunTrace 追溯
```

这些是业务接口，生产化阶段应保持不变（或仅做兼容性扩展），它们定义了什么在业务上成立。

### 3.2 可替换实现（V1 用内存/确定性，生产化可替换）

- **知识检索器**：`DeterministicKnowledgeRetriever` → 可替换为真实商品中心/向量检索适配器；
- **回答生成器**：`PresaleAnswerGenerator` → 可替换为真实模型适配器；
- **持久化**：当前 `PresaleRunTracer`/`AnswerDispositionService` 内部 `dict` → 可替换为 B2/数据库适配器。

### 3.3 平台接入（现有 B0–B3 的定位）

| 平台模块 | presale 如何接入 | 备注 |
|---|---|---|
| B0 契约 | `contracts.py`/`context.py` 引用 B0 模型（ObjectRef、ContextPackage） | presale 业务对象不在 B0 内 |
| B1 能力注册 | presale 读取 Agent/Prompt/ContextPolicy/PermissionProfile 定义 | 当前 runner 用常量快照，生产化改为从 B1 读取冻结版本 |
| B2 状态与持久化 | presale 的 run trace / disposition 持久化端口接入 | 见第 5 节 |
| B3 Context | `presale.context` 委托 `context.context_service` | 已接入，作为可替换内部实现 |

## 4. 依赖方向

必须遵守：

```text
presale（业务）  --依赖-->  B0/B1/B2/B3（平台）  --依赖-->  DB / 外部系统 / 模型适配器
```

禁止反向依赖：

- B0/B1/B2/B3 **不得** import presale 业务对象；
- presale 只能通过平台已暴露的接口（端口/契约）调用平台，不能依赖平台内部实现细节。

具体约束：

1. `presale.runner` 不得直接 new `InMemoryXRepository` 并绕过端口——应通过注入的持久化端口操作；
2. presale 业务对象（ProductQuestion/AnswerDraft）不得被要求迁入 B0；
3. B3 Context 只负责组装与校验，不读取 presale 业务真值来源。

## 5. 持久化端口（核心决策）

当前内存 dict 是隐藏实现。生产化需要为 presale 业务对象定义**端口**（端口 = 可被内存/数据库/其他适配器实现的接口），而不是直接用 SQL。

### 5.1 端口清单

```text
ProductQuestionRepository
    save(question) / get(id, tenant) / find_by_idempotency(tenant, key)

EvidenceRepository
    save_evidence(run_ref, items) / get_by_run(run_ref)

AnswerDraftRepository
    save(draft) / get_by_run(run_ref)

DispositionRepository
    save(record) / get_by_answer(answer_id)

RunTraceRepository
    save(trace) / get(run_ref, tenant) / mark_archived(run_ref, tenant)
```

每个端口一个接口，接口承担"调用方必须知道的一切"：方法签名、不变量、错误模式、租户边界。

### 5.2 与 B2 的关系

B2 已提供 `TaskRepository`/`RunRepository`/`EventRepository` 的 async 端口，其对象结构是 B0 的 Task/AgentRun。

生产化阶段的选择：

- **B2 端口保留**，用于承载平台级 Task/AgentRun/Event 生命周期；
- presale 业务对象（ProductQuestion/AnswerDraft/Disposition/Trace）**不**强行塞入 B2 的 B0 结构，而是新增 presale 自己的端口；
- 若未来需要把 presale 运行纳入统一事件审计，可在端口适配层把关键阶段映射为 B2 Event，但这是可选演进，不是本阶段前置。

### 5.3 适配器

为每个端口提供两个适配器以验证 seam 真实：

```text
InMemory<Port>Repository      → 复用现有内存实现
Sqlite<Port>Repository        → 生产化初始持久化（本地 SQLite 闭环）
```

"一个适配器意味着假设的 seam，两个适配器意味着真实的 seam" —— 用 InMemory + SQLite 验证每个端口都是真实 seam，且保持 V1 的本地闭环原则（不引入 PostgreSQL/分布式，除非进入下一阶段）。

### 5.4 保留策略归属

`RunTraceRepository` 负责 `mark_archived`。到期清理逻辑（`archive_expired`）保留在业务侧（如 `RetentionService`），通过端口调用仓储标记，不在仓储内自行决定业务策略。这样保留策略仍是业务规则，可测试、可替换。

## 6. 持久化对象形态

生产化持久化的对象应为**已验证的业务模型**（Pydantic model），而非裸 dict：

```text
当前（内存 dict 隐藏）          →  生产化（端口 + Pydantic 模型）
ProductQuestion 内存            →  ProductQuestion model（已有）
PresaleRunTracer._traces dict  →  PresaleRunTrace model + RunTraceRepository
AnswerDispositionService dict  →  HumanDispositionRecord model + DispositionRepository
```

这与 Standards 审查中指出的"裸 dict 引用"问题一致，一并解决：`run_ref`/`policy_ref`/`artifact_ref` 应改为明确的引用模型或复用 B0 `ObjectRef`/`ResourceRef`。

## 7. 需要从内存演进为端口的现有对象

| 当前实现 | 现状 | 生产化动作 |
|---|---|---|
| `PresaleRunTracer` | 内部 dict | 提取 `RunTraceRepository` 端口；tracer 成为协调器，依赖注入 |
| `AnswerDispositionService` | 内部 dict | 提取 `DispositionRepository`；保留业务处置规则 |
| `PresaleQaRunner` | 内存 runner | 依赖注入各端口；成为应用门面，不再自建持久化 |
| `PresaleAnswerGenerator` | 模板生成 | 保持为可替换实现；定义生成器接口，真实模型做适配器 |
| `DeterministicKnowledgeRetriever` | 内存检索 | 保持为可替换实现；定义检索器接口 |

## 8. 生产化阶段明确不做

- 不接入真实模型（定义生成器接口，保留模拟适配器即可）；
- 不接入真实商品中心/向量检索（定义检索器接口即可）；
- 不引入 PostgreSQL / 分布式事件 / 消息队列（保持本地 SQLite 闭环）；
- 不做完整 B4 权限引擎 / 容器沙箱；
- 不做消费者消息发送；
- 不做多 Agent / B5 Loop；
- 不把 presale 业务对象迁入 B0；
- 不做大范围领域重构——只做"端口化 + 适配器"的结构演进，保持业务语义不变。

## 9. 演进顺序与门禁

### 9.1 演进顺序

1. ✅ **定义端口接口**：先给 ProductQuestion/Evidence/AnswerDraft/Disposition/Trace 各定端口与 Pydantic 对象；
2. ✅ **实现 InMemory + SQLite 适配器**：每个端口两个适配器，验证 seam 真实；
3. ✅ **改造 runner/tracer/disposition 为依赖注入**：从"内部 new dict"改为注入端口（含 async 转换）；
4. ✅ **接入保留策略**：RetentionService 通过端口 mark_archived；
5. ✅ **让 presale 依赖平台冻结定义**：从 B1 读取 Agent/Prompt/Policy 版本，而非常量；
6. **跑通端到端**：内存与 SQLite 两套适配器下主路径一致；
7. **再次 code-review**，再决定是否进入真实外部服务/生产数据库阶段。

> 当前进度：1–5 已完成。Step 5 通过 `DefinitionSource`/`B1DefinitionSource` 读取租户范围内 active 的 AgentSpec、PromptPackage、ContextPolicy，并在每次运行中冻结版本与摘要。

### 9.2 门禁

每一步后必须保持：

```bash
uv run pytest -q
uv run ruff check src
uv run ruff format --check src
uv run pre-commit run --all-files
```

以及 V1 不变量：

- 主路径可运行且确定性；
- 无证据/冲突/跨租户/超预算/失败都有明确出口；
- run trace 查询带 tenant_id；
- 幂等不重复创建；
- 只读无写副作用；
- AnswerDraft 带证据或 need_human=true；
- 内存与 SQLite 行为一致。

## 10. 数据流（见 data-flow 文档）

一次问答在持久化端口下：

```text
runner.ask(question)
 → question_repo.save(question)
 → retriever.retrieve → evidence_repo.save_evidence(run_ref, items)
 → context_builder → context_package
 → answer_generator.generate → answer_repo.save(draft)
 → trace_repo.save(trace)
```

处置时：

```text
runner.accept/edit/escalate/discard
 → disposition_repo.save(record)
 → trace_repo.mark_disposition(run_ref, state)
```

到期时：

```text
RetentionService.archive_expired(tenant)
 → trace_repo.mark_archived(run_ref, tenant)   # 保留留痕，不物理删除
```
