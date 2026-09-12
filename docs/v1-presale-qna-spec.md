# V1 售前商品问答规格

> 状态：规格草案，基于已确认的产品目的和领域决策
> 版本：v1.0-draft
> 更新时间：2026-09-07
> 适用用户：电商平台内部商品运营人员、客服运营人员

## Problem Statement

内部客服和商品运营人员面对商品售前问题时，需要在商品资料、规则和提示词之间人工查找信息。现有基础设施已经具备 Agent 配置、任务运行、上下文组装和事件记录能力，但还没有把这些能力连成一条可验证的业务路径。

V1 需要解决的是：在明确的单商品范围内，从商品运营团队维护的已发布知识中找到可定位的事实依据，生成一份供内部人员审核的回答草稿；当系统无法证明回答可靠时，必须明确转人工，而不是生成没有依据的确定性回答。

## Solution

提供一个应用层的 `answer_product_question` 用例：

```text
ProductQuestion
→ ProductScope 校验
→ 租户与只读权限校验
→ 确定性知识检索
→ EvidenceItem 生成
→ ContextPackage 组装
→ AnswerDraft 生成
→ accepted / edited / escalated / discarded
→ Task / AgentRun / Event 追溯
```

V1 原型使用项目内版本化 JSON 商品资料集、内存知识仓储、确定性关键词检索和可替换的模拟回答生成器。所有替代实现必须显式标记为 prototype，不得宣称生产能力。

系统只生成内部使用的回答草稿，不直接发送消费者消息，也不执行任何商品、订单、库存、价格、支付或站外写操作。

## User Stories

1. 作为商品运营人员，我希望提交一个绑定明确商品的问题，以便系统只使用该商品范围内的资料。
2. 作为客服运营人员，我希望看到回答使用了哪些商品资料，以便判断回答是否有依据。
3. 作为客服运营人员，我希望证据能定位到具体字段或片段，以便快速核对原文。
4. 作为商品运营人员，我希望回答显示其使用的知识版本，以便避免用新资料事后解释旧回答。
5. 作为客服运营人员，我希望没有可靠证据时系统明确建议转人工，以便避免把猜测发给消费者。
6. 作为客服运营人员，我希望证据冲突时系统转人工，而不是自行选择一个未经确认的事实。
7. 作为客服运营人员，我希望超出商品范围的问题被识别出来，以便避免跨商品误答。
8. 作为商品运营人员，我希望跨租户知识访问被拒绝，以便保护不同业务主体的数据边界。
9. 作为客服运营人员，我希望涉及实时价格、库存或配送的问题被转人工，以便避免使用过期静态资料。
10. 作为内部用户，我希望看到回答的置信度信号和触发原因，以便决定是否采用或升级处理。
11. 作为内部用户，我希望接受回答草稿，以便将其作为客服流程中的建议回复。
12. 作为内部用户，我希望编辑回答草稿并保留原始版本，以便修正表达而不丢失系统输出。
13. 作为内部用户，我希望把问题转人工，以便由人工处理复杂、不确定或高风险问题。
14. 作为内部用户，我希望丢弃不合适的草稿，以便明确该结果没有被采用。
15. 作为审计人员，我希望通过 `run_ref` 查询一次运行的输入、知识证据、配置和结果，以便复盘回答来源。
16. 作为平台维护人员，我希望每次运行冻结 Agent、Prompt、ContextPolicy 和知识版本，以便配置变更不改变历史解释。
17. 作为平台维护人员，我希望检索无结果、权限失败、预算超限和模型失败都有明确失败状态，以便定位问题而不是看到伪成功。
18. 作为平台维护人员，我希望重复提交具有幂等行为，以便网络重试不产生无法解释的重复任务。
19. 作为商品运营团队，我希望知识来源具有发布状态和版本，以便只有已审核资料进入回答路径。
20. 作为商品运营团队，我希望 V1 原型可以使用固定 JSON 资料，以便在不接入生产系统的情况下验证业务闭环。
21. 作为业务负责人，我希望接受或编辑不等于消费者消息已发送，以便保留现有人工客服流程的控制权。
22. 作为数据治理负责人，我希望 V1 运行记录最多保留 30 天，以便控制原型阶段的数据积累。
23. 作为平台维护人员，我希望所有关键业务和技术阶段都有事件记录，以便判断失败发生在哪一段。
24. 作为内部用户，我希望回答输出结构化，而不是只有一段不可验证的文本，以便后续系统能够处理依据、置信度和人工建议。

## Implementation Decisions

### 1. 最高层测试 seam

V1 以一个应用层用例作为主要集成 seam：

```text
answer_product_question(request) -> AnswerDraftResult
```

该 seam 必须覆盖从 ProductQuestion 输入到 AnswerDraft/HumanDisposition 输出，以及通过 `run_ref` 查询追溯数据的完整路径。检索、Context、Task、AgentRun 和 Event 的单元/模块测试用于定位失败，但不替代这条端到端验收路径。

具体函数名和模块位置属于实现选择，不在本规格中冻结；冻结的是输入输出语义和观察结果。

### 2. ProductQuestion 输入

请求至少包含：

- `question_id`：业务问题标识；
- `tenant_id`：租户标识；
- `submitted_by`：内部操作者；
- `product_ref`：一个明确商品引用；
- `question_text`：非空问题文本；
- `idempotency_key`：重复提交保护；
- `requested_agent_ref`：可选，默认使用已批准的售前 Agent；
- `knowledge_scope`：只能表达当前商品范围；
- `submitted_at`：提交时间。

约束：

- `product_ref` 必须存在且属于 `tenant_id`；
- V1 不允许一个问题绑定多个商品；
- `question_text` 必须可被记录和审计；
- 重复的租户、操作者、商品和幂等键组合不得无界地产生新 Task；
- 输入不满足约束时不得创建成功的 AgentRun。

### 3. ProductKnowledgeSource

V1 原型使用项目内版本化 JSON 资料集。每条已发布知识来源至少表达：

- `source_id`；
- `tenant_id`；
- `product_ref`；
- `version`；
- `publication_status`，V1 只允许 `published` 进入检索；
- `title` 或来源名称；
- 可检索字段或片段；
- `updated_at`；
- `content_digest`；
- 来源定位信息。

商品运营团队是知识维护和审核责任方。V1 不实现知识编辑后台，但测试资料必须模拟已发布/未发布和不同版本。

### 4. 确定性检索

检索输入：

- `ProductQuestion.question_text`；
- `ProductScope.product_ref`；
- `tenant_id`；
- 已发布知识来源集合。

检索规则：

1. 先按 `tenant_id` 精确过滤；
2. 再按 `product_ref` 精确过滤；
3. 只读取 `published` 来源；
4. 对问题和字段内容执行确定性规范化；
5. 按明确关键词/短语匹配候选字段或片段；
6. 结果按确定性规则排序，排序相同必须有稳定的 tie-breaker；
7. 输出候选的来源版本、字段/片段定位、内容摘要和匹配原因；
8. 不使用跨租户、其他商品、未发布或无法定位的内容；
9. V1 不接入向量数据库、外部 RAG 服务或实时业务系统。

### 5. EvidenceItem

每个实际用于回答的证据项必须包含：

- `evidence_id`；
- `source_ref`；
- `source_version`；
- `tenant_id`；
- `product_ref`；
- `locator`：字段名、章节、片段范围或等价定位；
- `content_digest`；
- `relevance_reason`。

证据项不是完整知识库，也不是任意检索候选。只有进入 ContextPackage 并实际支持回答的候选才成为本次运行的 evidence。

### 6. 证据冲突

V1 认定为证据冲突的情况包括：

- 同一商品、同一事实属性在当前允许的已发布来源中出现不同值；
- 不同来源版本的内容不能依据明确的生效规则排序；
- 检索结果同时命中互斥规则；
- 证据定位或版本信息不完整，无法判断适用范围。

出现冲突时：

- 不生成确定性事实结论；
- `need_human = true`；
- `reason_codes` 至少包含 `EVIDENCE_CONFLICT`；
- 记录冲突证据引用和 `run.failed` 或 `answer.needs_human` 事件；
- 不允许回答生成器自行选择一个冲突值而不披露。

### 7. ContextPackage

ContextPackage 至少包含：

- `run_ref`；
- `model_call_sequence`；
- `policy_ref`；
- 商品问题内容的受限引用；
- 实际使用的 EvidenceItem provenance；
- Prompt/Agent 配置版本引用；
- `total_tokens` 和预算结果；
- 脱敏摘要；
- 内容摘要。

必须满足 B0 ContextPackage 校验。B3 当前的确定性组装、去重、优先级和预算能力复用；商品证据适配器是本规格新增缺口。

### 8. AnswerDraft 输出

成功或需要人工的结果都必须是结构化结果，至少包含：

- `answer_id`；
- `question_ref`；
- `run_ref`；
- `answer_text`；
- `evidence_refs`；
- `confidence_signal`；
- `need_human`；
- `reason_codes`；
- `generator_ref`；
- `generated_at`；
- 原始草稿版本标识。

事实性回答必须引用 EvidenceItem。没有证据时允许返回解释性占位或人工建议，但不得伪装成商品事实。

V1 的 `confidence_signal` 是规则型解释信号，不等同于准确率。建议至少表达：

- `supported`：是否存在足够证据；
- `conflict_free`：证据是否无冲突；
- `scope_match`：是否在商品范围内；
- `freshness_known`：资料版本和更新时间是否可知。

### 9. HumanDisposition

回答草稿的业务处置状态：

```text
answered → accepted | edited | escalated | discarded
```

规则：

- `accepted`：接受原始草稿；保留处置人和时间；不表示消费者消息已发送；
- `edited`：内部用户编辑后采用；必须保留原始草稿、编辑后内容、编辑人、编辑时间和版本关系；不表示消费者消息已发送；
- `escalated`：转人工；必须保留转人工原因；
- `discarded`：不采用；必须保留处置人和时间；
- 终态处置不能修改已经发生的 Event 和 provenance。

### 10. Task、AgentRun 和事件关联

关联必须满足：

```text
ProductQuestion 1 ── 1..n Task
Task 1 ── 1..n AgentRun
AgentRun 1 ── 0..1 AnswerDraft
AgentRun 1 ── 0..n ContextPackage
AgentRun 1 ── 0..n ToolCall
AgentRun 1 ── 1..n Event
```

V1 建议一个 ProductQuestion 一次只允许一个 active AgentRun；失败后如需再次执行，应产生可区分的 attempt，而不是覆盖旧运行。

技术状态沿用 B0/B2：

```text
Task: created → validated → queued → running → succeeded / failed
AgentRun: created → resolving → ready → running → succeeded / failed
```

业务状态独立维护，不得用 `AgentRun.succeeded` 直接推断内部用户已接受回答。

### 11. 权限与租户隔离

V1 最小权限模型：

- 操作者必须属于请求租户；
- 商品、知识来源、证据和运行记录必须属于同一租户；
- 知识查询只能读取已发布、属于指定商品的数据；
- V1 所有 ToolCall 都是只读；
- 跨租户请求默认拒绝；
- 价格、库存、订单、支付、商品资料写入和外部消息发送不属于 V1 权限范围；
- 权限拒绝必须产生明确失败或人工处置，并记录原因。

### 12. 数据保留

V1 原型运行记录固定保留 30 天。保留对象至少包括：

- ProductQuestion；
- Task；
- AgentRun；
- Context provenance；
- AnswerDraft 版本；
- HumanDisposition；
- 关键 Event。

具体删除触发时点由实现阶段确定，但不能超过 30 天默认策略；如有 legal hold 或合规要求，必须显式建模，不能静默绕过。

### 13. 错误行为

错误必须结构化并可观察。至少需要覆盖：

| 错误场景 | 结果 |
|---|---|
| 商品不存在 | 拒绝处理，不创建成功回答 |
| 商品不属于租户 | 权限拒绝，转人工或失败 |
| 知识来源为空 | `need_human=true`，原因 `NO_EVIDENCE` |
| 只有未发布知识 | 不使用，按无证据处理 |
| 证据冲突 | `need_human=true`，原因 `EVIDENCE_CONFLICT` |
| 问题超商品范围 | `need_human=true`，原因 `OUT_OF_SCOPE` |
| 涉及实时价格/库存/配送 | `need_human=true`，原因 `REALTIME_DATA_REQUIRED` |
| 上下文超预算 | 明确失败或转人工，原因 `CONTEXT_BUDGET_EXCEEDED` |
| 权限失败 | 明确拒绝并记录 `PERMISSION_DENIED` |
| 生成器失败 | 运行失败或转人工，原因 `GENERATION_FAILED` |
| 重复幂等请求 | 返回已有任务/运行引用，不重复创建 |
| 契约校验失败 | 明确失败，不返回伪造 AnswerDraft |

### 14. 可观测性和审计

一次成功或人工处置的运行必须能沿以下引用追溯：

```text
question_ref
→ task_ref
→ run_ref
→ frozen Agent/Prompt/Policy refs
→ knowledge source/version/locator
→ evidence_refs
→ context_ref/content_digest
→ answer_ref/version
→ disposition_ref
```

关键事件至少包括：

- `question.submitted`；
- `task.created`；
- `run.created`；
- `knowledge.retrieved`；
- `context.built`；
- `answer.generated`；
- `answer.needs_human`；
- `answer.accepted`；
- `answer.edited`；
- `answer.escalated`；
- `answer.discarded`；
- `run.failed`。

Event 是追加事实，不是可被后续状态覆盖的日志文本。

## Testing Decisions

### 1. 最高层验收

优先测试外部行为：一次合法 ProductQuestion 是否能得到结构化 AnswerDraft 或明确人工处置，并且能通过 `run_ref` 追溯知识证据、Context 和运行事件。

主集成测试不应绑定具体类名、内部字典结构或检索算法实现；只断言输入输出契约、状态结果、证据引用和可观察事件。

### 2. 必须覆盖的端到端场景

1. 单商品问题命中已发布知识，生成带字段/片段证据的 AnswerDraft；
2. 无知识命中，返回 `need_human=true` 和 `NO_EVIDENCE`；
3. 证据冲突，返回 `EVIDENCE_CONFLICT`，不生成确定性事实；
4. 跨租户知识不可见；
5. 未发布或其他商品知识不被使用；
6. 实时价格/库存/配送问题转人工；
7. Context 预算超限明确失败；
8. 生成器失败明确失败或转人工；
9. 接受草稿后可追溯，且不产生“已发送消费者消息”的假事实；
10. 编辑草稿后原始和编辑版本都可查询；
11. 转人工和丢弃都有处置事件；
12. 相同幂等键不会无界创建重复任务；
13. 30 天保留策略可被验证；
14. `run_ref` 可以查询完整最小追溯链。

### 3. 模块级测试

- **Knowledge Adapter**：租户过滤、商品过滤、发布状态、确定性排序、版本和定位；
- **Evidence Builder**：字段/片段定位、摘要、冲突检测；
- **Context Service**：来源组装、去重、预算和 B0 校验；
- **Answer Generator**：有证据/无证据/冲突输入下的结构化输出；
- **Application Orchestrator**：状态转换、幂等、失败出口和事件顺序；
- **Disposition Service**：accepted/edited/escalated/discarded 和版本留痕；
- **Runtime Repositories**：复用现有 B2 内存/SQLite 契约测试和回滚测试。

### 4. 现有测试基础

现有根级测试入口为：

```bash
uv run pytest -q
```

当前 B1/B2/B3 测试已经覆盖部分 Task、AgentRun、Context、仓储、SQLite 回滚和 API 行为。新 V1 测试必须新增一条业务应用层端到端 seam，不应只把现有基础设施测试数量继续扩大。

## Out of Scope

- 面向消费者的直接生产入口；
- 售后、退款、投诉；
- 自动下单、改价、优惠、库存写入、支付和订单操作；
- 真实价格、库存、配送系统接入；
- 真实生产 RAG、向量数据库和外部知识平台；
- 直播切片 Agent；
- 自媒体内容 Agent；
- 多 Agent 协作；
- 完整 B4 Harness、容器沙箱和多协议 Tool Executor；
- B5 多策略 Loop、无限重试、自主规划和反思；
- 消息发送、消费者通知和站外触达；
- 未经测量的准确率承诺；
- PostgreSQL、消息队列、对象存储和分布式事务生产化；
- 在本规格内重新设计 B0 已冻结字段语义。

## Further Notes

### 1. 现有 B0–B3 的复用

- **B0**：复用资源引用、ContextPackage、Task、AgentRun、Event、ToolCall、状态机和摘要策略；新增业务对象不能假装已经由 B0 完整覆盖。
- **B1**：复用版本化 Agent、Prompt、ContextPolicy、PermissionProfile 和只读 Tool 定义；暂不继续扩展通用注册平台能力。
- **B2**：复用 Task/Run/Event/Checkpoint 仓储和事务测试；Checkpoint 不是 V1 单次问答成功标准。
- **B3**：复用确定性来源组装、去重、排序、预算和 B0 校验；新增商品知识和 EvidenceItem 适配边界。

### 2. 需要新增或返工的契约

进入实现前必须先定义或冻结：

- ProductQuestion 输入契约；
- ProductKnowledgeSource 版本和发布状态契约；
- EvidenceItem 字段/片段定位契约；
- AnswerDraft 结构化输出契约；
- HumanDisposition 和草稿版本契约；
- 业务 ProductQuestion 状态机；
- 业务对象与 B0 Task/AgentRun 的关联契约。

这些契约不应通过随意增加 B0 通用字段来解决；如需修改 B0，必须单独版本化并记录兼容策略。

### 3. 规格完成后的下一步

规格可以进入 `/to-tickets`，但 ticket 应优先按一条 tracer bullet 拆分：

```text
固定 JSON 商品知识
→ 确定性检索
→ 字段/片段证据
→ ContextPackage
→ 模拟结构化 AnswerDraft
→ accepted/edited/escalated/discarded
→ run_ref 追溯
```

第一批 ticket 不应先实现完整 B4/B5，也不应先实现所有未来业务 Agent。

## Specification Gate

当前结论：**有条件通过，可以进入 `/to-tickets`。**

已满足：

- 目的、用户和第一条业务路径已确认；
- 业务对象与平台运行对象已区分；
- 输入、输出、状态、失败出口和只读边界已定义；
- 证据、人工处置、版本和追溯要求已定义；
- 明确复用 B0–B3 和不扩大范围的边界；
- 最高层端到端测试 seam 已确定。

进入 `/to-tickets` 前需要注意：

- 当前规格中的确定性检索算法、冲突判定、置信度信号和 30 天删除触发时点仍需在 ticket 验收标准中量化；
- 这些是实现规格细化，不再阻塞产品方向；
- 任何 ticket 都不得自行扩大到真实生产外部系统或业务写操作。
