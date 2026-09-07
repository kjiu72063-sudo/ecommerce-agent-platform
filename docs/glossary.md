# V1 领域术语表

> 适用范围：只读售前商品问答
> 更新时间：2026-09-06

| 术语 | 规范定义 | 不应混淆为 |
|---|---|---|
| 租户（Tenant） | 拥有商品、知识、配置和运行数据隔离边界的业务主体 | 商品、操作者、消费者 |
| 内部操作者（Operator） | 使用系统提交问题、审核回答或处理人工转接的商品/客服运营人员 | 终端消费者、Agent |
| 商品（Product） | 售前问题所指向的业务商品实体 | 商品知识来源、商品范围 |
| 商品范围（ProductScope） | 一次问题允许访问的商品或商品知识边界 | 租户范围、检索结果 |
| 商品问题（ProductQuestion） | 内部操作者提交的一次需要回答的售前问题 | Task、AgentRun |
| 商品知识来源（ProductKnowledgeSource） | 可授权使用的商品资料及其版本、状态和来源定位 | 证据项、ContextPackage |
| 证据项（EvidenceItem） | 本次运行实际使用、可定位到来源版本的事实片段 | 全部检索候选、回答本身 |
| 检索候选（RetrievalCandidate） | 知识查询返回的可能相关内容，尚未必被回答使用 | 已确认的证据项 |
| 回答草稿（AnswerDraft） | 系统生成、供内部用户审核或处置的回答建议 | 已发送消息、业务承诺 |
| 人工处置（HumanDisposition） | 内部用户对回答草稿的接受、编辑、转人工或丢弃动作 | AgentRun 状态 |
| 需要人工（NeedHuman） | 表示系统无法在当前证据和策略下可靠完成，建议人工处理 | 模型异常、任务失败 |
| 置信度信号（ConfidenceSignal） | 对当前回答可靠性的解释性信号 | 经验证的准确率、事实真值 |
| Task | B0/B2 定义的可调度任务对象，承载一次技术执行请求 | ProductQuestion |
| AgentRun | Task 的一次具体执行尝试及其冻结配置 | Task、AnswerDraft |
| ContextPackage | 一次回答生成使用的结构化上下文快照 | 商品知识库、PromptPackage |
| PromptPackage | 版本化的提示词片段和输出指导 | ContextPackage、回答草稿 |
| AgentSpec | Agent 的角色、目标、非目标和依赖配置声明 | 运行实例、业务回答 |
| SkillManifest | 可复用技能的版本化能力描述 | ToolManifest、业务流程 |
| ToolManifest | 工具能力、传输、风险和副作用的声明 | ToolCall |
| ToolCall | AgentRun 对某个已声明工具的一次调用事实 | ToolManifest |
| 只读工具（Read-only Tool） | 只查询授权数据、不修改业务状态的工具 | 无副作用的所有操作；读日志也需授权 |
| Context Policy | 规定上下文来源、预算、排序、去重和脱敏策略的版本化配置 | 业务知识规则 |
| Permission Profile | 规定允许/拒绝动作、资源和租户边界的版本化配置 | 单次 PermissionDecision |
| Permission Decision | 对一次具体访问或工具调用的允许、拒绝或需审批结果 | PermissionProfile |
| provenance | 说明数据、上下文或回答事实从哪个来源版本和位置而来的信息 | 普通日志、模型解释 |
| 运行事实（Event） | 已发生且可追加记录的系统事实 | 当前状态快照 |
| Artifact | 可寻址的较大输入、输出、快照或文件对象 | Event、普通字符串 |
| Checkpoint | AgentRun 在可恢复节点上的执行快照 | 任意结果缓存 |
| 业务状态 | ProductQuestion 的提交、处理、回答和人工处置状态 | Task/AgentRun 技术状态 |
| 技术状态 | Task、AgentRun、ToolCall 等平台对象的生命周期状态 | 人工是否接受回答 |
| tracer bullet | 一条从真实输入贯穿到业务输出的最小可观察业务路径 | 仅能单独通过的单元测试 |

## 术语使用规则

1. 说“问题”时，默认指 `ProductQuestion`；若指技术调度对象，必须明确说 `Task`。
2. 说“运行”时，默认指 `AgentRun`；不能用它代替商品问题的业务处置。
3. 说“知识”时，必须区分原始 `ProductKnowledgeSource`、检索候选和已使用的 `EvidenceItem`。
4. 说“回答”时，V1 默认指 `AnswerDraft`，不是已发送给消费者的最终消息。
5. 说“置信度”时，默认指可解释的 `ConfidenceSignal`，不能声称它等同于准确率。
6. “当前状态”和“已发生事实”分开表达：状态可被推进，Event 和 provenance 不能被改写来抹除历史。
7. “支持实时库存/价格”只有在明确接入权威只读来源并定义快照时间后才成立；不能因为存在字段或 ToolManifest 就默认支持。
