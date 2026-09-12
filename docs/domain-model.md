# V1 售前商品问答领域模型

> 状态：V1 领域模型已确认；实现细节由规格阶段细化
> 更新时间：2026-09-07
> 适用范围：V1 只读、带依据、可转人工的内部售前商品问答

## 1. 建模范围

本模型只描述一条业务路径：

```text
内部客服/运营人员
→ 提交商品问题
→ 绑定商品和知识范围
→ 检索知识
→ 形成证据集合
→ 生成回答草稿
→ 接受或转人工
→ 记录运行和审计事实
```

本模型将现有对象分为两层：

1. **业务领域对象**：回答“业务上发生了什么”；
2. **平台和运行时对象**：回答“系统如何配置、执行和记录这件事”。

B0–B3 当前主要覆盖第二层，不能替代第一层。

## 2. 核心业务对象

### 2.1 商品问题（ProductQuestion）

内部用户希望得到回答的一次明确售前问题。

核心属性：

- `question_id`：业务问题标识；
- `tenant_id`：所属租户；
- `submitted_by`：内部操作人；
- `product_scope`：V1 绑定的商品范围；
- `question_text`：原始问题；
- `conversation_context`：可选的已授权上下文；
- `requested_at`：提交时间；
- `idempotency_key`：重复提交保护。

业务含义：它表达“要回答什么”，不表达“系统如何执行”。

### 2.2 商品范围（ProductScope）

限定本次问题允许使用哪些商品资料。

V1 采用单商品范围：

```text
一个 ProductQuestion 必须绑定一个明确的 ProductScope
```

多商品比较、商品集合和跨商品推荐暂不进入 V1。

### 2.3 商品知识来源（ProductKnowledgeSource）

可被授权用于回答商品问题的业务资料，例如：

- 商品详情；
- 规格参数；
- 使用说明；
- 配送或售后规则中与售前回答有关的部分；
- 经审核的常见问答。

知识来源必须具有：

- 所属租户；
- 商品关联；
- 来源标识和版本；
- 生效状态；
- 更新时间；
- 内容摘要；
- 数据分类；
- 可追溯的来源定位。

V1 原型使用项目内版本化 JSON 商品资料集作为唯一输入来源；商品运营团队负责未来已发布知识的维护和审核。原型可以用内存记录模拟，但不能省略来源标识和版本。

### 2.4 证据项（EvidenceItem）

从一个或多个知识来源中选出的、支持回答的最小可引用事实片段。V1 要求达到字段/片段级，并记录来源、版本、定位和内容摘要。

证据项不是原始知识库本身，而是本次运行实际使用的证据快照。

核心属性：

- `evidence_id`；
- `source_ref`；
- `source_version`；
- `locator`：章节、字段、片段或其他定位；
- `content_digest`；
- `relevance_reason`；
- `tenant_id`；
- `product_ref`。

### 2.5 回答草稿（AnswerDraft）

系统为内部用户生成的、尚未代表最终业务承诺的回答建议。

核心属性：

- `answer_id`；
- `question_ref`；
- `run_ref`；
- `answer_text`；
- `evidence_refs`；
- `confidence_signal`；
- `human_review`；
- `generated_at`；
- `model_or_template_ref`。

V1 中 AnswerDraft 不等于已发送给消费者的最终消息。系统只生成建议，是否使用由内部用户决定。

### 2.6 人工处置（HumanDisposition）

内部用户对回答草稿的业务处置结果。

V1 至少区分：

- `accepted`：内部用户接受原始草稿；
- `edited`：内部用户编辑后采用，保留原始与编辑后版本；
- `escalated`：转交人工或更高权限人员；
- `discarded`：不采用该草稿。

`accepted` 和 `edited` 都不代表已发送给消费者；发送由现有客服流程负责。

## 3. 平台管理对象

这些对象已存在于 B0/B1，但它们不是业务问题本身：

| 对象 | 领域职责 |
|---|---|
| `AgentSpec` | 定义售前问答 Agent 的角色、目标、非目标和引用配置 |
| `SkillManifest` | 描述可复用的技能能力；V1 先不要求动态技能编排 |
| `ToolManifest` | 描述商品知识查询等工具能力及其副作用级别 |
| `PromptPackage` | 定义回答身份、规则、输出约束等提示内容 |
| `ContextPolicy` | 定义上下文来源、排序、预算、去重和脱敏策略 |
| `ModelPolicy` | 定义模型路由、预算和降级策略；V1 可由替代实现模拟 |
| `PermissionProfile` | 定义只读访问和租户隔离规则 |
| `LoopProfile` | 描述迭代策略；V1 只允许 single-pass 语义 |

平台管理对象的共同不变量：

- 必须带版本；
- 必须经过定义对象生命周期管理；
- 运行时必须使用冻结的版本/摘要，而不是隐式读取“当前最新”；
- 平台配置变更不能悄悄改变已经完成运行的解释。

## 4. 运行时对象

| 对象 | 领域含义 | V1 用法 |
|---|---|---|
| `Task` | 一次可追踪的业务请求 | 表示 ProductQuestion 的运行任务 |
| `AgentRun` | 一次具体执行尝试 | 绑定 Task、Agent 快照、依赖和运行结果 |
| `ContextPackage` | 一次模型或回答生成所使用的上下文快照 | 必须包含证据 provenance 和摘要 |
| `Event` | 已发生的运行事实 | 记录提交、检索、生成、失败、转人工等事实 |
| `Artifact` | 可寻址的较大输入/输出或快照 | 必要时保存完整问题、回答或上下文 |
| `Checkpoint` | 可恢复执行的快照 | V1 单次问答不是核心；暂不作为成功标准 |
| `ToolCall` | 一次具体工具调用 | V1 只允许只读知识查询调用 |

## 5. 审计对象

### 5.1 Provenance

Provenance 说明一个上下文或回答事实来自哪里。至少要能回答：

```text
这条回答使用了哪份商品资料的哪个版本、哪个片段？
```

### 5.2 PermissionDecision

说明本次问题/工具调用为什么被允许或拒绝。V1 至少需要表达：

- 操作人身份；
- 租户范围；
- 商品范围；
- 只读动作；
- 决策结果；
- 决策依据摘要。

### 5.3 RunEvent

事件是事实记录，不是业务当前状态的唯一替代品。建议记录：

- `question.submitted`；
- `task.created`；
- `knowledge.retrieved`；
- `context.built`；
- `answer.generated`；
- `answer.needs_human`；
- `answer.accepted` / `answer.edited` / `answer.discarded`；
- `run.failed`。

## 6. 临时计算对象

这些对象只存在于一个处理步骤或一次运行内，不应被当作长期业务主数据：

- `RetrievalCandidate`：检索候选；
- `EvidenceSet`：本次回答候选证据集合；
- `ConfidenceSignal`：模型/规则产生的置信度信号；
- `ContextAssembly`：ContextPackage 生成前的中间结构；
- `HumanEscalationReason`：转人工原因集合；
- `ModelResponse`：模型原始响应；
- `RedactionResult`：脱敏处理结果。

临时对象一旦影响最终回答或处置，应转化为可追溯字段、Artifact 或 Event，不允许只留在日志里。

## 7. 关系模型

```text
Tenant
  ├── Operator
  ├── Product
  │     └── ProductKnowledgeSource
  │             └── EvidenceItem
  └── ProductQuestion
          ├── Task
          │     └── AgentRun
          │             ├── ContextPackage
          │             │     └── EvidenceItem refs
          │             ├── ToolCall (read-only only)
          │             ├── Event
          │             └── AnswerDraft
          │                     └── HumanDisposition
          └── AgentSpec snapshot
```

关键关系：

- 一个 `ProductQuestion` 对应一个业务问题；
- 一个 `ProductQuestion` 至少产生一个 `Task`；
- 一个 `Task` 可以有多个 `AgentRun`，但同一时刻只能有一个 active run；
- 一个 `AgentRun` 必须冻结 AgentSpec、Prompt、ContextPolicy、PermissionProfile 等依赖版本；
- 一个 `AnswerDraft` 必须关联一个 `AgentRun`；
- 一个 `AnswerDraft` 的事实性内容必须引用零个或多个 `EvidenceItem`，若无有效证据则必须标记人工处置；
- `HumanDisposition` 只处置回答草稿，不改变原始知识来源和运行事实；
- `ToolCall` 必须属于 AgentRun，V1 只能是只读知识查询。

## 8. 生命周期

### 8.1 ProductQuestion 生命周期（建议）

```text
submitted
  → scoped
  → processing
  → answered
  → accepted / edited / escalated / discarded
```

失败出口：

```text
submitted / scoped / processing → failed
submitted / scoped / processing → cancelled
```

状态含义：

- `submitted`：已接收，尚未完成商品和知识范围确认；
- `scoped`：商品和知识范围已确认；
- `processing`：正在检索、组装或生成；
- `answered`：已产生回答草稿；
- `accepted`：内部用户接受草稿；
- `edited`：内部用户编辑后采用；
- `escalated`：需要人工处理；
- `discarded`：草稿被放弃；
- `failed`：系统无法可靠完成；
- `cancelled`：调用方主动取消。

这个业务状态机尚未写入 B0，因为它是 V1 业务语义，不应直接借用 Task 或 AgentRun 状态机。

### 8.2 Task 生命周期

沿用 B0 Task 状态机，由 B2 负责运行调度：

```text
created → validated → queued → running
                                  ├→ succeeded
                                  ├→ failed
                                  ├→ waiting_input
                                  ├→ waiting_approval
                                  ├→ suspended
                                  ├→ cancelled
                                  └→ expired
```

Task 是执行载体，不代替 ProductQuestion 的业务处置状态。

### 8.3 AgentRun 生命周期

沿用 B0 AgentRun 状态机：

```text
created → resolving → ready → running
                                  ├→ waiting_tool
                                  ├→ waiting_input
                                  ├→ checkpointed
                                  ├→ succeeded
                                  ├→ failed
                                  ├→ cancelled
                                  └→ timed_out
```

V1 原型建议只走：

```text
created → resolving → ready → running → succeeded / failed
```

### 8.4 ToolCall 生命周期

V1 只允许只读工具调用：

```text
proposed → validating → scheduled → executing → succeeded / failed
                         └→ denied
```

若将来引入有副作用工具，必须另行引入 idempotency、审批和沙箱规则，不能复用 V1 的只读假设。

## 9. 核心不变量

1. **租户隔离**：任何问题、知识、证据、配置和运行记录都不能跨租户隐式读取。
2. **商品范围明确**：V1 的问题必须绑定一个明确商品或明确知识范围。
3. **证据可追溯**：每个事实性回答要么有证据引用，要么明确标记需要人工确认。
4. **证据冻结**：一次 AgentRun 使用的知识版本、片段摘要和 ContextPackage 生成后不可被“当前最新知识”替换解释。
5. **只读副作用**：V1 ToolCall 不得改变价格、库存、订单、支付、商品资料或外部消息状态。
6. **配置冻结**：运行必须记录实际使用的 AgentSpec、PromptPackage、ContextPolicy、PermissionProfile 和模型/替代实现版本。
7. **运行与业务分离**：Task/AgentRun 的技术生命周期不能直接代表 ProductQuestion 的人工处置结果。
8. **失败显式**：检索无证据、权限失败、预算超限、模型失败和契约失败必须产生明确失败或人工处置，不得伪造成功。
9. **幂等**：同一业务问题的重复提交不能无界地产生重复任务；使用 B0 的 idempotency key 约束。
10. **审计不可变**：Event 和 provenance 是已发生事实，不能通过更新当前对象来抹除历史。
11. **版本可解释**：回答结果必须能够解释其使用的配置和知识版本。
12. **人工优先兜底**：系统无法证明可靠性时，输出人工处置建议，而不是提高置信度掩盖不确定性。

## 10. 模块责任边界

| 模块 | 负责 | 不负责 |
|---|---|---|
| ProductQuestion/Application | 接收问题、绑定范围、协调业务处置 | 不实现模型调用和知识检索细节 |
| Knowledge Adapter | 查询授权知识并返回候选证据 | 不决定最终回答和人工处置 |
| Permission Boundary | 校验租户、操作者、商品范围和只读动作 | 不生成回答 |
| Context Service | 将已授权输入组装为 ContextPackage | 不自行扩大知识范围、不决定业务真值 |
| Answer Generator | 根据 Context 生成结构化草稿 | 不宣称无证据事实为确定事实 |
| Human Disposition | 接受、编辑、转人工或丢弃草稿 | 不修改原始运行事件 |
| B1 Registry | 管理版本化 Agent/Prompt/Tool/Policy 定义 | 不保存回答事实和人工处置 |
| B2 Runtime | 管理 Task/Run/Event/Checkpoint 持久化 | 不定义商品业务规则 |
| B3 Context | 组装和校验上下文 | 不替代知识权威源 |
| B4 Harness（后续） | 执行权限、工具和审批边界 | 不决定产品问答目标 |

## 11. 当前领域风险

- 现有 B0 有丰富的运行时字段，但没有 V1 的 ProductQuestion、ProductKnowledgeSource、EvidenceItem、AnswerDraft 业务契约；
- B3 当前输入是通用 descriptor，尚未定义商品知识检索和证据引用契约；
- B2 当前 Task/AgentRun 服务没有完整的业务问题和回答草稿关联；
- `confidence` 的业务语义尚未确定，不能直接当成准确率；
- 商品资料的权威来源、审核状态和更新时间责任人尚未确定；
- 是否允许价格、库存、配送等实时查询尚未确定；
- 人工处置是否包含最终发送动作尚未确定。
