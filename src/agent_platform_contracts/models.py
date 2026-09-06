"""B0 contract reference models.

The models are the executable source for the JSON Schema 2020-12 artifacts.
They intentionally reject undeclared fields and encode cross-field invariants
that JSON Schema alone cannot express without implementation-specific code.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

API_VERSION = "agent-platform/v1alpha1"
SEMVER_PATTERN = (
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
DIGEST_PATTERN = r"^sha256:[0-9a-f]{64}$"
UUID7_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
RESOURCE_ID_PATTERN = rf"^(?:ten|usr|prj|agt|skl|tol|prm|mpo|cpo|lop|pep|tsk|run|ckp|tcl|apr|art|evt)_{UUID7_PATTERN}$"  # noqa: E501

SemVer = Annotated[str, Field(pattern=SEMVER_PATTERN)]
Digest = Annotated[str, Field(pattern=DIGEST_PATTERN)]
ResourceId = Annotated[str, Field(pattern=RESOURCE_ID_PATTERN)]
SchemaId = Annotated[str, Field(pattern=r"^sch_[a-z0-9][a-z0-9._-]{2,127}$")]
Key = Annotated[
    str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,126}[a-z0-9]$", min_length=3, max_length=128)
]
Namespace = Annotated[
    str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,126}[a-z0-9]$", min_length=2, max_length=128)
]
NonEmptyString = Annotated[str, Field(min_length=1, max_length=4096)]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=True,
        protected_namespaces=(),
    )


class ScopeType(StrEnum):
    SYSTEM = "system"
    TENANT = "tenant"
    USER = "user"
    PROJECT = "project"
    SESSION = "session"


class ResourceKind(StrEnum):
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


class Scope(StrictModel):
    type: ScopeType
    tenant_id: ResourceId | None = None
    user_id: ResourceId | None = None
    project_id: ResourceId | None = None
    session_id: Annotated[str, Field(pattern=r"^ses_[A-Za-z0-9._:-]{3,128}$")] | None = None

    @model_validator(mode="after")
    def validate_scope_members(self) -> Scope:
        if self.type != ScopeType.SYSTEM and self.tenant_id is None:
            raise ValueError("tenant_id is required outside system scope")
        if self.tenant_id is not None and not self.tenant_id.startswith("ten_"):
            raise ValueError("tenant_id must use ten_ prefix")
        if (
            self.type in {ScopeType.USER, ScopeType.PROJECT, ScopeType.SESSION}
            and self.user_id is None
        ):
            raise ValueError("user_id is required for user, project, and session scope")
        if self.user_id is not None and not self.user_id.startswith("usr_"):
            raise ValueError("user_id must use usr_ prefix")
        if self.type in {ScopeType.PROJECT, ScopeType.SESSION} and self.project_id is None:
            raise ValueError("project_id is required for project and session scope")
        if self.project_id is not None and not self.project_id.startswith("prj_"):
            raise ValueError("project_id must use prj_ prefix")
        if self.type == ScopeType.SESSION and self.session_id is None:
            raise ValueError("session_id is required for session scope")
        return self


class ActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SERVICE = "service"
    SYSTEM = "system"


class ActorRef(StrictModel):
    actor_type: ActorType
    actor_id: NonEmptyString
    tenant_id: ResourceId | None = None

    @model_validator(mode="after")
    def validate_actor_prefix(self) -> ActorRef:
        expected = {"user": "usr_", "agent": "agt_"}.get(str(self.actor_type))
        if expected and not self.actor_id.startswith(expected):
            raise ValueError(f"actor_id must use {expected} prefix for {self.actor_type}")
        if self.tenant_id is not None and not self.tenant_id.startswith("ten_"):
            raise ValueError("tenant_id must use ten_ prefix")
        return self


class DefinitionMetadata(StrictModel):
    id: ResourceId
    key: Key
    namespace: Namespace
    version: SemVer
    revision: Annotated[int, Field(ge=1)]
    scope: Scope
    labels: dict[
        Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._/-]{0,62}$")],
        Annotated[str, Field(max_length=256)],
    ] = Field(default_factory=dict)
    annotations: dict[
        Annotated[str, Field(max_length=128)], Annotated[str, Field(max_length=2048)]
    ] = Field(default_factory=dict)
    content_digest: Digest
    created_at: AwareDatetime
    created_by: ActorRef


class RuntimeMetadata(StrictModel):
    id: ResourceId
    revision: Annotated[int, Field(ge=1)]
    scope: Scope
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    created_at: AwareDatetime
    created_by: ActorRef
    updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_updated_at(self) -> RuntimeMetadata:
        if self.updated_at is not None and self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class DefinitionPhase(StrEnum):
    PROPOSED = "proposed"
    DRAFT = "draft"
    TESTING = "testing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class ResolutionPurpose(StrEnum):
    NEW_RUN = "new_run"
    RESUME_RUN = "resume_run"


class DefinitionStatus(StrictModel):
    phase: DefinitionPhase
    observed_revision: Annotated[int, Field(ge=1)]
    reason: Annotated[str, Field(max_length=2048)] | None = None
    activated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def active_requires_timestamp(self) -> DefinitionStatus:
        if self.phase == DefinitionPhase.ACTIVE and self.activated_at is None:
            raise ValueError("active definitions require activated_at")
        return self


class ResourceRef(StrictModel):
    kind: ResourceKind
    id: ResourceId
    version: SemVer
    digest: Digest

    @model_validator(mode="after")
    def validate_kind_id(self) -> ResourceRef:
        expected = KIND_PREFIX[str(self.kind)]
        if not self.id.startswith(expected):
            raise ValueError(f"id must use {expected} prefix for {self.kind}")
        if self.kind not in DEFINITION_KINDS:
            raise ValueError("ResourceRef with semantic version must target a definition resource")
        return self


class ObjectRef(StrictModel):
    kind: ResourceKind
    id: ResourceId

    @model_validator(mode="after")
    def validate_kind_id(self) -> ObjectRef:
        expected = KIND_PREFIX[str(self.kind)]
        if not self.id.startswith(expected):
            raise ValueError(f"id must use {expected} prefix for {self.kind}")
        return self


class SchemaRef(StrictModel):
    id: SchemaId
    version: SemVer
    digest: Digest


class ArtifactRef(StrictModel):
    kind: Literal["Artifact"] = "Artifact"
    id: ResourceId
    digest: Digest

    @field_validator("id")
    @classmethod
    def artifact_prefix(cls, value: str) -> str:
        if not value.startswith("art_"):
            raise ValueError("ArtifactRef id must use art_ prefix")
        return value


class SecretRef(StrictModel):
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    key: Annotated[str, Field(min_length=1, max_length=512)]
    version: Annotated[int, Field(ge=1)] | str
    field: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")]


class TraceContext(StrictModel):
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    span_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
    parent_span_id: Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")] | None = None
    correlation_id: Annotated[str, Field(pattern=r"^corr_[A-Za-z0-9._:-]{3,128}$")]


class PriceSnapshotRef(StrictModel):
    snapshot_id: Annotated[str, Field(pattern=r"^price_[A-Za-z0-9._:-]{3,128}$")]
    version: SemVer
    effective_at: AwareDatetime
    digest: Digest


class Budget(StrictModel):
    max_wall_time_seconds: Annotated[int, Field(gt=0)]
    max_model_input_tokens: Annotated[int, Field(ge=0)] | None = None
    max_model_output_tokens: Annotated[int, Field(ge=0)] | None = None
    max_model_tokens: Annotated[int, Field(gt=0)]
    max_cost_usd: Annotated[Decimal, Field(ge=0)]
    max_tool_calls: Annotated[int, Field(ge=0)]
    max_iterations: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def validate_token_budget(self) -> Budget:
        if (
            self.max_model_input_tokens is not None
            and self.max_model_input_tokens > self.max_model_tokens
        ):
            raise ValueError("max_model_input_tokens cannot exceed max_model_tokens")
        if (
            self.max_model_output_tokens is not None
            and self.max_model_output_tokens > self.max_model_tokens
        ):
            raise ValueError("max_model_output_tokens cannot exceed max_model_tokens")
        if self.max_model_input_tokens is not None and self.max_model_output_tokens is not None:
            if self.max_model_input_tokens + self.max_model_output_tokens > self.max_model_tokens:
                raise ValueError("input and output token budgets exceed max_model_tokens")
        return self


class Usage(StrictModel):
    wall_time_seconds: Annotated[float, Field(ge=0)] = 0
    model_input_tokens: Annotated[int, Field(ge=0)] = 0
    model_output_tokens: Annotated[int, Field(ge=0)] = 0
    model_tokens: Annotated[int, Field(ge=0)] = 0
    cost_usd: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    tool_calls: Annotated[int, Field(ge=0)] = 0
    iterations: Annotated[int, Field(ge=0)] = 0
    price_snapshot_ref: PriceSnapshotRef

    @model_validator(mode="after")
    def validate_token_usage(self) -> Usage:
        if self.model_input_tokens + self.model_output_tokens != self.model_tokens:
            raise ValueError("model_tokens must equal input plus output tokens")
        return self


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    APPROVAL = "approval"
    BUDGET = "budget"
    MODEL = "model"
    TOOL = "tool"
    DEPENDENCY = "dependency"
    CONFLICT = "conflict"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


class ErrorSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class StandardError(StrictModel):
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")]
    category: ErrorCategory
    message: Annotated[str, Field(min_length=1, max_length=4096)]
    retryable: bool
    safe_to_retry: bool
    severity: ErrorSeverity
    details: dict[str, Any] = Field(default_factory=dict)
    cause_ref: Annotated[str, Field(pattern=r"^evt_[0-9a-f-]{36}$")] | None = None
    occurred_at: AwareDatetime

    @model_validator(mode="after")
    def safe_retry_implies_retryable(self) -> StandardError:
        if self.safe_to_retry and not self.retryable:
            raise ValueError("safe_to_retry requires retryable")
        return self


class ContextSection(StrictModel):
    type: ContextSourceType | Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    priority: Annotated[int, Field(ge=0, le=100)]
    token_count: Annotated[int, Field(ge=0)]
    provenance_refs: Annotated[list[NonEmptyString], Field(min_length=1)]
    content_digest: Digest


class RedactionSummary(StrictModel):
    secret_count: Annotated[int, Field(ge=0)]
    pii_count: Annotated[int, Field(ge=0)]
    restricted_count: Annotated[int, Field(ge=0)] = 0


class ContextPackage(StrictModel):
    run_ref: ObjectRef
    model_call_sequence: Annotated[int, Field(ge=1)]
    policy_ref: ResourceRef
    sections: Annotated[list[ContextSection], Field(min_length=1)]
    total_tokens: Annotated[int, Field(ge=0)]
    redaction_summary: RedactionSummary
    content_digest: Digest
    artifact_ref: ArtifactRef

    @model_validator(mode="after")
    def validate_context_package(self) -> ContextPackage:
        if self.run_ref.kind != ResourceKind.AGENT_RUN:
            raise ValueError("run_ref must reference AgentRun")
        if self.policy_ref.kind != ResourceKind.CONTEXT_POLICY:
            raise ValueError("policy_ref must reference ContextPolicy")
        if sum(section.token_count for section in self.sections) != self.total_tokens:
            raise ValueError("total_tokens must equal the sum of section token counts")
        return self


class MemoryPolicy(StrictModel):
    readable_scopes: list[ScopeType]
    writable_scopes: list[ScopeType]
    write_requires_approval: bool
    max_retention_days: Annotated[int, Field(ge=1)]
    allow_cross_user: Literal[False] = False
    allow_cross_tenant: Literal[False] = False


class ApprovalDefaults(StrictModel):
    external_send: bool = True
    destructive: Literal[True] = True
    privileged: Literal[True] = True
    approval_ttl_seconds: Annotated[int, Field(gt=0)]


class ConcurrencyPolicy(StrictModel):
    max_parallel_tasks: Annotated[int, Field(gt=0)]
    max_parallel_runs_per_task: Annotated[int, Field(gt=0)]
    serialization_key_template: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class BindingSelector(StrictModel):
    domain: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")] | None = None
    namespace: Namespace | None = None
    status: Literal["active"] = "active"
    labels: dict[str, str] = Field(default_factory=dict)


class Binding(StrictModel):
    selector: BindingSelector
    max_candidates: Annotated[int, Field(ge=1, le=100)]


class AgentSpecSpec(StrictModel):
    purpose: NonEmptyString
    domain: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    goals: Annotated[list[NonEmptyString], Field(min_length=1)]
    non_goals: Annotated[list[NonEmptyString], Field(min_length=1)]
    input_schema_ref: SchemaRef
    output_schema_ref: SchemaRef
    prompt_package_ref: ResourceRef
    context_policy_ref: ResourceRef
    model_policy_ref: ResourceRef
    loop_profile_ref: ResourceRef
    permission_profile_ref: ResourceRef
    skill_bindings: list[Binding] = Field(default_factory=list)
    tool_bindings: list[Binding] = Field(default_factory=list)
    memory_policy: MemoryPolicy
    budget_defaults: Budget
    approval_defaults: ApprovalDefaults
    concurrency_policy: ConcurrencyPolicy
    eval_suite_refs: Annotated[list[ArtifactRef], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_reference_kinds(self) -> AgentSpecSpec:
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


class TriggerExamples(StrictModel):
    positive: Annotated[list[NonEmptyString], Field(min_length=1)]
    negative: Annotated[list[NonEmptyString], Field(min_length=1)]


class ToolRequirement(StrictModel):
    tool_ref: ResourceRef
    required_capabilities: list[NonEmptyString] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_tool(self) -> ToolRequirement:
        if self.tool_ref.kind != ResourceKind.TOOL_MANIFEST:
            raise ValueError("tool_ref must reference ToolManifest")
        return self


class SkillRequirement(StrictModel):
    skill_ref: ResourceRef
    optional: bool = False

    @model_validator(mode="after")
    def require_skill(self) -> SkillRequirement:
        if self.skill_ref.kind != ResourceKind.SKILL_MANIFEST:
            raise ValueError("skill_ref must reference SkillManifest")
        return self


class PermissionRequest(StrictModel):
    actions: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]], Field(min_length=1)
    ]
    resources: Annotated[list[NonEmptyString], Field(min_length=1)]
    conditions: dict[str, Any] = Field(default_factory=dict)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuntimeRequirements(StrictModel):
    operating_systems: list[Literal["linux", "windows", "macos", "any"]]
    binaries: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_.+-]{1,128}$")]] = Field(
        default_factory=list
    )
    network_domains: list[Annotated[str, Field(pattern=r"^(?:[a-z0-9-]+\.)+[a-z]{2,63}$")]] = Field(
        default_factory=list
    )
    has_scripts: bool
    sandbox_required: bool
    sandbox_profile: Annotated[str, Field(min_length=1, max_length=128)] | None = None

    @model_validator(mode="after")
    def scripts_require_sandbox(self) -> RuntimeRequirements:
        if self.has_scripts and (not self.sandbox_required or self.sandbox_profile is None):
            raise ValueError("skills with scripts require a named sandbox profile")
        return self


class ContextBudget(StrictModel):
    max_skill_tokens: Annotated[int, Field(gt=0)]
    max_reference_tokens: Annotated[int, Field(ge=0)]
    max_total_tokens: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def parts_fit_total(self) -> ContextBudget:
        if self.max_skill_tokens + self.max_reference_tokens > self.max_total_tokens:
            raise ValueError("skill and reference token budgets exceed total")
        return self


class SourceRepository(StrictModel):
    repository: Annotated[str, Field(min_length=1, max_length=512)]
    commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    path: Annotated[str, Field(min_length=1, max_length=1024)]


class EvalSummary(StrictModel):
    trigger_precision: Annotated[float, Field(ge=0, le=1)]
    trigger_recall: Annotated[float, Field(ge=0, le=1)]
    output_pass_rate: Annotated[float, Field(ge=0, le=1)]
    security_passed: bool
    regression_passed: bool
    evaluated_cases: Annotated[int, Field(gt=0)]
    evaluated_at: AwareDatetime


class ProvenanceType(StrEnum):
    HUMAN = "human"
    HERMES_PROPOSAL = "hermes_proposal"
    EXTERNAL = "external"
    IMPORTED = "imported"


class DefinitionProvenance(StrictModel):
    type: ProvenanceType
    actor: ActorRef
    source_ref: NonEmptyString | None = None


class SkillManifestSpec(StrictModel):
    portable_name: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")]
    description: Annotated[str, Field(min_length=20, max_length=2048)]
    domain: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]], Field(min_length=1)
    ]
    tags: list[Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]] = Field(
        default_factory=list
    )
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
        for ref in self.conflicts_with:
            if ref.kind != ResourceKind.SKILL_MANIFEST:
                raise ValueError("conflicts_with must reference SkillManifest")
        ids = [requirement.skill_ref.id for requirement in self.required_skills]
        if len(ids) != len(set(ids)):
            raise ValueError("required_skills cannot contain duplicates")
        return self


class ToolTransport(StrEnum):
    LOCAL = "local"
    HTTP = "http"
    GRPC = "grpc"
    MCP = "mcp"
    OPENCLAW = "openclaw"


class SideEffect(StrEnum):
    READ_ONLY = "read_only"
    LOCAL_WRITE = "local_write"
    EXTERNAL_WRITE = "external_write"
    EXTERNAL_SEND = "external_send"
    DESTRUCTIVE = "destructive"
    PRIVILEGED = "privileged"


class ExecutionLocation(StrEnum):
    CLOUD = "cloud"
    LOCAL = "local"
    SANDBOX = "sandbox"
    DEVICE = "device"
    GPU = "gpu"


class EndpointRef(StrictModel):
    service_id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    endpoint_key: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:/-]{1,255}$")]


class IdempotencyPolicy(StrictModel):
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
    connect_timeout_seconds: Annotated[float, Field(gt=0)]
    execution_timeout_seconds: Annotated[float, Field(gt=0)]


class RetryPolicy(StrictModel):
    max_attempts: Annotated[int, Field(ge=1)]
    retryable_error_codes: list[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")]]
    backoff: Literal["none", "fixed", "exponential"]
    base_delay_seconds: Annotated[float, Field(ge=0)]
    requires_safe_to_retry: Literal[True] = True


class RateLimit(StrictModel):
    requests: Annotated[int, Field(gt=0)]
    per_seconds: Annotated[int, Field(gt=0)]


class ApprovalRequirement(StrictModel):
    mode: Literal["none", "conditional", "always"]
    conditions: list[NonEmptyString] = Field(default_factory=list)


class HealthContract(StrictModel):
    healthcheck_key: Annotated[str, Field(min_length=1, max_length=256)]
    interval_seconds: Annotated[int, Field(gt=0)]
    unhealthy_after_failures: Annotated[int, Field(gt=0)]


class ToolManifestSpec(StrictModel):
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    capability: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]
    domain: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]], Field(min_length=1)
    ]
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
        if self.side_effect != SideEffect.READ_ONLY and not self.idempotency.supported:
            raise ValueError("side-effect tools must support scoped idempotency")
        if (
            self.side_effect in {SideEffect.DESTRUCTIVE, SideEffect.PRIVILEGED}
            and self.approval_requirement.mode != "always"
        ):
            raise ValueError("destructive and privileged tools require approval always")
        if self.execution_location == ExecutionLocation.SANDBOX and self.sandbox_profile is None:
            raise ValueError("sandbox execution requires sandbox_profile")
        return self


class PromptLayer(StrEnum):
    SAFETY = "safety"
    IDENTITY = "identity"
    DOMAIN = "domain"
    BEHAVIOR = "behavior"
    OUTPUT_CONTRACT = "output_contract"
    ERROR_POLICY = "error_policy"


class PromptFragment(StrictModel):
    name: Key
    layer: PromptLayer
    order: Annotated[int, Field(ge=0)]
    content: Annotated[str, Field(min_length=1, max_length=20000)]


class ModelCompatibility(StrictModel):
    required_capabilities: list[
        Literal["tool_calling", "vision", "long_context", "structured_output", "reasoning"]
    ]
    provider_allowlist: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]], Field(min_length=1)
    ]


class PromptPackageSpec(StrictModel):
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


class ModelRoute(StrictModel):
    route_id: Key
    provider: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")]
    model: NonEmptyString
    priority: Annotated[int, Field(ge=0)]
    required_capabilities: list[NonEmptyString]
    conditions: dict[str, Any] = Field(default_factory=dict)


class DataClassificationRule(StrictModel):
    classification: Literal["public", "internal", "confidential", "restricted"]
    allowed_providers: list[NonEmptyString]
    require_local: bool = False


class FallbackStep(StrictModel):
    route_id: Key
    on_error_codes: Annotated[list[NonEmptyString], Field(min_length=1)]


class CircuitBreaker(StrictModel):
    failure_threshold: Annotated[int, Field(gt=0)]
    window_seconds: Annotated[int, Field(gt=0)]
    open_seconds: Annotated[int, Field(gt=0)]


class ModelPolicySpec(StrictModel):
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


class ContextSourceType(StrEnum):
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
    source: ContextSourceType
    effect: Literal["allow", "deny"]
    priority: Annotated[int, Field(ge=0, le=100)]
    filters: dict[str, Any] = Field(default_factory=dict)


class ContextTokenBudget(StrictModel):
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
    top_k: Annotated[int, Field(ge=1, le=100)]
    similarity_threshold: Annotated[float, Field(ge=0, le=1)]
    metadata_token_limit: Annotated[int, Field(gt=0)]


class ToolSelection(StrictModel):
    max_visible_tools: Annotated[int, Field(ge=1, le=256)]
    schema_token_limit: Annotated[int, Field(gt=0)]


class ContextMemoryScope(StrictModel):
    allowed_scopes: list[ScopeType]
    allow_cross_user: Literal[False] = False
    allow_cross_tenant: Literal[False] = False


class FreshnessPolicy(StrictModel):
    default_ttl_seconds: Annotated[int, Field(ge=0)]
    source_ttl_seconds: dict[ContextSourceType, Annotated[int, Field(ge=0)]] = Field(
        default_factory=dict
    )


class DeduplicationPolicy(StrictModel):
    strategy: Literal["digest", "semantic", "hybrid"]
    similarity_threshold: Annotated[float, Field(ge=0, le=1)] | None = None


class CompactionPolicy(StrictModel):
    strategy: Literal["extractive", "abstractive", "hybrid"]
    target_ratio: Annotated[float, Field(gt=0, le=1)]
    preserve_provenance: Literal[True] = True


class RedactionPolicy(StrictModel):
    redact_secrets: Literal[True] = True
    pii_mode: Literal["none", "mask", "remove"]
    restricted_data_mode: Literal["deny", "local_only", "mask"]


class SnapshotPolicy(StrictModel):
    persist: bool
    store_content: bool
    retention_days: Annotated[int, Field(ge=1)]
    require_digest: Literal[True] = True


class ContextPolicySpec(StrictModel):
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


class LoopStrategy(StrEnum):
    SINGLE_PASS = "single_pass"
    REACT = "react"
    REPAIR = "repair"
    RALPH = "ralph"
    REVIEW_REFINE = "review_refine"


class StopCondition(StrictModel):
    condition_type: Literal["success", "failure", "budget", "human_stop", "validator"]
    expression: NonEmptyString


class CheckpointPolicy(StrictModel):
    interval_iterations: Annotated[int, Field(gt=0)]
    on_tool_side_effect: bool
    on_human_interrupt: Literal[True] = True
    on_node_end: bool


class LoopRetryPolicy(StrictModel):
    max_model_retries: Annotated[int, Field(ge=0)]
    max_node_retries: Annotated[int, Field(ge=0)]
    backoff: Literal["none", "fixed", "exponential"]


class HumanInterrupt(StrictModel):
    stage: NonEmptyString
    reason: NonEmptyString
    required: bool


class ProgressPolicy(StrictModel):
    emit_every_iterations: Annotated[int, Field(gt=0)]
    persist_summary: bool


class RollbackPolicy(StrictModel):
    strategy: Literal["none", "compensating_action", "manual"]
    compensation_tool_refs: list[ResourceRef] = Field(default_factory=list)


class LoopProfileSpec(StrictModel):
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


class PermissionEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PermissionRule(StrictModel):
    effect: PermissionEffect
    actions: Annotated[
        list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]], Field(min_length=1)
    ]
    resources: Annotated[list[NonEmptyString], Field(min_length=1)]
    conditions: dict[str, Any] = Field(default_factory=dict)


class PermissionProfileSpec(StrictModel):
    roles: list[Key] = Field(default_factory=list)
    rules: Annotated[list[PermissionRule], Field(min_length=1)]
    capabilities: list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]] = Field(
        default_factory=list
    )
    default_decision: Literal["deny"] = "deny"
    deny_precedence: Literal[True] = True
    cross_tenant_default: Literal["deny"] = "deny"


class TaskSource(StrictModel):
    type: Literal["openclaw", "api", "cron", "webhook", "ui", "system"]
    channel: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    source_message_id: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class RoutingConstraints(StrictModel):
    allowed_agent_refs: list[ResourceRef] = Field(default_factory=list)
    allowed_domains: list[NonEmptyString] = Field(default_factory=list)
    required_model_capabilities: list[NonEmptyString] = Field(default_factory=list)


class Schedule(StrictModel):
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
    actions: list[NonEmptyString]
    resources: list[NonEmptyString]
    expires_at: AwareDatetime | None = None


class RetentionPolicy(StrictModel):
    retain_days: Annotated[int, Field(ge=1)]
    delete_after: AwareDatetime | None = None
    legal_hold: bool = False


class TaskSpec(StrictModel):
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
        if (
            self.approval_policy_ref
            and self.approval_policy_ref.kind != ResourceKind.PERMISSION_PROFILE
        ):
            raise ValueError("approval_policy_ref must reference PermissionProfile")
        return self


class TaskPhase(StrEnum):
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


class WorkerRef(StrictModel):
    worker_id: Annotated[str, Field(pattern=r"^wrk_[A-Za-z0-9._:-]{3,128}$")]
    service: Key
    instance: NonEmptyString


class Lease(StrictModel):
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
    INITIAL = "initial"
    FALLBACK = "fallback"


class ModelSelectionRecord(StrictModel):
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
        if (
            self.selection_reason == ModelSelectionReason.FALLBACK
            and self.trigger_error_code is None
        ):
            raise ValueError("fallback selection requires trigger_error_code")
        if (
            self.selection_reason == ModelSelectionReason.INITIAL
            and self.trigger_error_code is not None
        ):
            raise ValueError("initial selection cannot declare trigger_error_code")
        if self.event_ref.kind != ResourceKind.EVENT:
            raise ValueError("event_ref must reference Event")
        return self


class GraphRef(StrictModel):
    graph_id: Annotated[str, Field(pattern=r"^grf_[A-Za-z0-9._:-]{3,128}$")]
    version: SemVer
    node_id: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class AgentRunSpec(StrictModel):
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
        if (
            self.current_checkpoint_ref
            and self.current_checkpoint_ref.kind != ResourceKind.CHECKPOINT
        ):
            raise ValueError("current_checkpoint_ref must reference Checkpoint")
        activation_sequences = [item.sequence for item in self.dynamic_dependency_activations]
        if activation_sequences != list(range(1, len(activation_sequences) + 1)):
            raise ValueError("dynamic dependency activation sequences must be contiguous from 1")
        activated_refs = [
            (
                item.resource_ref.kind,
                item.resource_ref.id,
                item.resource_ref.version,
                item.resource_ref.digest,
            )
            for item in self.dynamic_dependency_activations
        ]
        if len(activated_refs) != len(set(activated_refs)):
            raise ValueError("a dynamic dependency cannot be activated twice in one run")
        startup_refs = {
            (item.kind, item.id, item.version, item.digest)
            for item in self.resolved_dependencies.startup_skill_refs
            + self.resolved_dependencies.startup_tool_refs
        }
        if startup_refs.intersection(activated_refs):
            raise ValueError("dynamic dependency cannot duplicate a startup-frozen dependency")
        model_sequences = [item.sequence for item in self.model_selection_history]
        if model_sequences != list(range(1, len(model_sequences) + 1)):
            raise ValueError("model selection sequences must be contiguous from 1")
        if self.model_selection_history[0].selection_reason != ModelSelectionReason.INITIAL:
            raise ValueError("first model selection must be initial")
        if any(
            item.selection_reason != ModelSelectionReason.FALLBACK
            for item in self.model_selection_history[1:]
        ):
            raise ValueError("later model selections must be fallback selections")
        route_ids = [item.route_id for item in self.model_selection_history]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("model fallback cannot revisit a route in one run")
        if self.current_model_selection != self.model_selection_history[-1]:
            raise ValueError(
                "current_model_selection must equal the last model_selection_history record"
            )
        frozen_price = self.resolved_dependencies.price_snapshot_ref
        for selection in self.model_selection_history:
            if (
                selection.price_snapshot_ref.version != frozen_price.version
                or selection.price_snapshot_ref.digest != frozen_price.digest
            ):
                raise ValueError("model selections must use the run-frozen price snapshot")
        if (
            self.usage.model_tokens > self.budget.max_model_tokens
            or self.usage.cost_usd > self.budget.max_cost_usd
        ):
            raise ValueError("run usage cannot exceed run budget")
        return self


class AgentRunPhase(StrEnum):
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
    phase: AgentRunPhase
    reason: Annotated[str, Field(max_length=2048)] | None = None


class NodeState(StrictModel):
    current_node: NonEmptyString
    next_node: NonEmptyString | None = None


class CheckpointSpec(StrictModel):
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
        if (
            self.parent_checkpoint_ref
            and self.parent_checkpoint_ref.kind != ResourceKind.CHECKPOINT
        ):
            raise ValueError("parent_checkpoint_ref must reference Checkpoint")
        return self


class CheckpointStatus(StrictModel):
    phase: Literal["committed"] = "committed"


class PermissionDecisionValue(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class PermissionDecision(StrictModel):
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
    tool_ref: ResourceRef
    side_effect: SideEffect
    risk_level: RiskLevel

    @model_validator(mode="after")
    def require_tool_ref(self) -> ToolSnapshot:
        if self.tool_ref.kind != ResourceKind.TOOL_MANIFEST:
            raise ValueError("tool_ref must reference ToolManifest")
        return self


class ToolCallSpec(StrictModel):
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
    phase: ToolCallPhase


class RequestedAction(StrictModel):
    action: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.:-]{2,127}$")]
    resource: NonEmptyString


class ApproverRule(StrictModel):
    role: Key
    count: Annotated[int, Field(gt=0)]
    separation_of_duties: bool = False


class ApprovalDecisionEntry(StrictModel):
    approver: ActorRef
    decision: Literal["approve", "reject", "revoke"]
    decided_at: AwareDatetime
    comment: Annotated[str, Field(max_length=2048)] | None = None


class ApprovalSpec(StrictModel):
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
    REQUESTED = "requested"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    REVOKED = "revoked"
    CONSUMED = "consumed"


class ApprovalStatus(StrictModel):
    phase: ApprovalPhase


class ArtifactLocator(StrictModel):
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
    encrypted: bool
    algorithm: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    key_ref: SecretRef | None = None

    @model_validator(mode="after")
    def encrypted_requires_key(self) -> EncryptionSpec:
        if self.encrypted and (self.algorithm is None or self.key_ref is None):
            raise ValueError("encrypted artifact requires algorithm and key_ref")
        return self


class ArtifactProvenance(StrictModel):
    task_ref: ObjectRef | None = None
    run_ref: ObjectRef | None = None
    tool_call_ref: ObjectRef | None = None
    model_route_id: Key | None = None
    actor: ActorRef


class ArtifactSpec(StrictModel):
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
    PENDING_UPLOAD = "pending_upload"
    AVAILABLE = "available"
    QUARANTINED = "quarantined"
    BLOCKED = "blocked"
    ARCHIVED = "archived"
    DELETED = "deleted"


class ArtifactStatus(StrictModel):
    phase: ArtifactPhase


class EventSpec(StrictModel):
    specversion: Literal["1.0"] = "1.0"
    id: ResourceId
    source: Annotated[str, Field(pattern=r"^(?:/|https?://)[^\s]{1,510}$")]
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
    phase: Literal["recorded"] = "recorded"


def _validate_resource_identity(kind: str, metadata: DefinitionMetadata | RuntimeMetadata) -> None:
    expected = KIND_PREFIX[kind]
    if not metadata.id.startswith(expected):
        raise ValueError(f"metadata.id must use {expected} prefix for {kind}")


class AgentSpecResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["AgentSpec"] = "AgentSpec"
    metadata: DefinitionMetadata
    spec: AgentSpecSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> AgentSpecResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class SkillManifestResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["SkillManifest"] = "SkillManifest"
    metadata: DefinitionMetadata
    spec: SkillManifestSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> SkillManifestResource:
        _validate_resource_identity(self.kind, self.metadata)
        if (
            self.spec.provenance.type == ProvenanceType.HERMES_PROPOSAL
            and self.status.phase not in {DefinitionPhase.PROPOSED, DefinitionPhase.DRAFT}
        ):
            raise ValueError("Hermes proposals may only be proposed or draft")
        if self.status.phase == DefinitionPhase.ACTIVE:
            if not (
                self.spec.eval_summary.security_passed and self.spec.eval_summary.regression_passed
            ):
                raise ValueError(
                    "active skill requires passing security and regression evaluations"
                )
        return self


class ToolManifestResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ToolManifest"] = "ToolManifest"
    metadata: DefinitionMetadata
    spec: ToolManifestSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> ToolManifestResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class PromptPackageResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["PromptPackage"] = "PromptPackage"
    metadata: DefinitionMetadata
    spec: PromptPackageSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> PromptPackageResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class ModelPolicyResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ModelPolicy"] = "ModelPolicy"
    metadata: DefinitionMetadata
    spec: ModelPolicySpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> ModelPolicyResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class ContextPolicyResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ContextPolicy"] = "ContextPolicy"
    metadata: DefinitionMetadata
    spec: ContextPolicySpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> ContextPolicyResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class LoopProfileResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["LoopProfile"] = "LoopProfile"
    metadata: DefinitionMetadata
    spec: LoopProfileSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> LoopProfileResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class PermissionProfileResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["PermissionProfile"] = "PermissionProfile"
    metadata: DefinitionMetadata
    spec: PermissionProfileSpec
    status: DefinitionStatus

    @model_validator(mode="after")
    def invariants(self) -> PermissionProfileResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class TaskResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Task"] = "Task"
    metadata: RuntimeMetadata
    spec: TaskSpec
    status: TaskStatus

    @model_validator(mode="after")
    def invariants(self) -> TaskResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class AgentRunResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["AgentRun"] = "AgentRun"
    metadata: RuntimeMetadata
    spec: AgentRunSpec
    status: AgentRunStatus

    @model_validator(mode="after")
    def invariants(self) -> AgentRunResource:
        _validate_resource_identity(self.kind, self.metadata)
        if (
            self.status.phase in {AgentRunPhase.RUNNING, AgentRunPhase.WAITING_TOOL}
            and self.spec.lease is None
        ):
            raise ValueError("executing run requires an active lease snapshot")
        if self.status.phase == AgentRunPhase.SUCCEEDED and not self.spec.output_artifact_refs:
            raise ValueError("succeeded run requires output artifacts")
        return self


class CheckpointResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Checkpoint"] = "Checkpoint"
    metadata: RuntimeMetadata
    spec: CheckpointSpec
    status: CheckpointStatus

    @model_validator(mode="after")
    def invariants(self) -> CheckpointResource:
        _validate_resource_identity(self.kind, self.metadata)
        return self


class ToolCallResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["ToolCall"] = "ToolCall"
    metadata: RuntimeMetadata
    spec: ToolCallSpec
    status: ToolCallStatus

    @model_validator(mode="after")
    def invariants(self) -> ToolCallResource:
        _validate_resource_identity(self.kind, self.metadata)
        gated = {
            ToolCallPhase.SCHEDULED,
            ToolCallPhase.EXECUTING,
            ToolCallPhase.SUCCEEDED,
            ToolCallPhase.UNKNOWN,
        }
        high_risk = self.spec.tool_snapshot.side_effect in {
            SideEffect.DESTRUCTIVE,
            SideEffect.PRIVILEGED,
        }
        if high_risk and self.status.phase in gated and self.spec.approval_ref is None:
            raise ValueError("high-risk ToolCall requires Approval before scheduling or execution")
        if (
            self.status.phase == ToolCallPhase.DENIED
            and self.spec.permission_decision.decision != PermissionDecisionValue.DENY
        ):
            raise ValueError("denied ToolCall requires deny permission decision")
        return self


class ApprovalResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Approval"] = "Approval"
    metadata: RuntimeMetadata
    spec: ApprovalSpec
    status: ApprovalStatus

    @model_validator(mode="after")
    def invariants(self) -> ApprovalResource:
        _validate_resource_identity(self.kind, self.metadata)
        approvals = [entry for entry in self.spec.decisions if entry.decision == "approve"]
        rejections = [entry for entry in self.spec.decisions if entry.decision == "reject"]
        required_count = sum(rule.count for rule in self.spec.required_approvers)
        if (
            self.status.phase in {ApprovalPhase.APPROVED, ApprovalPhase.CONSUMED}
            and len(approvals) < required_count
        ):
            raise ValueError("approved or consumed status requires all approvers")
        if self.status.phase == ApprovalPhase.REJECTED and not rejections:
            raise ValueError("rejected status requires a reject decision")
        if self.status.phase == ApprovalPhase.CONSUMED and (
            not self.spec.one_time or self.spec.usage_count != 1
        ):
            raise ValueError("consumed status requires one-time approval used exactly once")
        return self


class ArtifactResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Artifact"] = "Artifact"
    metadata: RuntimeMetadata
    spec: ArtifactSpec
    status: ArtifactStatus

    @model_validator(mode="after")
    def invariants(self) -> ArtifactResource:
        _validate_resource_identity(self.kind, self.metadata)
        if self.status.phase == ArtifactPhase.AVAILABLE and (
            self.spec.content_digest is None or self.spec.size_bytes is None
        ):
            raise ValueError("available artifact requires digest and size")
        return self


class EventResource(StrictModel):
    api_version: Literal[API_VERSION] = API_VERSION
    kind: Literal["Event"] = "Event"
    metadata: RuntimeMetadata
    spec: EventSpec
    status: EventStatus

    @model_validator(mode="after")
    def invariants(self) -> EventResource:
        _validate_resource_identity(self.kind, self.metadata)
        if self.spec.id != self.metadata.id:
            raise ValueError("CloudEvents id must equal metadata.id")
        return self


class CommonTypesCatalog(StrictModel):
    """Schema catalog used only to publish shared JSON Schema definitions."""

    scope: Scope
    actor_ref: ActorRef
    resource_ref: ResourceRef
    object_ref: ObjectRef
    schema_ref: SchemaRef
    artifact_ref: ArtifactRef
    secret_ref: SecretRef
    trace_context: TraceContext
    price_snapshot_ref: PriceSnapshotRef
    budget: Budget
    usage: Usage
    context_package: ContextPackage


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
    "common-types": CommonTypesCatalog,
    "standard-error": StandardError,
}
