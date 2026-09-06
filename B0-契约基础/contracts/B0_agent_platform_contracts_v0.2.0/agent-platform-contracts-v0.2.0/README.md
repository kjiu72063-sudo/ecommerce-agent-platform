# Agent Platform B0 Contracts

> 合同包版本：`0.2.0`  
> API 版本：`agent-platform/v1alpha1`  
> 当前状态：`review_candidate`  
> 基线文档：`B0 Agent 底层对象与协议详细设计 v0.3.0-rc.1`

本目录是多智能体底层平台 B0 阶段的可执行契约包。它将 B0 设计文档中的对象、状态机、版本、权限、幂等、租约和安全约束落实为 JSON Schema、Pydantic v2 模型、示例及一致性测试。

当前不包含数据库表、API 服务、消息队列、Registry、Harness 或业务 Agent 实现。

## 交付范围

- 15 个核心资源模型：8 个定义资源、7 个运行资源；
- 2 份公共 Schema：公共类型目录与 `StandardError`；
- 17 份 JSON Schema Draft 2020-12；
- 15 个有效示例；
- 19 个无效示例及预期平台错误码；
- 6 个显式状态机；
- Pydantic v2 参考模型；
- 权限、摘要、解析生命周期、动态激活、模型切换、幂等、重试与租约参考函数；
- 31 项一致性测试；
- 兼容性和测试规范。

## 目录

```text
agent-platform-contracts/
├── schemas/
│   ├── common/
│   ├── definitions/
│   └── runtime/
├── examples/
│   ├── valid/
│   └── invalid/
├── state-machines/
├── vocabularies/
├── compatibility/
├── conformance/
├── docs/
├── scripts/
└── src/agent_platform_contracts/
```

## 权威关系

```text
B0 设计文档
→ Pydantic v2 参考模型与显式状态机
→ JSON Schema、示例、状态机 JSON、合同清单
→ 一致性测试
```

- `models.py` 负责字段类型和跨字段语义不变量；
- JSON Schema 负责跨语言结构校验；
- `state_machines.py` 负责合法状态迁移；
- Harness 后续必须同时执行 Schema 校验和语义校验，不能只执行其中一层；
- `contract-manifest.json` 保存所有生成文件的 SHA-256 摘要。

## 生成合同

```bash
python -m pip install -r requirements-dev.txt
PYTHONPATH=src python scripts/export_contracts.py
```

重复生成必须得到稳定内容和摘要。生成脚本不会修改源模型。

## 运行测试

```bash
PYTHONPATH=src python conformance/run.py
```

预期结果：

```text
Ran 31 tests
OK
```

## 双层校验

### JSON Schema 层

校验：

- 必填字段；
- 类型、枚举、格式和正则；
- 未声明字段拒绝；
- UUIDv7 类型前缀；
- Semantic Versioning；
- SHA-256 摘要；
- 基础长度和数值边界。

### Harness 语义层

通过 Pydantic v2 验证器和策略函数强制：

- Skill 自动提案不能直接激活；
- 有副作用 Tool 必须支持幂等；
- 高风险 ToolCall 执行前必须绑定审批；
- 模型路由供应商必须处于白名单；
- Context 分项预算不能超过总预算；
- Prompt 片段顺序不能重复；
- 一次性 Approval 不能重复消费；
- 敏感 Artifact 必须加密；
- Event 的 CloudEvents `id` 必须与资源 `metadata.id` 一致；
- Worker 必须持有当前 Fencing Token 才能提交。
- 新 Run 只能解析 `active` 定义，旧 Run 恢复可继续使用已冻结的 `deprecated` 定义；
- 动态 Skill/Tool 必须在首次使用前冻结，并以只追加历史记录激活；
- ModelPolicy 声明范围内的 Fallback 保持在同一 Run，越出冻结边界则创建新 Run。

JSON Schema 无法完整表达所有集合关系、状态相关约束和运行时授权规则，因此生产 Harness 不得把 JSON Schema 当成唯一安全边界。

## 当前评审结论

本合同包已经通过本地一致性测试，但仍标记为 `review_candidate`。只有用户完成契约评审并确认后，B0 主文档才适合进入 `approved`；在此之前不得开始 B1 实现。
