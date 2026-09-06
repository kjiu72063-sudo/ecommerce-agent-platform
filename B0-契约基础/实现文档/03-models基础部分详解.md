# 第三步：models.py 基础部分详解

> 已完成文件：`src/agent_platform_contracts/models.py`（基础部分）

---

## 已实现的内容

### 1. 常量定义

```python
API_VERSION = "agent-platform/v1alpha1"  # API 版本
SEMVER_PATTERN = r"^..."                  # 语义版本正则
DIGEST_PATTERN = r"^sha256:..."          # SHA-256 摘要正则
UUID7_PATTERN = r"..."                   # UUIDv7 正则
RESOURCE_ID_PATTERN = r"..."             # 资源 ID 正则
```

**为什么需要这些正则？**
- 用于 Pydantic 的字段验证
- 确保数据格式正确
- 防止非法数据进入系统

### 2. 类型别名

```python
SemVer = Annotated[str, Field(pattern=SEMVER_PATTERN)]      # 语义版本
Digest = Annotated[str, Field(pattern=DIGEST_PATTERN)]      # 内容摘要
ResourceId = Annotated[str, Field(pattern=RESOURCE_ID_PATTERN)]  # 资源 ID
Key = Annotated[str, Field(pattern=KEY_PATTERN, min_length=3, max_length=128)]  # 标识符
Namespace = Annotated[str, Field(pattern=NAMESPACE_PATTERN, min_length=2, max_length=128)]  # 命名空间
```

**Annotated 的作用**：
- `Annotated[str, Field(pattern=...)]` 表示"带约束的字符串"
- Pydantic 会自动验证字段是否符合约束

### 3. 资源类型枚举

```python
class ResourceKind(StrEnum):
    AGENT_SPEC = "AgentSpec"           # Agent 定义
    SKILL_MANIFEST = "SkillManifest"   # 技能清单
    TOOL_MANIFEST = "ToolManifest"     # 工具清单
    # ... 共 15 种
```

**StrEnum 的作用**：
- 继承自 `str` 和 `Enum`
- 枚举值可以直接当字符串使用
- 比普通枚举更方便

### 4. 作用域验证

```python
class Scope(StrictModel):
    type: ScopeType
    tenant_id: ResourceId | None = None
    user_id: ResourceId | None = None
    project_id: ResourceId | None = None
    session_id: str | None = None

    @model_validator(mode="after")
    def validate_scope_members(self) -> Scope:
        # 验证逻辑
        if self.type != ScopeType.SYSTEM and self.tenant_id is None:
            raise ValueError("tenant_id is required outside system scope")
        # ...
```

**验证规则**：
- 系统级作用域：不需要任何 ID
- 租户级：需要 tenant_id
- 用户级：需要 tenant_id + user_id
- 项目级：需要 tenant_id + user_id + project_id
- 会话级：需要所有 ID

### 5. Actor 引用

```python
class ActorRef(StrictModel):
    actor_type: ActorType   # user / agent / service / system
    actor_id: NonEmptyString
    tenant_id: ResourceId | None = None
```

**前缀验证**：
- user 类型的 actor_id 必须以 `usr_` 开头
- agent 类型的 actor_id 必须以 `agt_` 开头

---

## 关键设计决策

### 为什么使用 Pydantic v2？

1. **类型安全**：自动验证字段类型
2. **约束验证**：支持正则、范围等约束
3. **跨字段验证**：`model_validator` 支持复杂业务规则
4. **序列化**：自动转换为 JSON
5. **性能**：比 v1 快 5-50 倍

### 为什么禁止额外字段？

```python
model_config = ConfigDict(extra="forbid")
```

- 防止拼写错误导致的静默失败
- 确保数据结构严格一致
- 便于发现未知字段

---

## 下一步

接下来我们将添加：
- DefinitionMetadata（定义对象元数据）
- RuntimeMetadata（运行对象元数据）
- ResourceRef（资源引用）
- SchemaRef（Schema 引用）
- Budget（预算）
- StandardError（标准错误）
