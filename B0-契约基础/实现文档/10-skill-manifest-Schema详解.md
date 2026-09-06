# JSON Schema 定义对象详解 - skill-manifest.schema.json

> 文件位置：`schemas/definitions/skill-manifest.schema.json`
> 作用：定义 SkillManifest 资源对象的结构

---

## 一、Skill 是什么？

**Skill（技能）** 是可移植、按需加载的程序性知识与任务 SOP。

**类比**：
- AgentSpec ≈ 一个岗位（如"客服"）
- Skill ≈ 一个技能证书（如"处理退款"）
- 一个岗位可以有多个技能
- 一个技能可以被多个岗位使用

**Skill Bundle 结构**：
```
skill-name/
├── SKILL.md          # 技能说明文档
├── scripts/          # 脚本
├── references/       # 参考资料
├── assets/           # 资源文件
└── evals/            # 评估用例
```

---

## 二、核心字段详解

### 2.1 portable_name（可移植名称）

```json
"portable_name": {
  "type": "string",
  "pattern": "^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$",
  "description": "与 SKILL.md 中的名称一致，用于跨平台移植"
}
```

**约束解析**：
- 只能包含小写字母、数字、连字符
- 不能以连字符开头或结尾
- 长度 3-64 字符

**有效示例**：
- `code-review`
- `live-clip-workflow`
- `presale-consultant`

**为什么需要 portable_name？**
- **跨平台移植**：Skill 可以从一个平台复制到另一个平台
- **SKILL.md 一致**：与文档中的名称保持同步
- **唯一标识**：在全局范围内唯一

---

### 2.2 description（描述）

```json
"description": {
  "type": "string",
  "minLength": 20,
  "maxLength": 2048,
  "description": "何时使用、解决什么问题（至少20字符）"
}
```

**为什么要求至少 20 字符？**
- **充分描述**：太短的描述无法说明技能用途
- **触发判断**：模型需要足够信息判断何时使用
- **文档质量**：保证基本的文档质量

**示例**：
```
"This skill performs automated code review with security checks,
identifying potential vulnerabilities and code quality issues."
```

---

### 2.3 domain（领域）

```json
"domain": {
  "type": "array",
  "items": {
    "type": "string",
    "pattern": "^[a-z][a-z0-9_-]{1,63}$"
  },
  "minItems": 1,
  "description": "所属领域，可多值"
}
```

**为什么是数组？**
- 一个技能可以属于多个领域
- 便于按领域分类和检索

**示例**：
```json
"domain": ["development", "security"]
"domain": ["ecommerce", "customer_service"]
```

---

### 2.4 trigger_examples（触发示例）

```json
"trigger_examples": {
  "type": "object",
  "properties": {
    "positive": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    },
    "negative": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    }
  },
  "required": ["positive", "negative"]
}
```

**为什么必须有正例和反例？**

**正例（应该触发）**：
```json
"positive": [
  "Review this code for security issues",
  "Check if this function has vulnerabilities"
]
```

**反例（不应该触发）**：
```json
"negative": [
  "Write new code",
  "Deploy to production"
]
```

**作用**：
1. **触发判断**：模型根据示例判断何时使用技能
2. **评估测试**：用于计算触发精确率和召回率
3. **防止误触发**：明确什么场景不应该使用

**评估指标**：
- **精确率**：触发的请求中，有多少是正确的？
- **召回率**：应该触发的请求中，有多少被正确触发？

---

### 2.5 required_tools（所需工具）

```json
"required_tools": {
  "type": "array",
  "items": {
    "$ref": "#/$defs/ToolRequirement"
  }
}
```

**ToolRequirement 结构**：
```json
{
  "tool_ref": {
    "kind": "ToolManifest",
    "id": "tol_0198f6d0-...",
    "version": "1.0.0",
    "digest": "sha256:..."
  },
  "required_capabilities": ["speech_to_text", "video_cut"]
}
```

**为什么声明工具依赖？**
- **前置检查**：执行前验证工具是否可用
- **版本兼容**：确保工具版本满足最低要求
- **能力声明**：明确需要工具的哪些能力

---

### 2.6 required_skills（技能依赖）

```json
"required_skills": {
  "type": "array",
  "items": {
    "$ref": "#/$defs/SkillRequirement"
  }
}
```

**SkillRequirement 结构**：
```json
{
  "skill_ref": {
    "kind": "SkillManifest",
    "id": "skl_0198f6d0-...",
    "version": "1.0.0",
    "digest": "sha256:..."
  },
  "optional": false
}
```

**optional 字段**：
- `false`：必需依赖，缺失则无法执行
- `true`：可选依赖，缺失仍可执行但功能受限

**为什么有技能依赖？**
- **技能复用**：复杂技能可以组合简单技能
- **模块化**：避免重复实现通用功能

---

### 2.7 conflicts_with（冲突技能）

```json
"conflicts_with": {
  "type": "array",
  "items": {
    "$ref": "#/$defs/ResourceRef"
  },
  "description": "显式冲突的技能"
}
```

**冲突场景**：
- 同名不同来源的技能
- 指令冲突的技能
- 工具和权限冲突的技能

**示例**：
```json
"conflicts_with": [
  {
    "kind": "SkillManifest",
    "id": "skl_old_code_review",
    "version": "1.0.0",
    "digest": "sha256:..."
  }
]
```

**为什么需要冲突声明？**
- **防止歧义**：多个技能同时激活可能导致行为不确定
- **明确选择**：强制用户选择使用哪个技能
- **向后兼容**：新版本技能可以声明与旧版本冲突

---

### 2.8 permission_requirements（权限需求）

```json
"permission_requirements": {
  "type": "array",
  "items": {
    "$ref": "#/$defs/PermissionRequest"
  },
  "description": "请求但不授予权限"
}
```

**PermissionRequest 结构**：
```json
{
  "actions": ["repository.read", "file.write"],
  "resources": ["project:prj_demo/repository:*"],
  "conditions": {
    "environment": ["development", "sandbox"]
  }
}
```

**关键设计**：
- **只请求，不授予**：Skill 不能自己给自己权限
- **Harness 验证**：运行时由 Harness 检查是否满足
- **最小权限**：只请求必需的权限

---

### 2.9 risk_level（风险级别）

```json
"risk_level": {
  "type": "string",
  "enum": ["low", "medium", "high", "critical"]
}
```

**风险级别对照表**：

| 级别 | 说明 | 审批要求 | 示例 |
|---|---|---|---|
| `low` | 低风险 | 无需审批 | 查询信息 |
| `medium` | 中等风险 | 可能需要审批 | 生成内容 |
| `high` | 高风险 | 需要审批 | 修改数据 |
| `critical` | 关键风险 | 必须审批 | 删除数据、部署 |

---

### 2.10 runtime_requirements（运行时需求）

```json
"runtime_requirements": {
  "type": "object",
  "properties": {
    "operating_systems": { ... },
    "binaries": { ... },
    "network_domains": { ... },
    "has_scripts": { "type": "boolean" },
    "sandbox_required": { "type": "boolean" },
    "sandbox_profile": { ... }
  }
}
```

**字段说明**：

| 字段 | 作用 | 示例 |
|---|---|---|
| `operating_systems` | 支持的操作系统 | `["linux", "macos"]` |
| `binaries` | 依赖的命令行工具 | `["ffmpeg", "git"]` |
| `network_domains` | 需要访问的域名 | `["api.example.com"]` |
| `has_scripts` | 是否包含脚本 | `true` |
| `sandbox_required` | 是否需要沙箱 | `true` |
| `sandbox_profile` | 沙箱配置名 | `"video_processing"` |

**沙箱设计**：
```json
// 有脚本必须有沙箱
"has_scripts": true  →  "sandbox_required": true, "sandbox_profile": "xxx"
```

**为什么需要沙箱？**
- **隔离执行**：防止恶意代码影响宿主机
- **资源限制**：限制 CPU、内存、网络访问
- **安全边界**：Skill 默认不可信

---

### 2.11 context_budget（Context 预算）

```json
"context_budget": {
  "type": "object",
  "properties": {
    "max_skill_tokens": { "type": "integer", "exclusiveMinimum": 0 },
    "max_reference_tokens": { "type": "integer", "minimum": 0 },
    "max_total_tokens": { "type": "integer", "exclusiveMinimum": 0 }
  }
}
```

**预算分配**：
```
max_total_tokens (总预算)
├── max_skill_tokens (技能内容)
└── max_reference_tokens (参考资料)
```

**约束**：
```
max_skill_tokens + max_reference_tokens <= max_total_tokens
```

**为什么需要 Context 预算？**
- **Token 限制**：模型有 Token 上限
- **成本控制**：Token 越多，成本越高
- **优先级管理**：确保重要信息不被截断

---

### 2.12 bundle_artifact_ref（发布包引用）

```json
"bundle_artifact_ref": {
  "$ref": "#/$defs/ArtifactRef",
  "description": "不可变发布包引用"
}
```

**ArtifactRef 结构**：
```json
{
  "kind": "Artifact",
  "id": "art_0198f6d0-...",
  "digest": "sha256:..."
}
```

**为什么是不可变的？**
- **版本锁定**：发布后内容不能修改
- **可追溯**：通过 digest 验证内容完整性
- **安全**：防止发布后被篡改

---

### 2.13 source_repository（源码仓库）

```json
"source_repository": {
  "type": "object",
  "properties": {
    "repository": { "type": "string" },
    "commit": { "type": "string", "pattern": "^[0-9a-f]{40}$" },
    "path": { "type": "string" }
  }
}
```

**commit 字段**：
- 必须是 40 位十六进制（Git SHA-1）
- 精确到具体的代码版本

**示例**：
```json
{
  "repository": "https://github.com/example/skills",
  "commit": "a1b2c3d4e5f6...",
  "path": "skills/code-review"
}
```

**为什么记录源码仓库？**
- **可追溯**：从发布包追溯到源码
- **审计**：审查代码变更历史
- **重建**：可以从源码重新构建

---

### 2.14 eval_summary（评估摘要）

```json
"eval_summary": {
  "type": "object",
  "properties": {
    "trigger_precision": { "type": "number", "minimum": 0, "maximum": 1 },
    "trigger_recall": { "type": "number", "minimum": 0, "maximum": 1 },
    "output_pass_rate": { "type": "number", "minimum": 0, "maximum": 1 },
    "security_passed": { "type": "boolean" },
    "regression_passed": { "type": "boolean" },
    "evaluated_cases": { "type": "integer", "exclusiveMinimum": 0 },
    "evaluated_at": { "type": "string", "format": "date-time" }
  }
}
```

**评估指标**：

| 指标 | 说明 | 目标 |
|---|---|---|
| `trigger_precision` | 触发精确率 | > 0.9 |
| `trigger_recall` | 触发召回率 | > 0.8 |
| `output_pass_rate` | 输出通过率 | > 0.85 |
| `security_passed` | 安全评估 | 必须 true |
| `regression_passed` | 回归测试 | 必须 true |

**active 状态要求**：
```python
if status.phase == "active":
    assert eval_summary.security_passed == True
    assert eval_summary.regression_passed == True
```

---

### 2.15 provenance（来源）

```json
"provenance": {
  "type": "object",
  "properties": {
    "type": { "enum": ["human", "hermes_proposal", "external", "imported"] },
    "actor": { "$ref": "#/$defs/ActorRef" },
    "source_ref": { "type": "string" }
  }
}
```

**来源类型**：

| 类型 | 说明 | 限制 |
|---|---|---|
| `human` | 人工创建 | 无限制 |
| `hermes_proposal` | AI 提案 | 只能是 proposed 或 draft |
| `external` | 外部来源 | 需要审查 |
| `imported` | 导入 | 需要验证 |

**Hermes 提案限制**：
```python
if provenance.type == "hermes_proposal":
    assert status.phase in ["proposed", "draft"]
```

**为什么限制 AI 提案？**
- **安全考虑**：AI 生成的技能需要人工审查
- **质量控制**：防止低质量技能进入生产
- **信任边界**：Skill 默认不可信

---

## 三、关键设计决策总结

### 1. 为什么需要 trigger_examples？

- **触发判断**：模型根据示例判断何时使用
- **评估测试**：计算精确率和召回率
- **防止误触发**：明确边界

### 2. 为什么有沙箱要求？

- **安全隔离**：Skill 脚本可能包含恶意代码
- **资源限制**：防止资源耗尽攻击
- **信任边界**：Skill 默认不可信

### 3. 为什么限制 AI 提案？

- **安全审查**：AI 生成内容需要人工验证
- **质量保证**：防止低质量技能
- **责任明确**：人工对技能质量负责

### 4. 为什么需要评估摘要？

- **质量门禁**：active 状态必须通过评估
- **可观测性**：追踪技能质量
- **持续改进**：基于评估结果优化

---

## 四、下一步

接下来我们将创建：
- tool-manifest.schema.json（工具清单）
- 其他定义对象 Schema
