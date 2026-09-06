# B0 可执行契约包交付报告

交付日期：`2026-08-29`  
合同包版本：`0.2.0`  
API 版本：`agent-platform/v1alpha1`  
评审状态：`review_candidate`

## 交付结果

| 项目 | 数量 | 结果 |
|---|---:|---|
| 核心资源模型 | 15 | 通过 |
| 公共 Schema | 2 | 通过 |
| 资源 Schema | 15 | 通过 |
| 有效示例 | 15 | 全部通过 JSON Schema 与 Pydantic v2 |
| 无效示例 | 19 | 全部被 Pydantic v2 拒绝 |
| 状态机 | 6 | 状态目标与终态约束通过 |
| 一致性测试 | 31 | `31/31` 通过 |
| Python Wheel | 1 | 构建成功 |

## 已验证的不变量

- UUIDv7 与资源类型前缀；
- JSON Schema Draft 2020-12 Meta-Schema；
- 未知字段默认拒绝；
- 定义对象使用 Semantic Versioning；
- AgentRun 不允许 `latest` 依赖；
- CloudEvents 1.0 必要属性；
- 权限 `deny` 优先；
- Task 与 ToolCall 作用域化幂等；
- `ToolCall.unknown` 禁止自动重试；
- Lease 到期或 Fencing Token 过期时禁止提交；
- AgentRun 使用带版本的价格快照；
- 生成文件 SHA-256 摘要可复现；
- 有效示例中不存在已知原始凭证模式。
- 新 Run 与旧 Run 恢复采用不同的定义生命周期解析规则；
- 动态依赖首次使用前冻结，激活历史保持连续且只追加；
- 同 Run Fallback 与新 Run Restart 的边界由可执行策略测试覆盖；
- 模型当前选择与不可变选择历史保持一致。

## 设计落地澄清

1. Eval Suite 在当前 15 对象边界内使用 `ArtifactRef`；
2. Event 使用 CloudEvents 1.0 标准属性，并增加平台强类型扩展；
3. JSON Schema 与 Harness 语义验证是两层强制边界；
4. Model Price Snapshot 同时进入依赖快照和 Usage；
5. 定义资源 Metadata 与运行资源 Metadata 分离。
6. 启动绑定依赖与动态依赖采用分阶段冻结；
7. ModelPolicy 回退链内切换不增加 Run `attempt`，越界切换创建新 Run。

## 尚未声明完成的内容

- 用户尚未对本合同包完成最终评审；
- B0 主文档尚未从 `Reviewed` 更新为 `approved`；
- B1～B5 尚未承诺并验证不绕过本契约；
- Registry、数据库、API、Event Store、Harness 与 Loop Engine 尚未实现；
- 跨版本自动 Schema Diff 和旧 Run 恢复集成测试属于后续阶段。

因此，本交付物可以进入评审，但不得据此宣称 B0 已经最终完成，也不得直接跳过评审进入 B1 编码。
