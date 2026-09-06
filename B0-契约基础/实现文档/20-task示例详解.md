# 示例文件详解 - task.json

> 文件位置：`examples/valid/task.json`
> 作用：展示一个有效的 Task 资源对象

---

## 一、文件结构

```json
{
  "api_version": "...",   // API 版本
  "kind": "...",          // 资源类型
  "metadata": { ... },    // 元数据
  "spec": { ... },        // 核心规格
  "status": { ... }       // 状态
}
```

**统一资源信封**：所有资源对象都遵循这个结构

---

## 二、逐字段详解

### 2.1 api_version

```json
"api_version": "agent-platform/v1alpha1"
```

**作用**：声明使用的 API 版本

**为什么是 v1alpha1？**
- 表示这是初始版本
- 后续可能有不兼容变更
- 正式发布后会是 v1

### 2.2 kind

```json
"kind": "Task"
```

**作用**：声明资源类型

**必须是 15 种之一**：
- 定义对象：AgentSpec, SkillManifest, ToolManifest, PromptPackage, ModelPolicy, ContextPolicy, LoopProfile, PermissionProfile
- 运行对象：Task, AgentRun, Checkpoint, ToolCall, Approval, Artifact, Event

### 2.3 metadata（元数据）

```json
"metadata": {
  "id": "tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
  "revision": 1,
  "scope": { ... },
  "labels": { ... },
  "annotations": { ... },
  "created_at": "2026-09-01T12:00:00Z",
  "created_by": { ... }
}
```

#### id（资源 ID）

```json
"id": "tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"
```

**格式**：`类型前缀 + UUIDv7`

**解析**：
- `tsk_` - Task 的类型前缀
- `0198f6d0` - 时间戳部分
- `7ef0-7b0e` - UUIDv7 版本标识（必须是 7）
- `a0d3-5f9c96c7f411` - 随机部分

**为什么用 UUIDv7？**
- **时间有序**：按时间排序，便于索引
- **全局唯一**：几乎不可能冲突
- **分布式安全**：无需中央协调

#### revision（修订号）

```json
"revision": 1
```

**作用**：乐观并发控制

**使用场景**：
```python
# 更新时检查 revision
update_task(id, revision=1, new_data={...})
# 如果 revision 已被其他人修改为 2，更新失败
```

#### scope（作用域）

```json
"scope": {
  "type": "project",
  "tenant_id": "ten_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
  "user_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
  "project_id": "prj_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"
}
```

**作用域层级**：
```
system → tenant → user → project → session
```

**验证规则**：
- `project` 作用域必须有 `tenant_id`, `user_id`, `project_id`
- 所有 ID 必须使用正确前缀

#### labels（标签）

```json
"labels": {
  "domain": "development",
  "priority": "high"
}
```

**作用**：查询过滤

**使用场景**：
```sql
SELECT * FROM tasks WHERE labels->>'domain' = 'development'
```

#### created_at（创建时间）

```json
"created_at": "2026-09-01T12:00:00Z"
```

**格式**：RFC 3339（ISO 8601）

**必须带时区**：`Z` 表示 UTC

#### created_by（创建者）

```json
"created_by": {
  "actor_type": "user",
  "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
  "tenant_id": "ten_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"
}
```

**Actor 类型**：
- `user` - 用户
- `agent` - Agent
- `service` - 服务
- `system` - 系统

---

### 2.4 spec（核心规格）

#### title（标题）

```json
"title": "为项目增加用户设置页面"
```

**作用**：人类可读标题

**约束**：1-256 字符

#### intent（意图）

```json
"intent": "development.implement_feature"
```

**格式**：`领域.动作`

**作用**：
- 路由依据：根据意图选择 Agent
- 分类统计：按意图统计任务量

**示例**：
- `development.implement_feature` - 实现功能
- `ecommerce.presale_consultation` - 售前咨询
- `content.generate_article` - 生成文章

#### domain（领域）

```json
"domain": "development"
```

**作用**：业务领域标识

**约束**：小写字母、数字、下划线、连字符

#### requested_by（请求者）

```json
"requested_by": {
  "actor_type": "user",
  "actor_id": "usr_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"
}
```

**作用**：记录谁发起了这个任务

#### source（来源）

```json
"source": {
  "type": "openclaw",
  "channel": "feishu",
  "source_message_id": "msg_12345"
}
```

**来源类型**：
| 类型 | 说明 |
|---|---|
| `openclaw` | OpenClaw 平台 |
| `api` | API 调用 |
| `cron` | 定时任务 |
| `webhook` | Webhook |
| `ui` | 用户界面 |
| `system` | 系统内部 |

**作用**：追踪任务来源

#### payload（负载）

```json
"payload": {
  "repository_ref": "repo_demo",
  "requirement_artifact_ref": "art_requirement",
  "description": "实现用户设置页面..."
}
```

**作用**：任务输入数据

**可以是**：
- 内联 JSON 对象（如本例）
- ArtifactRef（大文件引用）

#### input_schema_ref（输入 Schema）

```json
"input_schema_ref": {
  "id": "sch_programming_task",
  "version": "1.0.0",
  "digest": "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

**作用**：定义 payload 应该符合的 Schema

**为什么需要 Schema？**
- **验证输入**：确保 payload 格式正确
- **文档化**：明确输入格式
- **兼容性**：版本控制

#### expected_output_schema_ref（期望输出 Schema）

```json
"expected_output_schema_ref": {
  "id": "sch_programming_result",
  "version": "1.0.0",
  "digest": "sha256:a7ffc6f8bf1ed76651c14756a061d662f580ff4de43b49fa82d80a4b80f8434a"
}
```

**作用**：定义期望的输出格式

**为什么需要期望输出？**
- **验证结果**：确保输出符合预期
- **契约**：明确任务成功的标准

#### budget（预算）

```json
"budget": {
  "max_wall_time_seconds": 7200,
  "max_model_input_tokens": 500000,
  "max_model_output_tokens": 200000,
  "max_model_tokens": 800000,
  "max_cost_usd": "30.00",
  "max_tool_calls": 100,
  "max_iterations": 20
}
```

**字段说明**：
| 字段 | 值 | 说明 |
|---|---|---|
| `max_wall_time_seconds` | 7200 | 最大执行时间 2 小时 |
| `max_model_tokens` | 800000 | 最大 Token 80 万 |
| `max_cost_usd` | "30.00" | 最大费用 30 美元 |
| `max_tool_calls` | 100 | 最大工具调用 100 次 |
| `max_iterations` | 20 | 最大迭代 20 次 |

**为什么费用用字符串？**
- JSON number 有精度限制
- 字符串可以精确表示

#### permission_grant（权限授予）

```json
"permission_grant": {
  "actions": ["repository.read", "repository.write", "file.read", "file.write"],
  "resources": ["project:prj_demo/repository:*"],
  "expires_at": "2026-09-02T12:00:00Z"
}
```

**作用**：本任务的权限范围

**关键设计**：
- **最小权限**：只授予必需的权限
- **有过期时间**：任务结束后权限失效
- **资源限定**：只能访问指定资源

#### idempotency_key（幂等键）

```json
"idempotency_key": "openclaw:feishu:message-12345"
```

**作用域**：`tenant + source + idempotency_key`

**为什么需要幂等键？**
- **防重复创建**：相同请求不会创建两个 Task
- **安全重试**：网络失败可以安全重试

#### retention_policy（保留策略）

```json
"retention_policy": {
  "retain_days": 90,
  "legal_hold": false
}
```

**字段说明**：
- `retain_days`: 保留 90 天
- `legal_hold`: 无法律保留

**为什么需要保留策略？**
- **数据生命周期**：自动清理旧数据
- **合规要求**：满足数据保留法规
- **存储优化**：释放存储空间

---

### 2.5 status（状态）

```json
"status": {
  "phase": "created"
}
```

**Task 生命周期**：
```
created → validated → queued → running → succeeded/failed/cancelled/expired
```

**当前状态**：`created` - 任务刚创建

---

## 三、关键设计总结

### 1. 统一资源信封

```json
{
  "api_version": "...",
  "kind": "...",
  "metadata": { ... },
  "spec": { ... },
  "status": { ... }
}
```

**好处**：
- 统一处理方式
- 便于通用工具开发
- 类似 Kubernetes 设计

### 2. 强类型引用

```json
"input_schema_ref": {
  "id": "sch_programming_task",
  "version": "1.0.0",
  "digest": "sha256:..."
}
```

**好处**：
- 精确版本
- 防篡改
- 可追溯

### 3. 幂等控制

```json
"idempotency_key": "openclaw:feishu:message-12345"
```

**好处**：
- 防重复创建
- 安全重试

### 4. 预算控制

```json
"budget": {
  "max_wall_time_seconds": 7200,
  "max_cost_usd": "30.00"
}
```

**好处**：
- 成本控制
- 资源保护

---

## 四、下一步

继续创建更多示例文件：
- agent-spec.json
- skill-manifest.json
- tool-manifest.json
- prompt-package.json
- 等等
