# B0 一致性测试规范

## 目的

本规范定义 B0 合同包的最低验证要求。任何 Registry、Runtime、Context Engine、Harness 或 Loop Engine 实现，只有通过本规范，才可声明兼容 `agent-platform/v1alpha1`。

## 校验层级

| 层级 | 执行者 | 作用 |
|---|---|---|
| L1 | JSON Schema Draft 2020-12 | 结构、类型、枚举、格式、必填字段和未知字段 |
| L2 | Pydantic v2 / 等价实现 | 跨字段、集合、引用 Kind 与状态相关不变量 |
| L3 | 状态机执行器 | 状态迁移和终态约束 |
| L4 | Harness 策略执行器 | 权限、审批、幂等、副作用、租约、预算和 Secret |
| L5 | 集成测试 | Registry 解析、Checkpoint 恢复、事件投影和外部回执对账 |

本合同包实现 L1～L4 的参考行为。L5 属于 B1～B5 集成范围。

## 必须通过的测试组

### Schema

1. 17 份 Schema 均通过 Draft 2020-12 Meta-Schema 校验；
2. 根对象和所有显式值对象默认 `additionalProperties: false`；
3. 15 个有效示例分别通过对应 JSON Schema；
4. 结构型无效示例被 JSON Schema 拒绝；
5. 19 个无效示例全部被参考语义模型拒绝；
6. 定义引用不得出现 `latest`；
7. 定义资源必须带 Semantic Versioning 与内容摘要；
8. 运行资源不得使用定义对象的语义版本充当运行状态版本。

### 状态机

1. 所有目标状态必须已经声明；
2. 每个状态机必须有唯一初始状态；
3. 终态不能通过普通命令恢复；
4. 非法迁移返回 `STATE_TRANSITION_NOT_ALLOWED`；
5. 所有合法迁移都必须产生 Event；
6. `ToolCall.unknown` 不允许直接回到 `executing`。

### 权限与审批

1. 无决策时默认 `deny`；
2. 任意一层 `deny` 导致最终 `deny`；
3. `require_approval` 优先于普通 `allow`；
4. Skill 只能提出 PermissionRequest，不能产生授权；
5. `destructive`、`privileged` ToolCall 在 `scheduled` 前必须有有效 Approval；
6. Approval 必须绑定输入摘要、动作、资源和策略快照；
7. 一次性 Approval 使用后进入 `consumed`，不得再次使用。

### 幂等与副作用

1. Task Key 作用域为 `tenant + source + idempotency_key`；
2. ToolCall Key 作用域为 `tool + target_resource + idempotency_key`；
3. 有副作用 Tool 与 ToolCall 必须声明幂等；
4. `retryable`、`safe_to_retry` 和 Tool 策略必须同时允许，才能自动重试；
5. `unknown` 状态永不自动重试；
6. Checkpoint Side Effect Ledger 必须使用 ToolCall Ref。

### 租约与恢复

1. `acquired_at <= heartbeat_at < expires_at`；
2. Fencing Token 必须单调增加；
3. 只有当前 Token 持有者可以提交；
4. 租约到期后禁止提交；
5. Checkpoint Sequence 从 1 开始并严格递增；
6. Checkpoint 一经提交不可修改。

### 价格与预算

1. AgentRun 依赖快照必须包含 Model Price Snapshot；
2. Usage 必须引用同一价格快照；
3. `model_tokens = input_tokens + output_tokens`；
4. Run Usage 不得超过 Run Budget；
5. Run Budget 不得超过 Task 剩余 Budget；
6. 价格变化不得回写历史 Usage。

### 定义解析、动态依赖与模型切换

1. 新 Run 只能解析生命周期为 `active` 的定义；
2. 旧 Run 恢复可继续使用其已冻结且现为 `deprecated` 的精确版本；
3. `blocked` 定义对新 Run 和恢复均失败关闭，`archived` 定义必须迁移或终止；
4. 启动绑定依赖在 Run 启动前冻结，动态 Skill/Tool 在首次使用前冻结；
5. 动态依赖激活序列从 1 连续递增，历史只能追加，不能覆写或删除；
6. 同一精确依赖不得同时出现在启动快照和动态激活历史中；
7. 同 Run 模型 Fallback 必须使用冻结 ModelPolicy 中声明的路由与错误码，并满足原权限、地域、数据分类和预算约束；
8. 终态 Run、回退链耗尽、冻结依赖变化或策略约束不再满足时，模型切换必须创建新的 AgentRun；
9. 每次模型选择必须产生 Event，当前选择必须等于历史最后一条记录。

### Secret 与 Artifact

1. Secret 只能以 SecretRef 表示；
2. 有效示例不得包含原始凭证模式；
3. Artifact Locator 不得包含签名 URL 或凭证查询参数；
4. `confidential/restricted` Artifact 必须加密；
5. `available` Artifact 必须有摘要和大小；
6. 新内容必须新建 Artifact，通过 `supersedes` 关联。

## 错误码要求

错误码是平台级稳定契约，不直接复用 Pydantic 或具体 JSON Schema 引擎的内部错误类型。实现必须将底层校验错误映射为 `vocabularies/error-codes.json` 中的稳定错误码。

## 通过标准

- 测试失败数为 `0`；
- 重复副作用数为 `0`；
- Meta-Schema 错误数为 `0`；
- 有效示例通过率为 `100%`；
- 无效示例拒绝率为 `100%`；
- 未经人工接受，不得通过跳过测试、降低约束或删除无效示例达到通过状态。
