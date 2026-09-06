"""B0 contract reference models.

The models are the executable source for the JSON Schema 2020-12 artifacts.
They intentionally reject undeclared fields and encode cross-field invariants
that JSON Schema alone cannot express without implementation-specific code.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================
# 常量定义
# ============================================================

# API 版本
API_VERSION = "agent-platform/v1alpha1"

# 语义版本正则：匹配 1.0.0, 2.1.3-beta.1 等格式
SEMVER_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"

# SHA-256 摘要正则：sha256: 后跟 64 位十六进制
DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"

# UUIDv7 正则：版本号必须是 7
UUID7_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"

# 资源 ID 正则：类型前缀 + UUIDv7
RESOURCE_ID_PATTERN = rf"^(?:ten|usr|prj|agt|skl|tol|prm|mpo|cpo|lop|pep|tsk|run|ckp|tcl|apr|art|evt)_{UUID7_PATTERN}$"

# Schema ID 正则
SCHEMA_ID_PATTERN = r"^sch_[a-z0-9][a-z0-9._-]{2,127}$"

# Key 正则（人类可读标识）
KEY_PATTERN = r"^[a-z0-9][a-z0-9-]{1,126}[a-z0-9]$"

# Namespace 正则
NAMESPACE_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,126}[a-z0-9]$"


# ============================================================
# 类型别名
# ============================================================

# 语义版本类型
SemVer = Annotated[str, Field(pattern=SEMVER_PATTERN)]

# 内容摘要类型
Digest = Annotated[str, Field(pattern=DIGEST_PATTERN)]

# 资源 ID 类型
ResourceId = Annotated[str, Field(pattern=RESOURCE_ID_PATTERN)]

# Schema ID 类型
SchemaId = Annotated[str, Field(pattern=SCHEMA_ID_PATTERN)]

# Key 类型
Key = Annotated[str, Field(pattern=KEY_PATTERN, min_length=3, max_length=128)]

# Namespace 类型
Namespace = Annotated[str, Field(pattern=NAMESPACE_PATTERN, min_length=2, max_length=128)]

# 非空字符串类型
NonEmptyString = Annotated[str, Field(min_length=1, max_length=4096)]


# ============================================================
# 资源类型与前缀映射
# ============================================================

class ResourceKind(StrEnum):
    """15 种核心资源类型"""
    AGENT_SPEC = "AgentSpec"
    SKILL_MANIFEST = "SkillManifest"
    TOOL_MANIFEST = "ToolManifest"
    PROMPT_PACKAGE = "PromptPackage"
    MODEL_POLICY = "ModelPolicy"
    CONTEXT_POLICY = "ContextPolicy"
    LOOP_PROFILE = "LoopProfile"
    PERMISSION_PROFILE = "PermissionProfile"
    TASK = "Task"
    AGENT_RUN = "AgentRun"
    CHECKPOINT = "Checkpoint"
    TOOL_CALL = "ToolCall"
    APPROVAL = "Approval"
    ARTIFACT = "Artifact"
    EVENT = "Event"


# 定义对象集合（8个）
DEFINITION_KINDS = {
    ResourceKind.AGENT_SPEC,
    ResourceKind.SKILL_MANIFEST,
    ResourceKind.TOOL_MANIFEST,
    ResourceKind.PROMPT_PACKAGE,
    ResourceKind.MODEL_POLICY,
    ResourceKind.CONTEXT_POLICY,
    ResourceKind.LOOP_PROFILE,
    ResourceKind.PERMISSION_PROFILE,
}

# 资源类型 → ID 前缀映射
KIND_PREFIX: dict[str, str] = {
    ResourceKind.AGENT_SPEC: "agt_",
    ResourceKind.SKILL_MANIFEST: "skl_",
    ResourceKind.TOOL_MANIFEST: "tol_",
    ResourceKind.PROMPT_PACKAGE: "prm_",
    ResourceKind.MODEL_POLICY: "mpo_",
    ResourceKind.CONTEXT_POLICY: "cpo_",
    ResourceKind.LOOP_PROFILE: "lop_",
    ResourceKind.PERMISSION_PROFILE: "pep_",
    ResourceKind.TASK: "tsk_",
    ResourceKind.AGENT_RUN: "run_",
    ResourceKind.CHECKPOINT: "ckp_",
    ResourceKind.TOOL_CALL: "tcl_",
    ResourceKind.APPROVAL: "apr_",
    ResourceKind.ARTIFACT: "art_",
    ResourceKind.EVENT: "evt_",
}


# ============================================================
# 基础模型配置
# ============================================================

class StrictModel(BaseModel):
    """严格模型基类：禁止未声明字段，启用字符串去空格"""
    model_config = ConfigDict(
        extra="forbid",              # 禁止额外字段
        str_strip_whitespace=True,   # 自动去除字符串首尾空格
        validate_assignment=True,    # 赋值时也验证
        use_enum_values=True,        # 使用枚举值而非枚举对象
        protected_namespaces=(),     # 禁用 model_ 保护命名空间（本领域合法使用 model_ 前缀）
    )


# ============================================================
# 作用域类型
# ============================================================

class ScopeType(StrEnum):
    """作用域类型"""
    SYSTEM = "system"      # 系统级
    TENANT = "tenant"      # 租户级
    USER = "user"          # 用户级
    PROJECT = "project"    # 项目级
    SESSION = "session"    # 会话级


class Scope(StrictModel):
    """作用域定义"""
    type: ScopeType
    tenant_id: ResourceId | None = None
    user_id: ResourceId | None = None
    project_id: ResourceId | None = None
    session_id: Annotated[str, Field(pattern=r"^ses_[A-Za-z0-9._:-]{3,128}$")] | None = None

    @model_validator(mode="after")
    def validate_scope_members(self) -> Scope:
        """验证作用域成员的完整性"""
        # 非系统作用域必须有租户 ID
        if self.type != ScopeType.SYSTEM and self.tenant_id is None:
            raise ValueError("tenant_id is required outside system scope")
        
        # 租户 ID 必须使用 ten_ 前缀
        if self.tenant_id is not None and not self.tenant_id.startswith("ten_"):
            raise ValueError("tenant_id must use ten_ prefix")
        
        # 用户级及以上作用域必须有用户 ID
        if self.type in {ScopeType.USER, ScopeType.PROJECT, ScopeType.SESSION} and self.user_id is None:
            raise ValueError("user_id is required for user, project, and session scope")
        
        # 用户 ID 必须使用 usr_ 前缀
        if self.user_id is not None and not self.user_id.startswith("usr_"):
            raise ValueError("user_id must use usr_ prefix")
        
        # 项目级和会话级必须有项目 ID
        if self.type in {ScopeType.PROJECT, ScopeType.SESSION} and self.project_id is None:
            raise ValueError("project_id is required for project and session scope")
        
        # 项目 ID 必须使用 prj_ 前缀
        if self.project_id is not None and not self.project_id.startswith("prj_"):
            raise ValueError("project_id must use prj_ prefix")
        
        # 会话级必须有会话 ID
        if self.type == ScopeType.SESSION and self.session_id is None:
            raise ValueError("session_id is required for session scope")
        
        return self


# ============================================================
# Actor 引用
# ============================================================

class ActorType(StrEnum):
    """Actor 类型"""
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"
    SYSTEM = "system"


class ActorRef(StrictModel):
    """Actor 引用"""
    actor_type: ActorType
    actor_id: NonEmptyString
    tenant_id: ResourceId | None = None

    @model_validator(mode="after")
    def validate_actor_prefix(self) -> ActorRef:
        """验证 Actor ID 前缀"""
        expected = {"user": "usr_", "agent": "agt_"}.get(str(self.actor_type))
        if expected and not self.actor_id.startswith(expected):
            raise ValueError(f"actor_id must use {expected} prefix for {self.actor_type}")
        if self.tenant_id is not None and not self.tenant_id.startswith("ten_"):
            raise ValueError("tenant_id must use ten_ prefix")
        return self


# ============================================================
# 元数据定义
# ============================================================

class DefinitionMetadata(StrictModel):
    """定义对象的元数据（用于 AgentSpec、SkillManifest 等）"""
    id: ResourceId                                              # 资源 ID
    key: Key                                                    # 人类可读标识
    namespace: Namespace                                        # 命名空间
    version: SemVer                                             # 语义版本
    revision: Annotated[int, Field(ge=1)]                       # 乐观并发修订号
    scope: Scope                                                # 作用域
    labels: dict[Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._/-]{0,62}$")], 
                 Annotated[str, Field(max_length=256)]] = Field(default_factory=dict)
    annotations: dict[Annotated[str, Field(max_length=128)], 
                      Annotated[str, Field(max_length=2048)]] = Field(default_factory=dict)
    content_digest: Digest                                      # 内容摘要
    created_at: AwareDatetime                                   # 创建时间
    created_by: ActorRef                                        # 创建者


class RuntimeMetadata(StrictModel):
    """运行对象的元数据（用于 Task、AgentRun 等）"""
    id: ResourceId                                              # 资源 ID
    revision: Annotated[int, Field(ge=1)]                       # 乐观并发修订号
    scope: Scope                                                # 作用域
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    created_at: AwareDatetime                                   # 创建时间
    created_by: ActorRef                                        # 创建者
    updated_at: AwareDatetime | None = None                     # 更新时间

    @model_validator(mode="after")
    def validate_updated_at(self) -> RuntimeMetadata:
        """更新时间不能早于创建时间"""
        if self.updated_at is not None and self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


# ============================================================
# 引用类型
# ============================================================

class ResourceRef(StrictModel):
    """资源引用（精确版本）"""
    kind: ResourceKind                                          # 资源类型
    id: ResourceId                                              # 资源 ID
    version: SemVer                                             # 语义版本
    digest: Digest                                              # 内容摘要

    @model_validator(mode="after")
    def validate_kind_id(self) -> ResourceRef:
        """验证 ID 前缀与资源类型匹配"""
        expected = KIND_PREFIX[str(self.kind)]
        if not self.id.startswith(expected):
            raise ValueError(f"id must use {expected} prefix for {self.kind}")
        if self.kind not in DEFINITION_KINDS:
            raise ValueError("ResourceRef with semantic version must target a definition resource")
        return self


class ObjectRef(StrictModel):
    """对象引用（不含版本）"""
    kind: ResourceKind                                          # 资源类型
    id: ResourceId                                              # 资源 ID

    @model_validator(mode="after")
    def validate_kind_id(self) -> ObjectRef:
        """验证 ID 前缀与资源类型匹配"""
        expected = KIND_PREFIX[str(self.kind)]
        if not self.id.startswith(expected):
            raise ValueError(f"id must use {expected} prefix for {self.kind}")
        return self


class SchemaRef(StrictModel):
    """Schema 引用"""
    id: SchemaId                                                # Schema ID
    version: SemVer                                             # 版本
    digest: Digest                                              # 内容摘要


class ArtifactRef(StrictModel):
    """Artifact 引用"""
    kind: Literal["Artifact"] = "Artifact"
    id: ResourceId                                              # Artifact ID
    digest: Digest                                              # 内容摘要

    @field_validator("id")
    @classmethod
    def artifact_prefix(cls, value: str) -> str:
        """验证 Artifact ID 前缀"""
        if not value.startswith("art_"):
            raise ValueError("ArtifactRef id must use art_ prefix")
        return value


class SecretRef(StrictModel):
    """Secret 引用（不存储实际密钥）"""
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]  # 密钥管理器
    key: Annotated[str, Field(min_length=1, max_length=512)]              # 密钥路径
    version: Annotated[int, Field(ge=1)] | str                            # 版本
    field: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")]  # 字段名


class TraceContext(StrictModel):
    """追踪上下文"""
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]            # 追踪 ID
    span_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]             # Span ID
    parent_span_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")] | None = None  # 父 Span
    correlation_id: Annotated[str, Field(pattern=r"^corr_[A-Za-z0-9._:-]{3,128}$")]  # 关联 ID


class PriceSnapshotRef(StrictModel):
    """价格快照引用"""
    snapshot_id: Annotated[str, Field(pattern=r"^price_[A-Za-z0-9._:-]{3,128}$")]
    version: SemVer
    effective_at: AwareDatetime
    digest: Digest


# ============================================================
# 预算与使用量
# ============================================================

class Budget(StrictModel):
    """预算定义"""
    max_wall_time_seconds: Annotated[int, Field(gt=0)]                    # 最大执行时间
    max_model_input_tokens: Annotated[int, Field(ge=0)] | None = None     # 最大输入 Token
    max_model_output_tokens: Annotated[int, Field(ge=0)] | None = None    # 最大输出 Token
    max_model_tokens: Annotated[int, Field(gt=0)]                          # 最大总 Token
    max_cost_usd: Annotated[Decimal, Field(ge=0)]                          # 最大费用
    max_tool_calls: Annotated[int, Field(ge=0)]                            # 最大工具调用次数
    max_iterations: Annotated[int, Field(gt=0)]                            # 最大迭代次数

    @model_validator(mode="after")
    def validate_token_budget(self) -> Budget:
        """验证 Token 预算一致性"""
        if self.max_model_input_tokens is not None and self.max_model_input_tokens > self.max_model_tokens:
            raise ValueError("max_model_input_tokens cannot exceed max_model_tokens")
        if self.max_model_output_tokens is not None and self.max_model_output_tokens > self.max_model_tokens:
            raise ValueError("max_model_output_tokens cannot exceed max_model_tokens")
        if self.max_model_input_tokens is not None and self.max_model_output_tokens is not None:
            if self.max_model_input_tokens + self.max_model_output_tokens > self.max_model_tokens:
                raise ValueError("input and output token budgets exceed max_model_tokens")
        return self


class Usage(StrictModel):
    """使用量统计"""
    wall_time_seconds: Annotated[float, Field(ge=0)] = 0                  # 执行时间
    model_input_tokens: Annotated[int, Field(ge=0)] = 0                   # 输入 Token
    model_output_tokens: Annotated[int, Field(ge=0)] = 0                  # 输出 Token
    model_tokens: Annotated[int, Field(ge=0)] = 0                         # 总 Token
    cost_usd: Annotated[Decimal, Field(ge=0)] = Decimal("0")              # 费用
    tool_calls: Annotated[int, Field(ge=0)] = 0                           # 工具调用次数
    iterations: Annotated[int, Field(ge=0)] = 0                           # 迭代次数
    price_snapshot_ref: PriceSnapshotRef                                   # 价格快照

    @model_validator(mode="after")
    def validate_token_usage(self) -> Usage:
        """验证 Token 使用量一致性"""
        if self.model_input_tokens + self.model_output_tokens != self.model_tokens:
            raise ValueError("model_tokens must equal input plus output tokens")
        return self


# ============================================================
# 错误模型
# ============================================================

class ErrorCategory(StrEnum):
    """错误分类"""
    VALIDATION = "validation"          # Schema 或契约错误
    AUTHENTICATION = "authentication"  # 身份认证失败
    AUTHORIZATION = "authorization"    # 权限拒绝
    APPROVAL = "approval"              # 审批拒绝
    BUDGET = "budget"                  # 预算超限
    MODEL = "model"                    # 模型调用失败
    TOOL = "tool"                      # 工具调用失败
    DEPENDENCY = "dependency"          # 依赖服务失败
    CONFLICT = "conflict"              # 版本或状态冲突
    CANCELLED = "cancelled"            # 取消
    TIMEOUT = "timeout"                # 超时
    INTERNAL = "internal"              # 未分类错误


class ErrorSeverity(StrEnum):
    """错误严重程度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StandardError(StrictModel):
    """标准错误对象"""
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")]       # 错误码
    category: ErrorCategory                                                 # 错误分类
    message: Annotated[str, Field(min_length=1, max_length=4096)]          # 错误消息
    retryable: bool                                                         # 是否可重试
    safe_to_retry: bool                                                     # 重试是否安全
    severity: ErrorSeverity                                                 # 严重程度
    details: dict[str, Any] = Field(default_factory=dict)                  # 详细信息
    cause_ref: Annotated[str, Field(pattern=r"^evt_[0-9a-f-]{36}$")] | None = None  # 原因事件
    occurred_at: AwareDatetime                                              # 发生时间

    @model_validator(mode="after")
    def safe_retry_implies_retryable(self) -> StandardError:
        """safe_to_retry 必须同时 retryable"""
        if self.safe_to_retry and not self.retryable:
            raise ValueError("safe_to_retry requires retryable")
        return self


# ============================================================
# 定义对象生命周期
# ============================================================

class DefinitionPhase(StrEnum):
    """定义对象生命周期状态"""
    PROPOSED = "proposed"              # 已提出
    DRAFT = "draft"                    # 草稿
    TESTING = "testing"                # 测试中
    AWAITING_APPROVAL = "awaiting_approval"  # 等待审批
    APPROVED = "approved"              # 已批准
    ACTIVE = "active"                  # 活跃（可用于生产）
    DEPRECATED = "deprecated"          # 已弃用
    BLOCKED = "blocked"                # 已阻塞
    ARCHIVED = "archived"              # 已归档


class DefinitionStatus(StrictModel):
    """定义对象状态"""
    phase: DefinitionPhase                                                  # 生命周期阶段
    observed_revision: Annotated[int, Field(ge=1)]                          # 观测到的修订号
    reason: Annotated[str, Field(max_length=2048)] | None = None            # 状态变更原因
    activated_at: AwareDatetime | None = None                               # 激活时间

    @model_validator(mode="after")
    def active_requires_timestamp(self) -> DefinitionStatus:
        """active 状态必须有激活时间"""
        if self.phase == DefinitionPhase.ACTIVE and self.activated_at is None:
            raise ValueError("active definitions require activated_at")
        return self


# ============================================================
# AgentSpec 辅助类型
# ============================================================

class MemoryPolicy(StrictModel):
    """记忆策略"""
    readable_scopes: list[ScopeType]                                      # 可读取的作用域
    writable_scopes: list[ScopeType]                                      # 可写入的作用域
    write_requires_approval: bool                                         # 写入是否需要审批
    max_retention_days: Annotated[int, Field(ge=1)]                       # 最大保留天数
    allow_cross_user: Literal[False] = False                              # 禁止跨用户
    allow_cross_tenant: Literal[False] = False                            # 禁止跨租户


class ApprovalDefaults(StrictModel):
    """审批默认配置"""
    external_send: bool = True                                            # 外部发送需要审批
    destructive: Literal[True] = True                                     # 破坏性操作必须审批
    privileged: Literal[True] = True                                      # 特权操作必须审批
    approval_ttl_seconds: Annotated[int, Field(gt=0)]                     # 审批有效期


class ConcurrencyPolicy(StrictModel):
    """并发策略"""
    max_parallel_tasks: Annotated[int, Field(gt=0)]                       # 最大并行任务数
    max_parallel_runs_per_task: Annotated[int, Field(gt=0)]               # 每个任务最大并行运行数
    serialization_key_template: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class BindingSelector(StrictModel):
    """绑定选择器"""
    domain: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")] | None = None
    namespace: Namespace | None = None
    status: Literal["active"] = "active"
    labels: dict[str, str] = Field(default_factory=dict)


class Binding(StrictModel):
    """绑定配置"""
    selector: BindingSelector                                             # 选择器
    max_candidates: Annotated[int, Field(ge=1, le=100)]                   # 最大候选数


# ============================================================
# 定义对象 1: AgentSpec
# ============================================================

class AgentSpecSpec(StrictModel):
    """AgentSpec 的 spec 部分"""
    purpose: NonEmptyString                                               # Agent 目的
    domain: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]    # 业务领域
    goals: Annotated[list[NonEmptyString], Field(min_length=1)]           # 目标列表
    non_goals: Annotated[list[NonEmptyString], Field(min_length=1)]       # 非目标列表
    input_schema_ref: SchemaRef                                           # 输入 Schema
    output_schema_ref: SchemaRef                                          # 输出 Schema
    prompt_package_ref: ResourceRef                                       # Prompt 包引用
    context_policy_ref: ResourceRef                                       # Context 策略引用
    model_policy_ref: ResourceRef                                         # 模型策略引用
    loop_profile_ref: ResourceRef                                         # Loop 配置引用
    permission_profile_ref: ResourceRef                                   # 权限配置引用
    skill_bindings: list[Binding] = Field(default_factory=list)           # 技能绑定
    tool_bindings: list[Binding] = Field(default_factory=list)            # 工具绑定
    memory_policy: MemoryPolicy                                           # 记忆策略
    budget_defaults: Budget                                               # 默认预算
    approval_defaults: ApprovalDefaults                                   # 审批默认配置
    concurrency_policy: ConcurrencyPolicy                                 # 并发策略
    eval_suite_refs: Annotated[list[ArtifactRef], Field(min_length=1)]    # 评估集引用

    @model_validator(mode="after")
    def validate_reference_kinds(self) -> AgentSpecSpec:
        """验证引用类型正确性"""
        expected = {
            "prompt_package_ref": ResourceKind.PROMPT_PACKAGE,
            "context_policy_ref": ResourceKind.CONTEXT_POLICY,
            "model_policy_ref": ResourceKind.MODEL_POLICY,
            "loop_profile_ref": ResourceKind.LOOP_PROFILE,
            "permission_profile_ref": ResourceKind.PERMISSION_PROFILE,
        }
        for field_name, kind in expected.items():
            if getattr(self, field_name).kind != kind:
                raise ValueError(f"{field_name} must reference {kind}")
        return self


class AgentSpecResource(StrictModel):
    """AgentSpec 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["AgentSpec"] = "AgentSpec"
    metadata: DefinitionMetadata
    spec: AgentSpecSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> AgentSpecResource:
        """验证资源完整性"""
        # 验证 ID 前缀
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 定义对象 2: SkillManifest
# ============================================================

class TriggerExamples(StrictModel):
    """触发示例"""
    positive: Annotated[list[NonEmptyString], Field(min_length=1)]        # 正例
    negative: Annotated[list[NonEmptyString], Field(min_length=1)]        # 反例


class ToolRequirement(StrictModel):
    """工具需求"""
    tool_ref: ResourceRef                                                 # 工具引用
    required_capabilities: list[NonEmptyString] = Field(default_factory=list)  # 所需能力

    @model_validator(mode="after")
    def require_tool(self) -> ToolRequirement:
        """验证引用的是 ToolManifest"""
        if self.tool_ref.kind != ResourceKind.TOOL_MANIFEST:
            raise ValueError("tool_ref must reference ToolManifest")
        return self


class SkillRequirement(StrictModel):
    """技能需求"""
    skill_ref: ResourceRef                                                # 技能引用
    optional: bool = False                                                # 是否可选

    @model_validator(mode="after")
    def require_skill(self) -> SkillRequirement:
        """验证引用的是 SkillManifest"""
        if self.skill_ref.kind != ResourceKind.SKILL_MANIFEST:
            raise ValueError("skill_ref must reference SkillManifest")
        return self


class PermissionRequest(StrictModel):
    """权限请求"""
    actions: Annotated[list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]], Field(min_length=1)]
    resources: Annotated[list[NonEmptyString], Field(min_length=1)]
    conditions: dict[str, Any] = Field(default_factory=dict)


class RiskLevel(StrEnum):
    """风险级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuntimeRequirements(StrictModel):
    """运行时需求"""
    operating_systems: list[Literal["linux", "windows", "macos", "any"]]
    binaries: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_.+-]{1,128}$")]] = Field(default_factory=list)
    network_domains: list[Annotated[str, Field(pattern=r"^(?:[a-z0-9-]+\.)+[a-z]{2,63}$")]] = Field(default_factory=list)
    has_scripts: bool
    sandbox_required: bool
    sandbox_profile: Annotated[str, Field(min_length=1, max_length=128)] | None = None

    @model_validator(mode="after")
    def scripts_require_sandbox(self) -> RuntimeRequirements:
        """有脚本必须有沙箱"""
        if self.has_scripts and (not self.sandbox_required or self.sandbox_profile is None):
            raise ValueError("skills with scripts require a named sandbox profile")
        return self


class ContextBudget(StrictModel):
    """Context 预算"""
    max_skill_tokens: Annotated[int, Field(gt=0)]
    max_reference_tokens: Annotated[int, Field(ge=0)]
    max_total_tokens: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def parts_fit_total(self) -> ContextBudget:
        """分项不能超过总额"""
        if self.max_skill_tokens + self.max_reference_tokens > self.max_total_tokens:
            raise ValueError("skill and reference token budgets exceed total")
        return self


class SourceRepository(StrictModel):
    """源码仓库"""
    repository: Annotated[str, Field(min_length=1, max_length=512)]
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    path: Annotated[str, Field(min_length=1, max_length=1024)]


class EvalSummary(StrictModel):
    """评估摘要"""
    trigger_precision: Annotated[float, Field(ge=0, le=1)]
    trigger_recall: Annotated[float, Field(ge=0, le=1)]
    output_pass_rate: Annotated[float, Field(ge=0, le=1)]
    security_passed: bool
    regression_passed: bool
    evaluated_cases: Annotated[int, Field(gt=0)]
    evaluated_at: AwareDatetime


class ProvenanceType(StrEnum):
    """来源类型"""
    HUMAN = "human"
    HERMES_PROPOSAL = "hermes_proposal"
    EXTERNAL = "external"
    IMPORTED = "imported"


class DefinitionProvenance(StrictModel):
    """定义来源"""
    type: ProvenanceType
    actor: ActorRef
    source_ref: NonEmptyString | None = None


class SkillManifestSpec(StrictModel):
    """SkillManifest 的 spec 部分"""
    portable_name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")]
    description: Annotated[str, Field(min_length=20, max_length=2048)]
    domain: Annotated[list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]], Field(min_length=1)]
    tags: list[Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]] = Field(default_factory=list)
    trigger_examples: TriggerExamples
    input_schema_ref: SchemaRef | None = None
    output_schema_ref: SchemaRef | None = None
    required_tools: list[ToolRequirement] = Field(default_factory=list)
    required_skills: list[SkillRequirement] = Field(default_factory=list)
    conflicts_with: list[ResourceRef] = Field(default_factory=list)
    permission_requirements: list[PermissionRequest] = Field(default_factory=list)
    risk_level: RiskLevel
    runtime_requirements: RuntimeRequirements
    context_budget: ContextBudget
    bundle_artifact_ref: ArtifactRef
    source_repository: SourceRepository
    eval_summary: EvalSummary
    provenance: DefinitionProvenance

    @model_validator(mode="after")
    def validate_skill_refs(self) -> SkillManifestSpec:
        """验证技能引用"""
        for ref in self.conflicts_with:
            if ref.kind != ResourceKind.SKILL_MANIFEST:
                raise ValueError("conflicts_with must reference SkillManifest")
        ids = [requirement.skill_ref.id for requirement in self.required_skills]
        if len(ids) != len(set(ids)):
            raise ValueError("required_skills cannot contain duplicates")
        return self


class SkillManifestResource(StrictModel):
    """SkillManifest 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["SkillManifest"] = "SkillManifest"
    metadata: DefinitionMetadata
    spec: SkillManifestSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> SkillManifestResource:
        """验证资源完整性"""
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        # Hermes 提案只能是 proposed 或 draft
        if self.spec.provenance.type == ProvenanceType.HERMES_PROPOSAL and self.status.phase not in {DefinitionPhase.PROPOSED, DefinitionPhase.DRAFT}:
            raise ValueError("Hermes proposals may only be proposed or draft")
        # active 状态必须通过安全和回归评估
        if self.status.phase == DefinitionPhase.ACTIVE:
            if not (self.spec.eval_summary.security_passed and self.spec.eval_summary.regression_passed):
                raise ValueError("active skill requires passing security and regression evaluations")
        return self


print("models.py 定义对象部分创建完成！")
print("已添加：AgentSpec、SkillManifest 及其辅助类型")

# ============================================================
# 定义对象 3: ToolManifest
# ============================================================

class ToolTransport(StrEnum):
    """工具传输协议"""
    LOCAL = "local"
    HTTP = "http"
    GRPC = "grpc"
    MCP = "mcp"
    OPENCLAW = "openclaw"


class SideEffect(StrEnum):
    """副作用分类"""
    READ_ONLY = "read_only"           # 只读
    LOCAL_WRITE = "local_write"       # 本地写入
    EXTERNAL_WRITE = "external_write" # 外部写入
    EXTERNAL_SEND = "external_send"   # 外部发送
    DESTRUCTIVE = "destructive"       # 破坏性
    PRIVILEGED = "privileged"         # 特权


class ExecutionLocation(StrEnum):
    """执行位置"""
    CLOUD = "cloud"
    LOCAL = "local"
    SANDBOX = "sandbox"
    DEVICE = "device"
    GPU = "gpu"


class EndpointRef(StrictModel):
    """服务端点引用"""
    service_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    endpoint_key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:/-]{1,255}$")]


class IdempotencyPolicy(StrictModel):
    """幂等策略"""
    supported: bool
    key_scope: Literal["none", "tool_target", "tenant_tool_target"]
    duplicate_semantics: Literal["reject", "return_original", "reconcile", "not_applicable"]

    @model_validator(mode="after")
    def validate_supported_scope(self) -> IdempotencyPolicy:
        if self.supported and self.key_scope == "none":
            raise ValueError("supported idempotency requires a non-none key scope")
        if not self.supported and self.key_scope != "none":
            raise ValueError("unsupported idempotency must use none key scope")
        return self


class TimeoutPolicy(StrictModel):
    """超时策略"""
    connect_timeout_seconds: Annotated[float, Field(gt=0)]
    execution_timeout_seconds: Annotated[float, Field(gt=0)]


class RetryPolicy(StrictModel):
    """重试策略"""
    max_attempts: Annotated[int, Field(ge=1)]
    retryable_error_codes: list[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")]]
    backoff: Literal["none", "fixed", "exponential"]
    base_delay_seconds: Annotated[float, Field(ge=0)]
    requires_safe_to_retry: Literal[True] = True


class RateLimit(StrictModel):
    """限流策略"""
    requests: Annotated[int, Field(gt=0)]
    per_seconds: Annotated[int, Field(gt=0)]


class ApprovalRequirement(StrictModel):
    """审批要求"""
    mode: Literal["none", "conditional", "always"]
    conditions: list[NonEmptyString] = Field(default_factory=list)


class HealthContract(StrictModel):
    """健康检查契约"""
    healthcheck_key: Annotated[str, Field(min_length=1, max_length=256)]
    interval_seconds: Annotated[int, Field(gt=0)]
    unhealthy_after_failures: Annotated[int, Field(gt=0)]


class ToolManifestSpec(StrictModel):
    """ToolManifest 的 spec 部分"""
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    capability: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]
    domain: Annotated[list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]], Field(min_length=1)]
    transport: ToolTransport
    endpoint_ref: EndpointRef
    input_schema_ref: SchemaRef
    output_schema_ref: SchemaRef
    auth_profile_ref: SecretRef | None = None
    side_effect: SideEffect
    risk_level: RiskLevel
    idempotency: IdempotencyPolicy
    timeout_policy: TimeoutPolicy
    retry_policy: RetryPolicy
    rate_limit: RateLimit | None = None
    execution_location: ExecutionLocation
    sandbox_profile: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    approval_requirement: ApprovalRequirement
    health_contract: HealthContract

    @model_validator(mode="after")
    def validate_effect_controls(self) -> ToolManifestSpec:
        """验证副作用控制"""
        if self.side_effect != SideEffect.READ_ONLY and not self.idempotency.supported:
            raise ValueError("side-effect tools must support scoped idempotency")
        if self.side_effect in {SideEffect.DESTRUCTIVE, SideEffect.PRIVILEGED} and self.approval_requirement.mode != "always":
            raise ValueError("destructive and privileged tools require approval always")
        if self.execution_location == ExecutionLocation.SANDBOX and self.sandbox_profile is None:
            raise ValueError("sandbox execution requires sandbox_profile")
        return self


class ToolManifestResource(StrictModel):
    """ToolManifest 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ToolManifest"] = "ToolManifest"
    metadata: DefinitionMetadata
    spec: ToolManifestSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> ToolManifestResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 定义对象 4: PromptPackage
# ============================================================

class PromptLayer(StrEnum):
    """Prompt 层级"""
    SAFETY = "safety"
    IDENTITY = "identity"
    DOMAIN = "domain"
    BEHAVIOR = "behavior"
    OUTPUT_CONTRACT = "output_contract"
    ERROR_POLICY = "error_policy"


class PromptFragment(StrictModel):
    """Prompt 片段"""
    name: Key
    layer: PromptLayer
    order: Annotated[int, Field(ge=0)]
    content: Annotated[str, Field(min_length=1, max_length=20000)]


class ModelCompatibility(StrictModel):
    """模型兼容性"""
    required_capabilities: list[Literal["tool_calling", "vision", "long_context", "structured_output", "reasoning"]]
    provider_allowlist: Annotated[list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]], Field(min_length=1)]


class PromptPackageSpec(StrictModel):
    """PromptPackage 的 spec 部分"""
    fragments: Annotated[list[PromptFragment], Field(min_length=1)]
    variables_schema_ref: SchemaRef
    model_compatibility: ModelCompatibility
    output_schema_ref: SchemaRef
    max_static_tokens: Annotated[int, Field(gt=0)]
    eval_suite_refs: Annotated[list[ArtifactRef], Field(min_length=1)]
    change_summary: Annotated[str, Field(min_length=1, max_length=4096)]

    @model_validator(mode="after")
    def validate_fragment_order(self) -> PromptPackageSpec:
        orders = [fragment.order for fragment in self.fragments]
        if len(orders) != len(set(orders)):
            raise ValueError("prompt fragment order values must be unique")
        if not any(fragment.layer == PromptLayer.SAFETY for fragment in self.fragments):
            raise ValueError("prompt package requires a safety fragment")
        return self


class PromptPackageResource(StrictModel):
    """PromptPackage 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["PromptPackage"] = "PromptPackage"
    metadata: DefinitionMetadata
    spec: PromptPackageSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> PromptPackageResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 定义对象 5: ModelPolicy
# ============================================================

class ModelRoute(StrictModel):
    """模型路由"""
    route_id: Key
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    model: NonEmptyString
    priority: Annotated[int, Field(ge=0)]
    required_capabilities: list[NonEmptyString]
    conditions: dict[str, Any] = Field(default_factory=dict)


class DataClassificationRule(StrictModel):
    """数据分类规则"""
    classification: Literal["public", "internal", "confidential", "restricted"]
    allowed_providers: list[NonEmptyString]
    require_local: bool = False


class FallbackStep(StrictModel):
    """回退步骤"""
    route_id: Key
    on_error_codes: Annotated[list[NonEmptyString], Field(min_length=1)]


class CircuitBreaker(StrictModel):
    """熔断器"""
    failure_threshold: Annotated[int, Field(gt=0)]
    window_seconds: Annotated[int, Field(gt=0)]
    open_seconds: Annotated[int, Field(gt=0)]


class ModelPolicySpec(StrictModel):
    """ModelPolicy 的 spec 部分"""
    routes: Annotated[list[ModelRoute], Field(min_length=1)]
    required_capabilities: list[NonEmptyString]
    provider_allowlist: Annotated[list[NonEmptyString], Field(min_length=1)]
    data_classification_rules: Annotated[list[DataClassificationRule], Field(min_length=1)]
    fallback_chain: list[FallbackStep]
    budget_limits: Budget
    quality_floor: Literal["economy", "standard", "high", "frontier"]
    region_constraints: list[Annotated[str, Field(pattern=r"^[A-Z]{2}(?:-[A-Z0-9]{1,3})?$")]]
    local_model_rules: dict[str, Any] = Field(default_factory=dict)
    circuit_breaker: CircuitBreaker

    @model_validator(mode="after")
    def validate_routes(self) -> ModelPolicySpec:
        route_ids = [route.route_id for route in self.routes]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("model route ids must be unique")
        if not set(route.provider for route in self.routes).issubset(set(self.provider_allowlist)):
            raise ValueError("all route providers must be allowlisted")
        if not set(step.route_id for step in self.fallback_chain).issubset(set(route_ids)):
            raise ValueError("fallback route must exist")
        return self


class ModelPolicyResource(StrictModel):
    """ModelPolicy 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ModelPolicy"] = "ModelPolicy"
    metadata: DefinitionMetadata
    spec: ModelPolicySpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> ModelPolicyResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 定义对象 6: ContextPolicy
# ============================================================

class ContextSourceType(StrEnum):
    """Context 来源类型"""
    TASK = "task"
    AGENT_SPEC = "agent_spec"
    PROMPT = "prompt"
    THREAD = "thread"
    MEMORY = "memory"
    PROJECT_STATE = "project_state"
    SKILL = "skill"
    TOOL_SCHEMA = "tool_schema"
    KNOWLEDGE = "knowledge"
    ARTIFACT = "artifact"
    TOOL_RESULT = "tool_result"
    GRAPH_STATE = "graph_state"
    APPROVAL = "approval"


class SourceRule(StrictModel):
    """来源规则"""
    source: ContextSourceType
    effect: Literal["allow", "deny"]
    priority: Annotated[int, Field(ge=0, le=100)]
    filters: dict[str, Any] = Field(default_factory=dict)


class ContextTokenBudget(StrictModel):
    """Context Token 预算"""
    total_tokens: Annotated[int, Field(gt=0)]
    reserved_output_tokens: Annotated[int, Field(ge=0)]
    per_source: dict[ContextSourceType, Annotated[int, Field(ge=0)]]

    @model_validator(mode="after")
    def validate_context_budget(self) -> ContextTokenBudget:
        if self.reserved_output_tokens >= self.total_tokens:
            raise ValueError("reserved output must be smaller than total context budget")
        if sum(self.per_source.values()) > self.total_tokens - self.reserved_output_tokens:
            raise ValueError("per-source budgets exceed available input tokens")
        return self


class SkillSelection(StrictModel):
    """技能选择策略"""
    top_k: Annotated[int, Field(ge=1, le=100)]
    similarity_threshold: Annotated[float, Field(ge=0, le=1)]
    metadata_token_limit: Annotated[int, Field(gt=0)]


class ToolSelection(StrictModel):
    """工具选择策略"""
    max_visible_tools: Annotated[int, Field(ge=1, le=256)]
    schema_token_limit: Annotated[int, Field(gt=0)]


class ContextMemoryScope(StrictModel):
    """Context 记忆作用域"""
    allowed_scopes: list[ScopeType]
    allow_cross_user: Literal[False] = False
    allow_cross_tenant: Literal[False] = False


class FreshnessPolicy(StrictModel):
    """新鲜度策略"""
    default_ttl_seconds: Annotated[int, Field(ge=0)]
    source_ttl_seconds: dict[ContextSourceType, Annotated[int, Field(ge=0)]] = Field(default_factory=dict)


class DeduplicationPolicy(StrictModel):
    """去重策略"""
    strategy: Literal["digest", "semantic", "hybrid"]
    similarity_threshold: Annotated[float, Field(ge=0, le=1)] | None = None


class CompactionPolicy(StrictModel):
    """压缩策略"""
    strategy: Literal["extractive", "abstractive", "hybrid"]
    target_ratio: Annotated[float, Field(gt=0, le=1)]
    preserve_provenance: Literal[True] = True


class RedactionPolicy(StrictModel):
    """脱敏策略"""
    redact_secrets: Literal[True] = True
    pii_mode: Literal["none", "mask", "remove"]
    restricted_data_mode: Literal["deny", "local_only", "mask"]


class SnapshotPolicy(StrictModel):
    """快照策略"""
    persist: bool
    store_content: bool
    retention_days: Annotated[int, Field(ge=1)]
    require_digest: Literal[True] = True


class ContextPolicySpec(StrictModel):
    """ContextPolicy 的 spec 部分"""
    source_rules: Annotated[list[SourceRule], Field(min_length=1)]
    token_budget: ContextTokenBudget
    skill_selection: SkillSelection
    tool_selection: ToolSelection
    memory_scope: ContextMemoryScope
    freshness: FreshnessPolicy
    deduplication: DeduplicationPolicy
    compaction: CompactionPolicy
    redaction: RedactionPolicy
    provenance_requirement: bool
    snapshot_policy: SnapshotPolicy


class ContextPolicyResource(StrictModel):
    """ContextPolicy 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ContextPolicy"] = "ContextPolicy"
    metadata: DefinitionMetadata
    spec: ContextPolicySpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> ContextPolicyResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 定义对象 7: LoopProfile
# ============================================================

class LoopStrategy(StrEnum):
    """Loop 策略"""
    SINGLE_PASS = "single_pass"
    REACT = "react"
    REPAIR = "repair"
    RALPH = "ralph"
    REVIEW_REFINE = "review_refine"


class StopCondition(StrictModel):
    """停止条件"""
    condition_type: Literal["success", "failure", "budget", "human_stop", "validator"]
    expression: NonEmptyString


class CheckpointPolicy(StrictModel):
    """Checkpoint 策略"""
    interval_iterations: Annotated[int, Field(gt=0)]
    on_tool_side_effect: bool
    on_human_interrupt: Literal[True] = True
    on_node_end: bool


class LoopRetryPolicy(StrictModel):
    """Loop 重试策略"""
    max_model_retries: Annotated[int, Field(ge=0)]
    max_node_retries: Annotated[int, Field(ge=0)]
    backoff: Literal["none", "fixed", "exponential"]


class HumanInterrupt(StrictModel):
    """人工中断"""
    stage: NonEmptyString
    reason: NonEmptyString
    required: bool


class ProgressPolicy(StrictModel):
    """进度策略"""
    emit_every_iterations: Annotated[int, Field(gt=0)]
    persist_summary: bool


class RollbackPolicy(StrictModel):
    """回滚策略"""
    strategy: Literal["none", "compensating_action", "manual"]
    compensation_tool_refs: list[ResourceRef] = Field(default_factory=list)


class LoopProfileSpec(StrictModel):
    """LoopProfile 的 spec 部分"""
    strategy: LoopStrategy
    max_iterations: Annotated[int, Field(gt=0)]
    max_wall_time_seconds: Annotated[int, Field(gt=0)]
    max_model_tokens: Annotated[int, Field(gt=0)]
    max_cost_usd: Annotated[Decimal, Field(ge=0)]
    stop_conditions: Annotated[list[StopCondition], Field(min_length=1)]
    evaluator_refs: Annotated[list[ResourceRef], Field(min_length=1)]
    checkpoint_policy: CheckpointPolicy
    retry_policy: LoopRetryPolicy
    human_interrupts: list[HumanInterrupt] = Field(default_factory=list)
    progress_policy: ProgressPolicy
    rollback_policy: RollbackPolicy

    @model_validator(mode="after")
    def validate_success_condition(self) -> LoopProfileSpec:
        if not any(condition.condition_type == "success" for condition in self.stop_conditions):
            raise ValueError("loop requires a success stop condition")
        if self.strategy == LoopStrategy.RALPH and not self.evaluator_refs:
            raise ValueError("ralph loop requires an external evaluator")
        return self


class LoopProfileResource(StrictModel):
    """LoopProfile 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["LoopProfile"] = "LoopProfile"
    metadata: DefinitionMetadata
    spec: LoopProfileSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> LoopProfileResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 定义对象 8: PermissionProfile
# ============================================================

class PermissionEffect(StrEnum):
    """权限效果"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PermissionRule(StrictModel):
    """权限规则"""
    effect: PermissionEffect
    actions: Annotated[list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]], Field(min_length=1)]
    resources: Annotated[list[NonEmptyString], Field(min_length=1)]
    conditions: dict[str, Any] = Field(default_factory=dict)


class PermissionProfileSpec(StrictModel):
    """PermissionProfile 的 spec 部分"""
    roles: list[Key] = Field(default_factory=list)
    rules: Annotated[list[PermissionRule], Field(min_length=1)]
    capabilities: list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]] = Field(default_factory=list)
    default_decision: Literal["deny"] = "deny"
    deny_precedence: Literal[True] = True
    cross_tenant_default: Literal["deny"] = "deny"


class PermissionProfileResource(StrictModel):
    """PermissionProfile 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["PermissionProfile"] = "PermissionProfile"
    metadata: DefinitionMetadata
    spec: PermissionProfileSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> PermissionProfileResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 运行对象 1: Task
# ============================================================

class TaskSource(StrictModel):
    """任务来源"""
    type: Literal["openclaw", "api", "cron", "webhook", "ui", "system"]
    channel: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    source_message_id: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class RoutingConstraints(StrictModel):
    """路由约束"""
    allowed_agent_refs: list[ResourceRef] = Field(default_factory=list)
    allowed_domains: list[NonEmptyString] = Field(default_factory=list)
    required_model_capabilities: list[NonEmptyString] = Field(default_factory=list)


class Schedule(StrictModel):
    """调度配置"""
    mode: Literal["immediate", "at", "delayed"]
    execute_at: AwareDatetime | None = None
    delay_seconds: Annotated[int, Field(gt=0)] | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> Schedule:
        if self.mode == "at" and self.execute_at is None:
            raise ValueError("at schedule requires execute_at")
        if self.mode == "delayed" and self.delay_seconds is None:
            raise ValueError("delayed schedule requires delay_seconds")
        return self


class PermissionGrant(StrictModel):
    """权限授予"""
    actions: list[NonEmptyString]
    resources: list[NonEmptyString]
    expires_at: AwareDatetime | None = None


class RetentionPolicy(StrictModel):
    """保留策略"""
    retain_days: Annotated[int, Field(ge=1)]
    delete_after: AwareDatetime | None = None
    legal_hold: bool = False


class TaskSpec(StrictModel):
    """Task 的 spec 部分"""
    title: Annotated[str, Field(min_length=1, max_length=256)]
    intent: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]
    domain: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    requested_by: ActorRef
    source: TaskSource
    payload: dict[str, Any] | ArtifactRef
    input_schema_ref: SchemaRef
    expected_output_schema_ref: SchemaRef
    input_artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    requested_agent_ref: ResourceRef | None = None
    routing_constraints: RoutingConstraints
    priority: Annotated[int, Field(ge=0, le=100)]
    schedule: Schedule | None = None
    dependencies: list[ObjectRef] = Field(default_factory=list)
    budget: Budget
    permission_grant: PermissionGrant
    approval_policy_ref: ResourceRef | None = None
    idempotency_key: Annotated[str, Field(min_length=8, max_length=512)]
    deadline_at: AwareDatetime | None = None
    retention_policy: RetentionPolicy

    @model_validator(mode="after")
    def validate_task_refs(self) -> TaskSpec:
        if self.requested_agent_ref and self.requested_agent_ref.kind != ResourceKind.AGENT_SPEC:
            raise ValueError("requested_agent_ref must reference AgentSpec")
        for ref in self.dependencies:
            if ref.kind != ResourceKind.TASK:
                raise ValueError("dependencies must reference Task")
        if self.approval_policy_ref and self.approval_policy_ref.kind != ResourceKind.PERMISSION_PROFILE:
            raise ValueError("approval_policy_ref must reference PermissionProfile")
        return self


class TaskPhase(StrEnum):
    """Task 生命周期状态"""
    CREATED = "created"
    VALIDATED = "validated"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    WAITING_APPROVAL = "waiting_approval"
    SUSPENDED = "suspended"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TaskStatus(StrictModel):
    """Task 状态"""
    phase: TaskPhase
    active_run_ref: ObjectRef | None = None
    final_artifact_ref: ArtifactRef | None = None
    error: StandardError | None = None

    @model_validator(mode="after")
    def validate_terminal_status(self) -> TaskStatus:
        if self.phase == TaskPhase.SUCCEEDED and self.final_artifact_ref is None:
            raise ValueError("succeeded task requires final_artifact_ref")
        if self.phase == TaskPhase.FAILED and self.error is None:
            raise ValueError("failed task requires error")
        return self


class TaskResource(StrictModel):
    """Task 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Task"] = "Task"
    metadata: RuntimeMetadata
    spec: TaskSpec
    status: TaskStatus

    @model_validator(mode="after")
    def invariants(self) -> TaskResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


# ============================================================
# 运行对象 2: AgentRun
# ============================================================

class WorkerRef(StrictModel):
    """Worker 引用"""
    worker_id: Annotated[str, Field(pattern=r"^wrk_[A-Za-z0-9._:-]{3,128}$")]
    service: Key
    instance: NonEmptyString


class Lease(StrictModel):
    """执行租约"""
    lease_id: Annotated[str, Field(pattern=r"^lease_[A-Za-z0-9._:-]{3,128}$")]
    worker_ref: WorkerRef
    acquired_at: AwareDatetime
    heartbeat_at: AwareDatetime
    expires_at: AwareDatetime
    fencing_token: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def validate_lease_times(self) -> Lease:
        if not (self.acquired_at <= self.heartbeat_at < self.expires_at):
            raise ValueError("lease timestamps must satisfy acquired <= heartbeat < expires")
        return self


class ResolvedDependencies(StrictModel):
    """已解析的依赖"""
    prompt_package_ref: ResourceRef
    context_policy_ref: ResourceRef
    model_policy_ref: ResourceRef
    loop_profile_ref: ResourceRef
    permission_profile_ref: ResourceRef
    startup_skill_refs: list[ResourceRef]
    startup_tool_refs: list[ResourceRef]
    price_snapshot_ref: PriceSnapshotRef
    schema_version: SemVer
    runtime_version: NonEmptyString

    @model_validator(mode="after")
    def validate_dependency_kinds(self) -> ResolvedDependencies:
        pairs = [
            (self.prompt_package_ref, ResourceKind.PROMPT_PACKAGE),
            (self.context_policy_ref, ResourceKind.CONTEXT_POLICY),
            (self.model_policy_ref, ResourceKind.MODEL_POLICY),
            (self.loop_profile_ref, ResourceKind.LOOP_PROFILE),
            (self.permission_profile_ref, ResourceKind.PERMISSION_PROFILE),
        ]
        for ref, kind in pairs:
            if ref.kind != kind:
                raise ValueError(f"dependency must reference {kind}")
        if any(ref.kind != ResourceKind.SKILL_MANIFEST for ref in self.startup_skill_refs):
            raise ValueError("startup_skill_refs must reference SkillManifest")
        if any(ref.kind != ResourceKind.TOOL_MANIFEST for ref in self.startup_tool_refs):
            raise ValueError("startup_tool_refs must reference ToolManifest")
        return self


class DynamicDependencyActivation(StrictModel):
    """动态依赖激活记录"""
    sequence: Annotated[int, Field(ge=1)]
    resource_ref: ResourceRef
    activated_at: AwareDatetime
    activation_reason: NonEmptyString
    source_skill_ref: ResourceRef | None = None
    permission_decision_digest: Digest
    event_ref: ObjectRef
    checkpoint_ref: ObjectRef | None = None

    @model_validator(mode="after")
    def validate_activation_refs(self) -> DynamicDependencyActivation:
        if self.resource_ref.kind not in {ResourceKind.SKILL_MANIFEST, ResourceKind.TOOL_MANIFEST}:
            raise ValueError("dynamic resource_ref must reference SkillManifest or ToolManifest")
        if self.source_skill_ref and self.source_skill_ref.kind != ResourceKind.SKILL_MANIFEST:
            raise ValueError("source_skill_ref must reference SkillManifest")
        if self.event_ref.kind != ResourceKind.EVENT:
            raise ValueError("event_ref must reference Event")
        if self.checkpoint_ref and self.checkpoint_ref.kind != ResourceKind.CHECKPOINT:
            raise ValueError("checkpoint_ref must reference Checkpoint")
        return self


class ModelSelectionReason(StrEnum):
    """模型选择原因"""
    INITIAL = "initial"
    FALLBACK = "fallback"


class ModelSelectionRecord(StrictModel):
    """模型选择记录"""
    sequence: Annotated[int, Field(ge=1)]
    route_id: Key
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    model: NonEmptyString
    selected_at: AwareDatetime
    selection_reason: ModelSelectionReason
    trigger_error_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")] | None = None
    price_snapshot_ref: PriceSnapshotRef
    event_ref: ObjectRef

    @model_validator(mode="after")
    def validate_model_selection(self) -> ModelSelectionRecord:
        if self.selection_reason == ModelSelectionReason.FALLBACK and self.trigger_error_code is None:
            raise ValueError("fallback selection requires trigger_error_code")
        if self.selection_reason == ModelSelectionReason.INITIAL and self.trigger_error_code is not None:
            raise ValueError("initial selection cannot declare trigger_error_code")
        if self.event_ref.kind != ResourceKind.EVENT:
            raise ValueError("event_ref must reference Event")
        return self


class GraphRef(StrictModel):
    """Graph 引用"""
    graph_id: Annotated[str, Field(pattern=r"^grf_[A-Za-z0-9._:-]{3,128}$")]
    version: SemVer
    node_id: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class AgentRunSpec(StrictModel):
    """AgentRun 的 spec 部分"""
    task_ref: ObjectRef
    attempt: Annotated[int, Field(ge=1)]
    agent_snapshot: ResourceRef
    resolved_dependencies: ResolvedDependencies
    dynamic_dependency_activations: list[DynamicDependencyActivation] = Field(default_factory=list)
    current_model_selection: ModelSelectionRecord
    model_selection_history: Annotated[list[ModelSelectionRecord], Field(min_length=1)]
    worker_ref: WorkerRef | None = None
    thread_ref: Annotated[str, Field(pattern=r"^thr_[A-Za-z0-9._:-]{3,128}$")] | None = None
    graph_ref: GraphRef | None = None
    current_checkpoint_ref: ObjectRef | None = None
    budget: Budget
    usage: Usage
    context_snapshot_refs: list[ArtifactRef] = Field(default_factory=list)
    output_artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    error: StandardError | None = None
    lease: Lease | None = None

    @model_validator(mode="after")
    def validate_run_refs(self) -> AgentRunSpec:
        if self.task_ref.kind != ResourceKind.TASK:
            raise ValueError("task_ref must reference Task")
        if self.agent_snapshot.kind != ResourceKind.AGENT_SPEC:
            raise ValueError("agent_snapshot must reference AgentSpec")
        if self.current_checkpoint_ref and self.current_checkpoint_ref.kind != ResourceKind.CHECKPOINT:
            raise ValueError("current_checkpoint_ref must reference Checkpoint")
        activation_sequences = [item.sequence for item in self.dynamic_dependency_activations]
        if activation_sequences != list(range(1, len(activation_sequences) + 1)):
            raise ValueError("dynamic dependency activation sequences must be contiguous from 1")
        activated_refs = [
            (item.resource_ref.kind, item.resource_ref.id, item.resource_ref.version, item.resource_ref.digest)
            for item in self.dynamic_dependency_activations
        ]
        if len(activated_refs) != len(set(activated_refs)):
            raise ValueError("a dynamic dependency cannot be activated twice in one run")
        startup_refs = {
            (item.kind, item.id, item.version, item.digest)
            for item in self.resolved_dependencies.startup_skill_refs + self.resolved_dependencies.startup_tool_refs
        }
        if startup_refs.intersection(activated_refs):
            raise ValueError("dynamic dependency cannot duplicate a startup-frozen dependency")
        model_sequences = [item.sequence for item in self.model_selection_history]
        if model_sequences != list(range(1, len(model_sequences) + 1)):
            raise ValueError("model selection sequences must be contiguous from 1")
        if self.model_selection_history[0].selection_reason != ModelSelectionReason.INITIAL:
            raise ValueError("first model selection must be initial")
        if any(item.selection_reason != ModelSelectionReason.FALLBACK for item in self.model_selection_history[1:]):
            raise ValueError("later model selections must be fallback selections")
        route_ids = [item.route_id for item in self.model_selection_history]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("model fallback cannot revisit a route in one run")
        if self.current_model_selection != self.model_selection_history[-1]:
            raise ValueError("current_model_selection must equal the last model_selection_history record")
        frozen_price = self.resolved_dependencies.price_snapshot_ref
        for selection in self.model_selection_history:
            if selection.price_snapshot_ref.version != frozen_price.version or selection.price_snapshot_ref.digest != frozen_price.digest:
                raise ValueError("model selections must use the run-frozen price snapshot")
        if self.usage.model_tokens > self.budget.max_model_tokens or self.usage.cost_usd > self.budget.max_cost_usd:
            raise ValueError("run usage cannot exceed run budget")
        return self


class AgentRunPhase(StrEnum):
    """AgentRun 生命周期状态"""
    CREATED = "created"
    RESOLVING = "resolving"
    READY = "ready"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    CHECKPOINTED = "checkpointed"
    SUSPENDED = "suspended"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class AgentRunStatus(StrictModel):
    """AgentRun 状态"""
    phase: AgentRunPhase
    reason: Annotated[str, Field(max_length=2048)] | None = None


class AgentRunResource(StrictModel):
    """AgentRun 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["AgentRun"] = "AgentRun"
    metadata: RuntimeMetadata
    spec: AgentRunSpec
    status: AgentRunStatus

    @model_validator(mode="after")
    def invariants(self) -> AgentRunResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        if self.status.phase in {AgentRunPhase.RUNNING, AgentRunPhase.WAITING_TOOL} and self.spec.lease is None:
            raise ValueError("executing run requires an active lease snapshot")
        if self.status.phase == AgentRunPhase.SUCCEEDED and not self.spec.output_artifact_refs:
            raise ValueError("succeeded run requires output artifacts")
        return self


# ============================================================
# 运行对象 3-7: Checkpoint, ToolCall, Approval, Artifact, Event
# ============================================================

class NodeState(StrictModel):
    """节点状态"""
    current_node: NonEmptyString
    next_node: NonEmptyString | None = None


class CheckpointSpec(StrictModel):
    """Checkpoint 的 spec 部分"""
    run_ref: ObjectRef
    sequence: Annotated[int, Field(ge=1)]
    graph_state: dict[str, Any] | ArtifactRef
    node_state: NodeState
    context_digest: Digest
    side_effect_ledger: list[ObjectRef]
    pending_approvals: list[ObjectRef]
    pending_tool_calls: list[ObjectRef]
    resume_token_ref: SecretRef
    created_reason: Literal["periodic", "node_end", "approval", "interrupt", "error", "manual"]
    parent_checkpoint_ref: ObjectRef | None = None

    @model_validator(mode="after")
    def validate_checkpoint_refs(self) -> CheckpointSpec:
        if self.run_ref.kind != ResourceKind.AGENT_RUN:
            raise ValueError("run_ref must reference AgentRun")
        if any(ref.kind != ResourceKind.TOOL_CALL for ref in self.side_effect_ledger):
            raise ValueError("side_effect_ledger must contain ToolCall refs")
        if any(ref.kind != ResourceKind.APPROVAL for ref in self.pending_approvals):
            raise ValueError("pending_approvals must contain Approval refs")
        if any(ref.kind != ResourceKind.TOOL_CALL for ref in self.pending_tool_calls):
            raise ValueError("pending_tool_calls must contain ToolCall refs")
        if self.parent_checkpoint_ref and self.parent_checkpoint_ref.kind != ResourceKind.CHECKPOINT:
            raise ValueError("parent_checkpoint_ref must reference Checkpoint")
        return self


class CheckpointStatus(StrictModel):
    """Checkpoint 状态"""
    phase: Literal["committed"] = "committed"


class CheckpointResource(StrictModel):
    """Checkpoint 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Checkpoint"] = "Checkpoint"
    metadata: RuntimeMetadata
    spec: CheckpointSpec
    status: CheckpointStatus

    @model_validator(mode="after")
    def invariants(self) -> CheckpointResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        return self


class PermissionDecisionValue(StrEnum):
    """权限决策值"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PermissionDecision(StrictModel):
    """权限决策"""
    decision: PermissionDecisionValue
    policy_refs: Annotated[list[ResourceRef], Field(min_length=1)]
    reason_codes: Annotated[list[NonEmptyString], Field(min_length=1)]
    constraints: dict[str, Any] = Field(default_factory=dict)
    request_digest: Digest
    decision_digest: Digest

    @model_validator(mode="after")
    def policies_are_permissions(self) -> PermissionDecision:
        if any(ref.kind != ResourceKind.PERMISSION_PROFILE for ref in self.policy_refs):
            raise ValueError("permission decisions must reference PermissionProfile")
        return self


class ToolSnapshot(StrictModel):
    """工具快照"""
    tool_ref: ResourceRef
    side_effect: SideEffect
    risk_level: RiskLevel

    @model_validator(mode="after")
    def require_tool_ref(self) -> ToolSnapshot:
        if self.tool_ref.kind != ResourceKind.TOOL_MANIFEST:
            raise ValueError("tool_ref must reference ToolManifest")
        return self


class ToolCallSpec(StrictModel):
    """ToolCall 的 spec 部分"""
    run_ref: ObjectRef
    tool_snapshot: ToolSnapshot
    requested_by: ActorRef
    input: dict[str, Any] | ArtifactRef
    input_digest: Digest
    idempotency_key: Annotated[str, Field(min_length=8, max_length=512)] | None = None
    permission_decision: PermissionDecision
    approval_ref: ObjectRef | None = None
    execution_target: ExecutionLocation
    attempt: Annotated[int, Field(ge=1)]
    output: dict[str, Any] | ArtifactRef | None = None
    side_effect_receipt: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    usage: dict[str, Annotated[float, Field(ge=0)]] = Field(default_factory=dict)
    error: StandardError | None = None

    @model_validator(mode="after")
    def validate_call_controls(self) -> ToolCallSpec:
        if self.run_ref.kind != ResourceKind.AGENT_RUN:
            raise ValueError("run_ref must reference AgentRun")
        if self.tool_snapshot.side_effect != SideEffect.READ_ONLY and self.idempotency_key is None:
            raise ValueError("side-effect ToolCall requires idempotency_key")
        if self.approval_ref and self.approval_ref.kind != ResourceKind.APPROVAL:
            raise ValueError("approval_ref must reference Approval")
        return self


class ToolCallPhase(StrEnum):
    """ToolCall 生命周期状态"""
    PROPOSED = "proposed"
    VALIDATING = "validating"
    DENIED = "denied"
    WAITING_APPROVAL = "waiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class ToolCallStatus(StrictModel):
    """ToolCall 状态"""
    phase: ToolCallPhase


class ToolCallResource(StrictModel):
    """ToolCall 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ToolCall"] = "ToolCall"
    metadata: RuntimeMetadata
    spec: ToolCallSpec
    status: ToolCallStatus

    @model_validator(mode="after")
    def invariants(self) -> ToolCallResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        gated = {ToolCallPhase.SCHEDULED, ToolCallPhase.EXECUTING, ToolCallPhase.SUCCEEDED, ToolCallPhase.UNKNOWN}
        high_risk = self.spec.tool_snapshot.side_effect in {SideEffect.DESTRUCTIVE, SideEffect.PRIVILEGED}
        if high_risk and self.status.phase in gated and self.spec.approval_ref is None:
            raise ValueError("high-risk ToolCall requires Approval before scheduling or execution")
        if self.status.phase == ToolCallPhase.DENIED and self.spec.permission_decision.decision != PermissionDecisionValue.DENY:
            raise ValueError("denied ToolCall requires deny permission decision")
        return self


class RequestedAction(StrictModel):
    """请求的动作"""
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]
    resource: NonEmptyString


class ApproverRule(StrictModel):
    """审批人规则"""
    role: Key
    count: Annotated[int, Field(gt=0)]
    separation_of_duties: bool = False


class ApprovalDecisionEntry(StrictModel):
    """审批决策记录"""
    approver: ActorRef
    decision: Literal["approve", "reject", "revoke"]
    decided_at: AwareDatetime
    comment: Annotated[str, Field(max_length=2048)] | None = None


class ApprovalSpec(StrictModel):
    """Approval 的 spec 部分"""
    subject_ref: ObjectRef
    requester: ActorRef
    approval_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]
    risk_summary: NonEmptyString
    requested_actions: Annotated[list[RequestedAction], Field(min_length=1)]
    input_digest: Digest
    policy_snapshot: ResourceRef
    required_approvers: Annotated[list[ApproverRule], Field(min_length=1)]
    decisions: list[ApprovalDecisionEntry] = Field(default_factory=list)
    expires_at: AwareDatetime
    one_time: bool
    usage_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_approval_spec(self) -> ApprovalSpec:
        if self.policy_snapshot.kind != ResourceKind.PERMISSION_PROFILE:
            raise ValueError("policy_snapshot must reference PermissionProfile")
        if self.one_time and self.usage_count > 1:
            raise ValueError("one-time approval cannot be used more than once")
        return self


class ApprovalPhase(StrEnum):
    """Approval 生命周期状态"""
    REQUESTED = "requested"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONSUMED = "consumed"


class ApprovalStatus(StrictModel):
    """Approval 状态"""
    phase: ApprovalPhase


class ApprovalResource(StrictModel):
    """Approval 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Approval"] = "Approval"
    metadata: RuntimeMetadata
    spec: ApprovalSpec
    status: ApprovalStatus

    @model_validator(mode="after")
    def invariants(self) -> ApprovalResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        approvals = [entry for entry in self.spec.decisions if entry.decision == "approve"]
        rejections = [entry for entry in self.spec.decisions if entry.decision == "reject"]
        required_count = sum(rule.count for rule in self.spec.required_approvers)
        if self.status.phase in {ApprovalPhase.APPROVED, ApprovalPhase.CONSUMED} and len(approvals) < required_count:
            raise ValueError("approved or consumed status requires all approvers")
        if self.status.phase == ApprovalPhase.REJECTED and not rejections:
            raise ValueError("rejected status requires a reject decision")
        if self.status.phase == ApprovalPhase.CONSUMED and (not self.spec.one_time or self.spec.usage_count != 1):
            raise ValueError("consumed status requires one-time approval used exactly once")
        return self


class ArtifactLocator(StrictModel):
    """Artifact 位置"""
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    bucket_or_repository: NonEmptyString
    object_key: Annotated[str, Field(min_length=1, max_length=2048)]
    version_id: Annotated[str, Field(min_length=1, max_length=256)] | None = None

    @field_validator("object_key")
    @classmethod
    def locator_cannot_be_signed_url(cls, value: str) -> str:
        lowered = value.lower()
        forbidden = ("x-amz-signature", "sig=", "token=", "password=")
        if any(item in lowered for item in forbidden):
            raise ValueError("artifact locator cannot contain credentials or signed URL parameters")
        return value


class EncryptionSpec(StrictModel):
    """加密规格"""
    encrypted: bool
    algorithm: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    key_ref: SecretRef | None = None

    @model_validator(mode="after")
    def encrypted_requires_key(self) -> EncryptionSpec:
        if self.encrypted and (self.algorithm is None or self.key_ref is None):
            raise ValueError("encrypted artifact requires algorithm and key_ref")
        return self


class ArtifactProvenance(StrictModel):
    """Artifact 来源"""
    task_ref: ObjectRef | None = None
    run_ref: ObjectRef | None = None
    tool_call_ref: ObjectRef | None = None
    model_route_id: Key | None = None
    actor: ActorRef


class ArtifactSpec(StrictModel):
    """Artifact 的 spec 部分"""
    artifact_type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    media_type: Annotated[str, Field(pattern=r"^[a-z]+/[a-z0-9.+-]+$")]
    storage_provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    locator: ArtifactLocator
    content_digest: Digest | None = None
    size_bytes: Annotated[int, Field(ge=0)] | None = None
    encryption: EncryptionSpec
    classification: Literal["public", "internal", "confidential", "restricted"]
    provenance: ArtifactProvenance
    schema_ref: SchemaRef | None = None
    retention_policy: RetentionPolicy
    access_policy_ref: ResourceRef
    supersedes: ArtifactRef | None = None

    @model_validator(mode="after")
    def validate_access_policy(self) -> ArtifactSpec:
        if self.access_policy_ref.kind != ResourceKind.PERMISSION_PROFILE:
            raise ValueError("access_policy_ref must reference PermissionProfile")
        if self.classification in {"confidential", "restricted"} and not self.encryption.encrypted:
            raise ValueError("sensitive artifacts must be encrypted")
        return self


class ArtifactPhase(StrEnum):
    """Artifact 生命周期状态"""
    PENDING_UPLOAD = "pending_upload"
    AVAILABLE = "available"
    QUARANTINED = "quarantined"
    BLOCKED = "blocked"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ArtifactStatus(StrictModel):
    """Artifact 状态"""
    phase: ArtifactPhase


class ArtifactResource(StrictModel):
    """Artifact 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Artifact"] = "Artifact"
    metadata: RuntimeMetadata
    spec: ArtifactSpec
    status: ArtifactStatus

    @model_validator(mode="after")
    def invariants(self) -> ArtifactResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        if self.status.phase == ArtifactPhase.AVAILABLE and (self.spec.content_digest is None or self.spec.size_bytes is None):
            raise ValueError("available artifact requires digest and size")
        return self


class EventSpec(StrictModel):
    """Event 的 spec 部分（CloudEvents 兼容）"""
    specversion: Literal["1.0"] = "1.0"
    id: ResourceId
    source: Annotated[str, Field(pattern=r"^(?:|https?://)[^\s]{1,510}$")]
    type: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,255}$")]
    subject: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    time: AwareDatetime
    datacontenttype: Literal["application/json"] = "application/json"
    dataschema: Annotated[str, Field(pattern=r"^https://[^\s]{1,2040}$")]
    subject_ref: ObjectRef
    sequence: Annotated[int, Field(ge=1)]
    trace: TraceContext
    schema_ref: SchemaRef
    data: dict[str, Any]

    @field_validator("id")
    @classmethod
    def event_id_prefix(cls, value: str) -> str:
        if not value.startswith("evt_"):
            raise ValueError("CloudEvents id must use evt_ prefix")
        return value


class EventStatus(StrictModel):
    """Event 状态"""
    phase: Literal["recorded"] = "recorded"


class EventResource(StrictModel):
    """Event 完整资源"""
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Event"] = "Event"
    metadata: RuntimeMetadata
    spec: EventSpec
    status: EventStatus

    @model_validator(mode="after")
    def invariants(self) -> EventResource:
        expected = KIND_PREFIX[self.kind]
        if not self.metadata.id.startswith(expected):
            raise ValueError(f"metadata.id must use {expected} prefix for {self.kind}")
        if self.spec.id != self.metadata.id:
            raise ValueError("CloudEvents id must equal metadata.id")
        return self


# ============================================================
# 资源模型注册表
# ============================================================

RESOURCE_MODELS: dict[str, type[StrictModel]] = {
    "agent-spec": AgentSpecResource,
    "skill-manifest": SkillManifestResource,
    "tool-manifest": ToolManifestResource,
    "prompt-package": PromptPackageResource,
    "model-policy": ModelPolicyResource,
    "context-policy": ContextPolicyResource,
    "loop-profile": LoopProfileResource,
    "permission-profile": PermissionProfileResource,
    "task": TaskResource,
    "agent-run": AgentRunResource,
    "checkpoint": CheckpointResource,
    "tool-call": ToolCallResource,
    "approval": ApprovalResource,
    "artifact": ArtifactResource,
    "event": EventResource,
}


COMMON_MODELS: dict[str, type[StrictModel]] = {
    "standard-error": StandardError,
}


print(f"models.py 完整版创建完成！")
print(f"已定义 {len(RESOURCE_MODELS)} 个资源模型")
