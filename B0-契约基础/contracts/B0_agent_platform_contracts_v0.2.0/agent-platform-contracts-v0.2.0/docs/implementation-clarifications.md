# B0 契约落地说明

以下内容用于记录从设计文档到可执行 Schema 时必须明确的实现细节。它们不改变 `O-01～O-12`，但后续若要修改，必须通过 Architecture Decision Record。

## Eval Suite 使用 ArtifactRef

B0 的 15 个核心资源中没有独立 `EvalSuite` 资源。评估集通常是较大的不可变文件集合，因此：

- `AgentSpec.eval_suite_refs` 使用 `ArtifactRef[]`；
- `PromptPackage.eval_suite_refs` 使用 `ArtifactRef[]`；
- Artifact 可以指向 Git、Object Storage 或其他受控存储；
- 后续若把 Eval Suite 升级为独立 Registry 资源，需要新增资源 Kind 和 API 版本评审。

## Event 使用 CloudEvents 1.0 标准属性

Event 信封包含：

- `specversion`；
- `id`；
- `source`；
- `type`；
- `subject`；
- `time`；
- `datacontenttype`；
- `dataschema`；
- `data`。

平台扩展字段包含：

- `subject_ref`；
- 聚合内 `sequence`；
- `trace`；
- 强类型 `schema_ref`。

`spec.id` 必须等于 `metadata.id`，避免 CloudEvents ID 与平台资源 ID 分裂。

## 结构校验与语义校验分离

JSON Schema 负责跨语言结构契约，Pydantic/Harness 负责下列语义：

- 集合之间的包含关系；
- 引用 Kind 与字段用途匹配；
- 当前状态是否要求 Approval、Lease、Artifact 或 Error；
- Context 分预算求和；
- Model Route 是否都位于 Provider Allowlist；
- 一次性审批是否被重复消费；
- 运行 Usage 是否超过 Budget。

任何非 Python 实现都必须提供等价语义验证器，不能只通过 JSON Schema 即宣称兼容。

## 价格快照双重引用

- `AgentRun.resolved_dependencies.price_snapshot_ref` 记录启动时冻结的价格表；
- `AgentRun.usage.price_snapshot_ref` 记录实际核算所用价格表；
- 两者默认必须一致；
- 若运行中价格版本发生切换，必须产生 Event 并拆分 Usage 计费明细，不能覆盖历史费用。

## 定义资源与运行资源的 Metadata 分离

- 定义资源包含 `key/namespace/version/content_digest`；
- 运行资源不包含 Semantic Versioning；
- 两者都包含 `revision`，但该字段只用于乐观并发；
- `revision` 不能替代内容版本或 Event Sequence。

## 定义生命周期解析分为新 Run 与恢复

- `new_run` 解析只接受 `active` 定义；
- `resume_run` 允许旧 Run 继续使用已冻结的 `active` 或 `deprecated` 精确版本；
- `blocked` 在两种模式下都失败关闭；
- `archived` 不允许直接恢复，必须进入受控迁移或终止流程；
- Registry 当前生命周期状态与 AgentRun 内的精确 `ResourceRef` 必须同时参与解析判定。

## 启动依赖与动态依赖分阶段冻结

- `resolved_dependencies.startup_skill_refs/startup_tool_refs` 记录启动前已经绑定的依赖；
- 运行时新选择的 Skill 或 Tool 必须先经过候选过滤、权限决策与精确版本解析；
- 首次使用前把精确 `ResourceRef` 追加到 `dynamic_dependency_activations`；
- 激活记录必须关联 Event，可选关联 Checkpoint，历史只允许追加；
- 已经启动冻结的依赖不得再次作为动态依赖重复激活。

## 同 Run Fallback 与新 Run Restart

以下条件全部满足时，模型切换属于同一 AgentRun：

- 当前 Run 未进入终态；
- 目标路由处于已冻结 ModelPolicy 的 Fallback Chain；
- 触发错误码被该回退步骤允许；
- Agent、Prompt、Context、Loop、Permission、Skill 和 Tool 等冻结依赖不变；
- 数据分类、供应商、地域、能力、质量与预算约束仍满足。

任一条件不满足时，不得原地改变 Run 的模型契约；如需继续执行，必须创建新的 AgentRun，并增加 `attempt`。所有模型选择写入只追加的 `model_selection_history`，`current_model_selection` 必须等于最后一条记录。
