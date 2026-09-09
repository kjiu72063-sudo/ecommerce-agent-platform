# V1 售前商品问答阶段复盘

> 复盘范围：Ticket 01–09
> 分支：`feature/v1-presale-qa`
> 基线：`b2f1068 chore: establish monorepo engineering baseline`
> 当前质量基线：108 passed；ruff/pre-commit 通过
> 更新时间：2026-09-08

## 1. 本阶段完成了什么

本阶段把已确认的售前商品问答 tracer bullet 从契约推进到可运行的内存原型：

```text
ProductQuestion
→ 确定性商品知识检索
→ EvidenceItem
→ ContextPackage
→ AnswerDraft
→ HumanDisposition
→ run_ref 追溯
```

已完成的 ticket：

- **01**：最小 `ProductQuestion`、`EvidenceRef`、`AnswerDraft` 契约；
- **02**：版本化 JSON/内存商品知识、确定性检索、字段/片段级证据；
- **03**：租户/商品范围过滤、去重、优先级、预算和 B0 `ContextPackage` 校验；
- **04**：确定性 AnswerDraft 生成、无证据/冲突/实时信息转人工；
- **05**：accepted/edited/escalated/discarded 处置和原始草稿留痕；
- **06**：最小 run trace、阶段记录、Context/Answer 关联和租户查询边界；
- **07**：端到端 runner，打通检索→Context→生成→处置注册→追溯；
- **08**：失败出口和只读副作用负向测试；
- **09**：同租户同幂等键的重复提交复用与冲突检测。

## 2. 哪些决策减少了返工

### 2.1 先冻结用户和 tracer bullet

先确认“内部商品运营/客服运营人员”和“只读、带依据、可转人工的售前商品问答”，避免继续扩展直播切片、自媒体运营和通用平台能力。

### 2.2 把业务对象和平台对象分开

明确区分：

```text
ProductQuestion ≠ Task ≠ AgentRun ≠ AnswerDraft
```

这避免了直接把 B0/B2 技术状态当作业务处置状态。

### 2.3 允许原型替代实现

固定 JSON、内存仓储、确定性检索和模拟生成器让主路径先跑通，避免提前接入真实模型、RAG、商品中心和生产副作用。

### 2.4 只读边界前置

先规定不改价、不下单、不写库存、不支付、不发送消息，Ticket 08 才能用探针明确验证，而不是在后续安全阶段被动补洞。

### 2.5 每个 ticket 使用红→绿门禁

TDD 暴露了多个跨组件问题：

- `run_id` 不符合 B0 UUIDv7 资源 ID；
- 同一问题多次运行时 `answer_id` 冲突；
- ContextPackage 返回字典而非校验模型；
- 低优先级证据去重规则不稳定；
- 预算失败被错误归类为生成失败。

如果只做单元实现，这些问题会延迟到端到端阶段才出现。

## 3. 实现阶段暴露的问题与根因

### 3.1 业务契约和 B0 资源契约之间仍有转换缝隙

`run_ref`、`policy_ref`、`artifact_ref` 等输入在 presale 层仍大量使用裸字典。根因是为了快速打通原型，复用了 B0 的最终校验，却没有先建立 V1 的类型化引用对象。

**处理决定：**当前不阻塞 tracer bullet；列入后续重构，优先替换为明确的 DTO/TypedDict/Pydantic 输入契约。

### 3.2 原型运行器没有接入完整 B2 持久化边界

当前 `PresaleQaRunner`、`AnswerDispositionService` 和 `PresaleRunTracer` 使用内存状态。根因是 Ticket 01–09 的目标是验证业务管道，而不是提前完成生产运行时。

**处理决定：**这是已知范围取舍，不在当前阶段偷偷扩展到 PostgreSQL、分布式事件或完整 B2 装配。

### 3.3 失败路径最初缺少业务可解释原因

Context 超预算一度被统一转换为 `ANSWER_GENERATION_FAILED`。根因是 runner 的异常边界过宽。

**已修复：**保留 `TOKEN_BUDGET_EXCEEDED` 等明确原因，并增加回归测试。

### 3.4 检索的精度与召回存在张力

单个中文桥接二字词可能把无关字段误判为证据。根因是 V1 确定性检索只做轻量字符级匹配。

**已修复：**要求至少两个匹配词；不足时转为无证据/人工路径。该策略牺牲部分召回，优先保护“不生成无依据回答”的不变量。

## 4. 当前范围内已修复的真实缺陷

### 4.1 跨租户 run trace 查询

审查发现 `get_trace(run_ref)` 可以不带租户读取。现在：

- 查询必须显式提供 `tenant_id`；
- 缺失租户抛 `TENANT_ID_REQUIRED`；
- 租户不匹配抛 `OUT_OF_SCOPE`；
- 新增跨租户回归测试。

### 4.2 检索单桥接词误判证据

现在要求至少两个匹配词，避免“季使”一类跨词边界的单词误命中。

### 4.3 失败原因被笼统吞并

Context 预算错误不再被伪装成生成失败，失败原因会进入 trace 和异常结果。

### 4.4 重复运行导致 AnswerDraft ID 冲突

`answer_id` 改为基于 run id 唯一，支持同一问题多次运行而不与处置注册冲突。

## 5. 审查发现中属于后续 ticket 或后续阶段的问题

### 5.1 Ticket 10：30 天保留

当前尚未实现过期和清理。它应作为独立 Ticket 10 完成，不能通过在 Ticket 01–09 中暗中增加清理逻辑来扩大范围。

### 5.2 Ticket 11：最小运行入口

当前 runner 可被测试调用，但尚未提供面向人工复核的一条命令或稳定 CLI。它属于 Ticket 11。

### 5.3 完整 PermissionDecision / PermissionProfile

当前实现了租户和商品范围过滤，以及只读负向测试，但没有完整权限决策引擎、RBAC/ABAC 或 B4 Harness。这是规格明确暂缓的能力，不应在 Ticket 08 之后悄悄扩张。

### 5.4 B2 Task/AgentRun/Event 生产持久化

当前 trace 是 presale 原型聚合记录，不是完整 SQLite/PostgreSQL B2 runtime 装配。生产化持久化、事件一致性和分布式语义属于后续阶段。

## 6. 有意的 V1 范围取舍，不现在修

以下不是遗漏，而是有意的 V1 约束：

- 内存数据，不承诺多进程一致性；
- 固定 JSON 知识，不接入真实商品中心；
- 确定性检索，不接入向量数据库或外部 RAG；
- 模拟生成器，不接入真实模型；
- `accepted/edited` 不代表消费者发送；
- 不实现完整 B4 Harness、审批平台和沙箱；
- 不实现 B5 Loop、多 Agent 协作和自动规划；
- 不执行价格、库存、订单、支付和外部消息写操作。

### 实时问题的保守策略

`_realtime_reason` 当前按价格、库存、配送、发货、到货等关键词触发人工。它可能对部分静态政策问题过度升级，但在 V1 没有实时数据源的条件下，这是安全优先的有意取舍：

```text
过度转人工 < 使用静态资料伪装实时事实
```

后续若要提高召回/自动化比例，必须先引入明确的实时数据源和意图识别契约，不能只简单放宽关键词。

## 7. Standards 味道：留到后续重构

以下问题已记录，但不阻塞当前 tracer bullet：

1. 测试中重复的 `ProductQuestion` 和 `KnowledgeSource` 工厂，应抽共享 fixture；
2. `run_ref`、`policy_ref`、`artifact_ref`、`configuration_refs` 裸字典，应替换为明确引用对象；
3. `evidence_sources: list[dict[str, Any]]` 应替换为类型化输入 DTO；
4. runner 和 answer generator 对检索状态存在重复分支，应收敛状态决策；
5. runner 的处置转发方法可拆出独立 application facade；
6. `model_dump(exclude=...)` 等协议细节应封装成稳定投影方法；
7. 手写 `_uuid7` 应改为明确命名的资源 ID 生成器或统一 B2 工具。

### 重构时机

在 Ticket 10/11 完成前不做大规模重构。原因：

- 当前每个 ticket 仍在验证领域边界；
- 过早抽象可能冻结错误的 API；
- 重构必须保持 108+ 测试和端到端主路径全绿；
- 应在领域契约稳定后一次性处理引用对象、测试 fixture 和状态策略。

## 8. 下一阶段门禁

进入 Ticket 10/11 前保留以下门禁：

```bash
uv run pytest -q
uv run ruff check src
uv run ruff format --check src
uv run pre-commit run --all-files
```

必须继续满足：

- 固定商品问题主路径可运行；
- 无证据、冲突、跨租户、超预算和生成失败都有明确结果；
- run trace 查询必须带 tenant_id；
- 同一租户幂等键不能重复创建运行；
- 只读负向探针不触发写操作；
- AnswerDraft 必须带证据或 `need_human=true`；
- 当前工作树和提交边界清晰。

## 9. 下一阶段明确不做

Ticket 10/11 期间不做：

- PostgreSQL 或分布式事件总线；
- 完整 B4 权限引擎；
- 容器沙箱；
- 真实模型和真实 RAG；
- 消费者消息发送；
- 多 Agent 协作；
- B5 Loop；
- 大范围 presale 领域重构；
- 为消除代码味道而改变已冻结的业务契约。

## 10. 复盘结论

当前可以进入 Ticket 10/11，但应把它们视为 V1 原型收尾，而不是生产化启动。

推荐顺序：

```text
Ticket 10：30 天保留策略
→ Ticket 11：最小可观测运行入口
→ 再做一次 code-review
→ 再决定是否进入生产化架构阶段
```

在进入生产化之前，需要另开一个阶段处理：

- B2 持久化装配；
- PermissionDecision 和只读授权；
- 事件/审计完整性；
- 引用对象类型化；
- 知识来源和实时数据契约；
- 真实模型替代验收；
- 生产数据治理和部署边界。
