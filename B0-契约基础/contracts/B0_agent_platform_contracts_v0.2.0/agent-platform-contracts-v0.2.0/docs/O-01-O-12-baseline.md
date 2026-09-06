# O-01～O-12 正式实现基线

确认日期：`2026-08-28`

| ID | 决策 | 在合同包中的落实 |
|---|---|---|
| O-01 | UUIDv7 + 类型前缀 | `ResourceId` 正则、Kind 与 ID 前缀语义校验 |
| O-02 | JSON Schema 2020-12 | 所有 Schema 的 `$schema` 与 Meta-Schema 测试 |
| O-03 | Pydantic v2 | `src/agent_platform_contracts/models.py` |
| O-04 | OpenAPI 3.1 | Schema 使用与 OpenAPI 3.1 相同的 2020-12 方言基础；API 文档留待 B1 |
| O-05 | `metadata/spec/status` | 15 个资源均使用统一三段式信封 |
| O-06 | CloudEvents 兼容信封 + 平台字段 | Event 使用 CloudEvents 1.0 标准属性并增加强类型引用、序列与 Trace |
| O-07 | RBAC + ABAC + Capability，Deny 优先 | PermissionProfile、PermissionDecision 与 `combine_permission_decisions` |
| O-08 | SHA-256 | Digest 正则、规范化 JSON 摘要和合同文件清单 |
| O-09 | Semantic Versioning | 定义资源与 ResourceRef 的版本正则及禁止 `latest` 测试 |
| O-10 | 作用域化 Idempotency Key | Task 与 ToolCall 的 Key、作用域摘要函数和测试 |
| O-11 | Lease + Heartbeat + Fencing Token | Lease 值对象、时间不变量与提交资格测试 |
| O-12 | 带版本的 Model Price Snapshot | AgentRun 依赖快照与 Usage 价格引用 |

