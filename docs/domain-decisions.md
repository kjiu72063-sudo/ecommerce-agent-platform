# V1 领域决策记录

> 状态：关键领域决策已确认
> 更新时间：2026-09-07
> 适用范围：只读、带依据、可转人工的内部售前商品问答

## 1. 已确认决策

| 编号 | 决策 | 当前结论 |
|---|---|---|
| D-01 | 第一类用户 | 电商平台内部商品运营人员和客服运营人员 |
| D-02 | 第一条业务路径 | 只读、带商品依据、可转人工的售前商品问答 |
| D-03 | 商品范围 | V1 一次问题绑定一个明确商品；不支持多商品比较 |
| D-04 | V1 原型知识来源 | 项目内版本化 JSON 商品资料集；作为原型唯一输入来源 |
| D-05 | 未来知识权威责任 | 商品运营团队维护和审核已发布商品知识 |
| D-06 | 检索方式 | V1 使用可复现的确定性检索；暂不接入向量数据库或外部 RAG 平台 |
| D-07 | 证据粒度 | 字段/片段级；记录来源、版本、定位、内容摘要 |
| D-08 | 转人工条件 | 无证据、证据冲突、超商品范围、涉及实时价格/库存、权限失败或系统失败时必须转人工 |
| D-09 | 实时业务数据 | V1 不接入真实实时价格、库存和配送系统 |
| D-10 | 回答含义 | 生成 `AnswerDraft`，不等于已发送消息或业务承诺 |
| D-11 | 草稿处置 | 支持接受、编辑、转人工和丢弃；原始草稿与编辑后版本都必须留痕 |
| D-12 | 编辑状态 | `edited` 表示编辑后的回答已被内部用户采用，不表示已发送给消费者 |
| D-13 | 发送边界 | `accepted` 和 `edited` 都不代表已发送；发送由现有客服流程负责 |
| D-14 | 数据保留 | V1 原型运行记录固定保留 30 天 |
| D-15 | 租户隔离 | 所有问题、知识、证据、配置和运行记录必须属于同一租户；跨租户默认拒绝 |
| D-16 | 执行形态 | 单次、有界、可失败；不实现复杂 Loop、无限重试或自主协作 |
| D-17 | 业务写操作 | V1 不执行改价、下单、库存写入、支付、订单操作或站外触达 |

## 2. V1 业务状态机

```text
submitted → scoped → processing → answered
answered → accepted | edited | escalated | discarded
submitted/scoped/processing → failed | cancelled
```

状态语义：

- `submitted`：问题已接收；
- `scoped`：单商品和知识范围已确认；
- `processing`：正在检索、组装或生成；
- `answered`：已产生回答草稿，等待内部处置；
- `accepted`：内部用户接受原始草稿；
- `edited`：内部用户编辑后采用，保留原始与编辑版本；
- `escalated`：转人工处理；
- `discarded`：草稿未被采用；
- `failed`：系统无法可靠完成；
- `cancelled`：调用方主动取消。

`accepted`/`edited` 不表示消费者消息已经发送。

## 3. 平台状态机边界

V1 继续使用 B0/B2 已定义的平台状态机，但不把它们当作业务状态：

- `Task`：承载调度请求；
- `AgentRun`：表示一次具体执行尝试；
- `ToolCall`：V1 只允许只读知识查询；
- `Event`：记录已经发生的技术或业务事实；
- `Checkpoint`：V1 单次问答不是核心成功标准。

业务 `ProductQuestion` 的处置状态必须独立于 `Task`/`AgentRun` 的技术状态。

## 4. 已确认的 V1 最小领域对象

```text
Tenant
Operator
Product
ProductScope
ProductQuestion
ProductKnowledgeSource
EvidenceItem
AnswerDraft
HumanDisposition
Task
AgentRun
ContextPackage
ToolCall
Event
Provenance
```

其中 `ProductQuestion`、`ProductKnowledgeSource`、`EvidenceItem`、`AnswerDraft` 和 `HumanDisposition` 是当前 B0–B3 尚未完整覆盖的业务对象，后续规格阶段必须优先定义它们的输入、输出和验收契约。

## 5. 仍然需要在规格阶段细化、但不再阻塞方向的问题

以下不是产品方向未决，而是实现规格需要进一步量化的规则：

- 字段/片段证据的具体定位格式；
- “证据冲突”的判定算法；
- 确定性检索的关键词、同义词和排序规则；
- 置信度信号的计算公式和展示范围；
- `escalated` 是否关联现有人工工单 ID；
- `edited` 版本的字段格式和版本号规则；
- 30 天保留从创建、最后访问还是运行完成时开始计算；
- 商品运营知识审核的最小发布状态；
- 原型 JSON 迁移到商品中心时的兼容策略。

这些事项可以在 `/to-spec` 中形成可验收规则，不应重新打开 V1 的产品边界。

## 6. 进入规格阶段结论

领域方向已收敛，可以进入 `/to-spec`。

规格必须围绕以下主路径编写：

```text
ProductQuestion
→ ProductScope
→ ProductKnowledgeSource
→ EvidenceItem
→ ContextPackage
→ AnswerDraft
→ HumanDisposition
→ Task / AgentRun / Event 追溯
```

暂不进入完整 B4/B5 实现，也不接入真实生产副作用。

---

# B4–B6（Harness / Loop / Agent）领域决策

> 对应新里程碑：可复用的 Agent 执行与决策循环层。

| 编号 | 决策 | 当前结论 |
|---|---|---|
| D-B1 | 里程碑目标 | 最小可观察 Agent 闭环：Harness 执行 Agent + Loop 决策，驱动现有售前问答 |
| D-B2 | Loop 终态 | need_human 或达到 max_steps 即终态；不再在已需人工时继续循环 |
| D-B3 | 首实例 | 复用现有售前 QA，暴露 `retrieve` 工具（只读） |
| D-B4 | 本轮循环语义 | 单步终态：continue 分支结构性保留但不触发；多步重查留待后续加工具 |
| D-B5 | max_steps | 默认 5（有界，防失控） |
| D-B6 | Harness 与现有 runner 关系 | **分层包装**：Harness 是通用执行壳，把售前问答作为 Agent 实例驱动一个 AgentRun + Loop；`PresaleQaRunner.ask` 内部业务流不变 |
| D-B7 | 时序 | 同步、请求内直连（无异步队列） |
| D-B8 | 副作用 | 本轮工具为只读检索，不新增有副作用的工具 |

领域模型见 `docs/domain-model-b4b6.md`。
