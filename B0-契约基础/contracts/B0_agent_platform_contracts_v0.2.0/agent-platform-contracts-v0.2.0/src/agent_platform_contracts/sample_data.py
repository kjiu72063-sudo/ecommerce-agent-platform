"""Deterministic valid and invalid examples for B0 conformance tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


NOW = "2026-08-28T00:00:00Z"
LATER = "2026-08-28T01:00:00Z"
EXPIRES = "2026-08-29T00:00:00Z"
UUIDS = {
    "tenant": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f401",
    "user": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f402",
    "project": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f403",
    "agent": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411",
    "skill": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f412",
    "tool": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f413",
    "prompt": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f414",
    "model": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f415",
    "context": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
    "loop": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f417",
    "permission": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f418",
    "task": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421",
    "run": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f422",
    "checkpoint": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f423",
    "tool_call": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f424",
    "approval": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f425",
    "artifact": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f426",
    "artifact_2": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f427",
    "event": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f428",
    "event_2": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f429",
    "event_3": "0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f42a",
}

TENANT_ID = f"ten_{UUIDS['tenant']}"
USER_ID = f"usr_{UUIDS['user']}"
PROJECT_ID = f"prj_{UUIDS['project']}"
IDS = {
    "AgentSpec": f"agt_{UUIDS['agent']}",
    "SkillManifest": f"skl_{UUIDS['skill']}",
    "ToolManifest": f"tol_{UUIDS['tool']}",
    "PromptPackage": f"prm_{UUIDS['prompt']}",
    "ModelPolicy": f"mpo_{UUIDS['model']}",
    "ContextPolicy": f"cpo_{UUIDS['context']}",
    "LoopProfile": f"lop_{UUIDS['loop']}",
    "PermissionProfile": f"pep_{UUIDS['permission']}",
    "Task": f"tsk_{UUIDS['task']}",
    "AgentRun": f"run_{UUIDS['run']}",
    "Checkpoint": f"ckp_{UUIDS['checkpoint']}",
    "ToolCall": f"tcl_{UUIDS['tool_call']}",
    "Approval": f"apr_{UUIDS['approval']}",
    "Artifact": f"art_{UUIDS['artifact']}",
    "Event": f"evt_{UUIDS['event']}",
}
ARTIFACT_2 = f"art_{UUIDS['artifact_2']}"
EVENT_2 = f"evt_{UUIDS['event_2']}"
EVENT_3 = f"evt_{UUIDS['event_3']}"

DIGESTS = {name: f"sha256:{index:064x}" for index, name in enumerate(IDS, start=1)}
SCHEMA_DIGEST = f"sha256:{200:064x}"
PRICE_DIGEST = f"sha256:{201:064x}"


def actor(actor_type: str = "user") -> dict[str, Any]:
    if actor_type == "user":
        actor_id = USER_ID
    elif actor_type == "agent":
        actor_id = IDS["AgentSpec"]
    elif actor_type == "service":
        actor_id = "svc_agent-runtime"
    else:
        actor_id = "system"
    return {"actor_type": actor_type, "actor_id": actor_id, "tenant_id": TENANT_ID}


def scope() -> dict[str, Any]:
    return {"type": "project", "tenant_id": TENANT_ID, "user_id": USER_ID, "project_id": PROJECT_ID}


def definition_metadata(kind: str, key: str) -> dict[str, Any]:
    return {
        "id": IDS[kind],
        "key": key,
        "namespace": "personal",
        "version": "1.0.0",
        "revision": 1,
        "scope": scope(),
        "labels": {"domain": "development"},
        "annotations": {},
        "content_digest": DIGESTS[kind],
        "created_at": NOW,
        "created_by": actor(),
    }


def runtime_metadata(kind: str) -> dict[str, Any]:
    return {
        "id": IDS[kind],
        "revision": 1,
        "scope": scope(),
        "labels": {"domain": "development"},
        "annotations": {},
        "created_at": NOW,
        "created_by": actor(),
        "updated_at": LATER,
    }


def definition_status() -> dict[str, Any]:
    return {"phase": "active", "observed_revision": 1, "activated_at": LATER}


def ref(kind: str) -> dict[str, Any]:
    return {"kind": kind, "id": IDS[kind], "version": "1.0.0", "digest": DIGESTS[kind]}


def obj_ref(kind: str) -> dict[str, Any]:
    return {"kind": kind, "id": IDS[kind]}


def event_ref(event_id: str = IDS["Event"]) -> dict[str, Any]:
    return {"kind": "Event", "id": event_id}


def schema_ref(name: str) -> dict[str, Any]:
    return {"id": f"sch_{name}", "version": "1.0.0", "digest": SCHEMA_DIGEST}


def artifact_ref(second: bool = False) -> dict[str, Any]:
    return {
        "kind": "Artifact",
        "id": ARTIFACT_2 if second else IDS["Artifact"],
        "digest": f"sha256:{202 if second else 14:064x}",
    }


def price_snapshot() -> dict[str, Any]:
    return {"snapshot_id": "price_2026-08-28", "version": "1.0.0", "effective_at": NOW, "digest": PRICE_DIGEST}


def initial_model_selection() -> dict[str, Any]:
    return {
        "sequence": 1,
        "route_id": "primary-model",
        "provider": "openai",
        "model": "gpt-frontier",
        "selected_at": NOW,
        "selection_reason": "initial",
        "price_snapshot_ref": price_snapshot(),
        "event_ref": event_ref(EVENT_3),
    }


def budget() -> dict[str, Any]:
    return {
        "max_wall_time_seconds": 3600,
        "max_model_input_tokens": 300000,
        "max_model_output_tokens": 100000,
        "max_model_tokens": 400000,
        "max_cost_usd": "20.00",
        "max_tool_calls": 100,
        "max_iterations": 20,
    }


def usage() -> dict[str, Any]:
    return {
        "wall_time_seconds": 15.5,
        "model_input_tokens": 1200,
        "model_output_tokens": 300,
        "model_tokens": 1500,
        "cost_usd": "0.25",
        "tool_calls": 1,
        "iterations": 1,
        "price_snapshot_ref": price_snapshot(),
    }


def base(kind: str, spec: dict[str, Any], status: dict[str, Any], definition: bool) -> dict[str, Any]:
    key_map = {
        "AgentSpec": "programming-agent",
        "SkillManifest": "repository-inspection",
        "ToolManifest": "repository-read",
        "PromptPackage": "programming-base",
        "ModelPolicy": "programming-models",
        "ContextPolicy": "programming-context",
        "LoopProfile": "bounded-repair",
        "PermissionProfile": "development-safe",
    }
    metadata = definition_metadata(kind, key_map[kind]) if definition else runtime_metadata(kind)
    return {"api_version": "agent-platform/v1alpha1", "kind": kind, "metadata": metadata, "spec": spec, "status": status}


def valid_examples() -> dict[str, dict[str, Any]]:
    agent_spec = base(
        "AgentSpec",
        {
            "purpose": "在受控代码仓库中完成可验证的编程任务",
            "domain": "development",
            "goals": ["分析代码库并完成任务", "运行测试并提供可验证结果"],
            "non_goals": ["未经审批部署生产环境", "访问任务范围外的仓库"],
            "input_schema_ref": schema_ref("programming-task"),
            "output_schema_ref": schema_ref("programming-result"),
            "prompt_package_ref": ref("PromptPackage"),
            "context_policy_ref": ref("ContextPolicy"),
            "model_policy_ref": ref("ModelPolicy"),
            "loop_profile_ref": ref("LoopProfile"),
            "permission_profile_ref": ref("PermissionProfile"),
            "skill_bindings": [{"selector": {"domain": "development", "status": "active", "labels": {}}, "max_candidates": 8}],
            "tool_bindings": [{"selector": {"domain": "development", "status": "active", "labels": {}}, "max_candidates": 12}],
            "memory_policy": {
                "readable_scopes": ["project", "user"],
                "writable_scopes": ["project"],
                "write_requires_approval": True,
                "max_retention_days": 365,
                "allow_cross_user": False,
                "allow_cross_tenant": False,
            },
            "budget_defaults": budget(),
            "approval_defaults": {
                "external_send": True,
                "destructive": True,
                "privileged": True,
                "approval_ttl_seconds": 1800,
            },
            "concurrency_policy": {
                "max_parallel_tasks": 4,
                "max_parallel_runs_per_task": 1,
                "serialization_key_template": "project:{project_id}:repository:{repository_id}",
            },
            "eval_suite_refs": [artifact_ref(second=True)],
        },
        definition_status(),
        True,
    )

    skill = base(
        "SkillManifest",
        {
            "portable_name": "repository-inspection",
            "description": "Inspect an authorized repository and summarize its structure before planning changes.",
            "domain": ["development"],
            "tags": ["repository", "inspection"],
            "trigger_examples": {
                "positive": ["分析这个代码仓库的结构"],
                "negative": ["向客户发送项目完成邮件"],
            },
            "input_schema_ref": schema_ref("repository-inspection-input"),
            "output_schema_ref": schema_ref("repository-inspection-output"),
            "required_tools": [{"tool_ref": ref("ToolManifest"), "required_capabilities": ["repository.read"]}],
            "required_skills": [],
            "conflicts_with": [],
            "permission_requirements": [{"actions": ["repository.read"], "resources": ["project:current/repository:*"], "conditions": {"environment": "sandbox"}}],
            "risk_level": "low",
            "runtime_requirements": {
                "operating_systems": ["linux"],
                "binaries": ["git", "rg"],
                "network_domains": [],
                "has_scripts": True,
                "sandbox_required": True,
                "sandbox_profile": "restricted-development",
            },
            "context_budget": {"max_skill_tokens": 4000, "max_reference_tokens": 6000, "max_total_tokens": 10000},
            "bundle_artifact_ref": artifact_ref(),
            "source_repository": {
                "repository": "agent-platform-skills",
                "commit": "0123456789abcdef0123456789abcdef01234567",
                "path": "skills/repository-inspection",
            },
            "eval_summary": {
                "trigger_precision": 0.95,
                "trigger_recall": 0.92,
                "output_pass_rate": 0.98,
                "security_passed": True,
                "regression_passed": True,
                "evaluated_cases": 120,
                "evaluated_at": NOW,
            },
            "provenance": {"type": "human", "actor": actor(), "source_ref": "review:skill-001"},
        },
        definition_status(),
        True,
    )

    tool = base(
        "ToolManifest",
        {
            "provider": "git-service",
            "capability": "repository.read",
            "domain": ["development"],
            "transport": "mcp",
            "endpoint_ref": {"service_id": "repository-gateway", "endpoint_key": "tools/repository.read"},
            "input_schema_ref": schema_ref("repository-read-input"),
            "output_schema_ref": schema_ref("repository-read-output"),
            "auth_profile_ref": {"provider": "vault", "key": "tenants/default/repository", "version": 1, "field": "access_token"},
            "side_effect": "read_only",
            "risk_level": "low",
            "idempotency": {"supported": False, "key_scope": "none", "duplicate_semantics": "not_applicable"},
            "timeout_policy": {"connect_timeout_seconds": 5, "execution_timeout_seconds": 60},
            "retry_policy": {
                "max_attempts": 3,
                "retryable_error_codes": ["TOOL_TIMEOUT", "DEPENDENCY_UNAVAILABLE"],
                "backoff": "exponential",
                "base_delay_seconds": 0.5,
                "requires_safe_to_retry": True,
            },
            "rate_limit": {"requests": 60, "per_seconds": 60},
            "execution_location": "sandbox",
            "sandbox_profile": "restricted-development",
            "approval_requirement": {"mode": "none", "conditions": []},
            "health_contract": {"healthcheck_key": "repository-gateway/health", "interval_seconds": 30, "unhealthy_after_failures": 3},
        },
        definition_status(),
        True,
    )

    prompt = base(
        "PromptPackage",
        {
            "fragments": [
                {"name": "global-safety", "layer": "safety", "order": 0, "content": "Respect permissions, approvals, and task scope."},
                {"name": "programming-identity", "layer": "identity", "order": 10, "content": "You are a bounded programming agent."},
                {"name": "structured-output", "layer": "output_contract", "order": 20, "content": "Return an object matching the declared output schema."},
            ],
            "variables_schema_ref": schema_ref("prompt-variables"),
            "model_compatibility": {"required_capabilities": ["tool_calling", "structured_output"], "provider_allowlist": ["openai"]},
            "output_schema_ref": schema_ref("programming-result"),
            "max_static_tokens": 8000,
            "eval_suite_refs": [artifact_ref(second=True)],
            "change_summary": "Initial approved programming prompt package.",
        },
        definition_status(),
        True,
    )

    model = base(
        "ModelPolicy",
        {
            "routes": [
                {"route_id": "primary-model", "provider": "openai", "model": "gpt-frontier", "priority": 100, "required_capabilities": ["tool_calling", "structured_output"], "conditions": {"risk": ["low", "medium"]}},
                {"route_id": "fallback-model", "provider": "openai", "model": "gpt-balanced", "priority": 50, "required_capabilities": ["tool_calling", "structured_output"], "conditions": {}},
            ],
            "required_capabilities": ["tool_calling", "structured_output"],
            "provider_allowlist": ["openai"],
            "data_classification_rules": [
                {"classification": "public", "allowed_providers": ["openai"], "require_local": False},
                {"classification": "restricted", "allowed_providers": [], "require_local": True},
            ],
            "fallback_chain": [{"route_id": "fallback-model", "on_error_codes": ["MODEL_UNAVAILABLE", "RATE_LIMITED"]}],
            "budget_limits": budget(),
            "quality_floor": "high",
            "region_constraints": ["JP"],
            "local_model_rules": {"required_for": ["restricted"]},
            "circuit_breaker": {"failure_threshold": 5, "window_seconds": 60, "open_seconds": 120},
        },
        definition_status(),
        True,
    )

    context = base(
        "ContextPolicy",
        {
            "source_rules": [
                {"source": "task", "effect": "allow", "priority": 100, "filters": {}},
                {"source": "memory", "effect": "allow", "priority": 60, "filters": {"scope": ["project", "user"]}},
                {"source": "knowledge", "effect": "allow", "priority": 70, "filters": {"require_provenance": True}},
            ],
            "token_budget": {"total_tokens": 50000, "reserved_output_tokens": 10000, "per_source": {"task": 5000, "prompt": 8000, "skill": 10000, "knowledge": 12000, "tool_schema": 5000}},
            "skill_selection": {"top_k": 8, "similarity_threshold": 0.72, "metadata_token_limit": 2000},
            "tool_selection": {"max_visible_tools": 24, "schema_token_limit": 8000},
            "memory_scope": {"allowed_scopes": ["project", "user"], "allow_cross_user": False, "allow_cross_tenant": False},
            "freshness": {"default_ttl_seconds": 3600, "source_ttl_seconds": {"tool_result": 300, "knowledge": 86400}},
            "deduplication": {"strategy": "hybrid", "similarity_threshold": 0.92},
            "compaction": {"strategy": "hybrid", "target_ratio": 0.6, "preserve_provenance": True},
            "redaction": {"redact_secrets": True, "pii_mode": "mask", "restricted_data_mode": "local_only"},
            "provenance_requirement": True,
            "snapshot_policy": {"persist": True, "store_content": False, "retention_days": 30, "require_digest": True},
        },
        definition_status(),
        True,
    )

    loop = base(
        "LoopProfile",
        {
            "strategy": "repair",
            "max_iterations": 20,
            "max_wall_time_seconds": 3600,
            "max_model_tokens": 400000,
            "max_cost_usd": "20.00",
            "stop_conditions": [
                {"condition_type": "success", "expression": "all_required_tests_pass"},
                {"condition_type": "budget", "expression": "hard_budget_reached"},
            ],
            "evaluator_refs": [ref("ToolManifest")],
            "checkpoint_policy": {"interval_iterations": 2, "on_tool_side_effect": True, "on_human_interrupt": True, "on_node_end": True},
            "retry_policy": {"max_model_retries": 2, "max_node_retries": 1, "backoff": "exponential"},
            "human_interrupts": [{"stage": "external_side_effect", "reason": "External writes need approval", "required": True}],
            "progress_policy": {"emit_every_iterations": 1, "persist_summary": True},
            "rollback_policy": {"strategy": "manual", "compensation_tool_refs": []},
        },
        definition_status(),
        True,
    )

    permission = base(
        "PermissionProfile",
        {
            "roles": ["developer"],
            "rules": [
                {"effect": "allow", "actions": ["repository.read"], "resources": ["project:current/repository:*"], "conditions": {"environment": ["development", "sandbox"]}},
                {"effect": "require_approval", "actions": ["repository.write"], "resources": ["project:current/repository:*"], "conditions": {}},
                {"effect": "deny", "actions": ["secret.read_raw"], "resources": ["*"], "conditions": {}},
            ],
            "capabilities": ["repository.read", "repository.write"],
            "default_decision": "deny",
            "deny_precedence": True,
            "cross_tenant_default": "deny",
        },
        definition_status(),
        True,
    )

    task = base(
        "Task",
        {
            "title": "检查并说明仓库结构",
            "intent": "development.inspect_repository",
            "domain": "development",
            "requested_by": actor(),
            "source": {"type": "openclaw", "channel": "feishu", "source_message_id": "message-12345"},
            "payload": {"repository_ref": "repo_demo", "requested_depth": 3},
            "input_schema_ref": schema_ref("programming-task"),
            "expected_output_schema_ref": schema_ref("programming-result"),
            "input_artifact_refs": [],
            "requested_agent_ref": ref("AgentSpec"),
            "routing_constraints": {"allowed_agent_refs": [ref("AgentSpec")], "allowed_domains": ["development"], "required_model_capabilities": ["tool_calling"]},
            "priority": 50,
            "schedule": {"mode": "immediate"},
            "dependencies": [],
            "budget": budget(),
            "permission_grant": {"actions": ["repository.read"], "resources": ["project:current/repository:*"], "expires_at": EXPIRES},
            "approval_policy_ref": ref("PermissionProfile"),
            "idempotency_key": "openclaw:feishu:message-12345",
            "deadline_at": EXPIRES,
            "retention_policy": {"retain_days": 90, "legal_hold": False},
        },
        {"phase": "queued"},
        False,
    )

    run = base(
        "AgentRun",
        {
            "task_ref": obj_ref("Task"),
            "attempt": 1,
            "agent_snapshot": ref("AgentSpec"),
            "resolved_dependencies": {
                "prompt_package_ref": ref("PromptPackage"),
                "context_policy_ref": ref("ContextPolicy"),
                "model_policy_ref": ref("ModelPolicy"),
                "loop_profile_ref": ref("LoopProfile"),
                "permission_profile_ref": ref("PermissionProfile"),
                "startup_skill_refs": [],
                "startup_tool_refs": [],
                "price_snapshot_ref": price_snapshot(),
                "schema_version": "1.0.0",
                "runtime_version": "python-runtime-1.0.0",
            },
            "dynamic_dependency_activations": [
                {
                    "sequence": 1,
                    "resource_ref": ref("SkillManifest"),
                    "activated_at": "2026-08-28T00:00:20Z",
                    "activation_reason": "Selected from the permission-filtered Skill catalog for repository inspection.",
                    "permission_decision_digest": f"sha256:{220:064x}",
                    "event_ref": event_ref(),
                    "checkpoint_ref": obj_ref("Checkpoint"),
                },
                {
                    "sequence": 2,
                    "resource_ref": ref("ToolManifest"),
                    "activated_at": "2026-08-28T00:00:30Z",
                    "activation_reason": "First Tool use required by the activated Skill.",
                    "source_skill_ref": ref("SkillManifest"),
                    "permission_decision_digest": f"sha256:{221:064x}",
                    "event_ref": event_ref(EVENT_2),
                    "checkpoint_ref": obj_ref("Checkpoint"),
                },
            ],
            "current_model_selection": initial_model_selection(),
            "model_selection_history": [initial_model_selection()],
            "worker_ref": {"worker_id": "wrk_runtime-01", "service": "agent-runtime", "instance": "instance-a"},
            "thread_ref": "thr_project-001",
            "budget": budget(),
            "usage": usage(),
            "context_snapshot_refs": [artifact_ref(second=True)],
            "output_artifact_refs": [],
            "lease": {
                "lease_id": "lease_run-001",
                "worker_ref": {"worker_id": "wrk_runtime-01", "service": "agent-runtime", "instance": "instance-a"},
                "acquired_at": NOW,
                "heartbeat_at": "2026-08-28T00:00:10Z",
                "expires_at": LATER,
                "fencing_token": 1,
            },
        },
        {"phase": "running"},
        False,
    )

    checkpoint = base(
        "Checkpoint",
        {
            "run_ref": obj_ref("AgentRun"),
            "sequence": 1,
            "graph_state": {"step": "inspect_repository", "completed": False},
            "node_state": {"current_node": "inspect", "next_node": "summarize"},
            "context_digest": f"sha256:{210:064x}",
            "side_effect_ledger": [],
            "pending_approvals": [],
            "pending_tool_calls": [obj_ref("ToolCall")],
            "resume_token_ref": {"provider": "vault", "key": "runtime/checkpoints/run-001", "version": 1, "field": "resume_token"},
            "created_reason": "node_end",
        },
        {"phase": "committed"},
        False,
    )

    tool_call = base(
        "ToolCall",
        {
            "run_ref": obj_ref("AgentRun"),
            "tool_snapshot": {"tool_ref": ref("ToolManifest"), "side_effect": "read_only", "risk_level": "low"},
            "requested_by": actor("agent"),
            "input": {"repository": "repo_demo", "path": "."},
            "input_digest": f"sha256:{211:064x}",
            "permission_decision": {
                "decision": "allow",
                "policy_refs": [ref("PermissionProfile")],
                "reason_codes": ["RESOURCE_IN_PROJECT_SCOPE"],
                "constraints": {"allowed_paths": ["**"]},
                "request_digest": f"sha256:{212:064x}",
                "decision_digest": f"sha256:{213:064x}",
            },
            "execution_target": "sandbox",
            "attempt": 1,
            "output": {"entries": ["src", "tests"]},
            "usage": {"wall_time_seconds": 0.25, "network_bytes": 0},
        },
        {"phase": "succeeded"},
        False,
    )

    approval = base(
        "Approval",
        {
            "subject_ref": obj_ref("ToolCall"),
            "requester": actor("agent"),
            "approval_type": "tool_execution",
            "risk_summary": "Write operation changes an authorized development repository.",
            "requested_actions": [{"action": "repository.write", "resource": "project:current/repository:repo_demo"}],
            "input_digest": f"sha256:{214:064x}",
            "policy_snapshot": ref("PermissionProfile"),
            "required_approvers": [{"role": "project-owner", "count": 1, "separation_of_duties": False}],
            "decisions": [{"approver": actor(), "decision": "approve", "decided_at": LATER, "comment": "Approved for development branch."}],
            "expires_at": EXPIRES,
            "one_time": True,
            "usage_count": 0,
        },
        {"phase": "approved"},
        False,
    )

    artifact = base(
        "Artifact",
        {
            "artifact_type": "document",
            "media_type": "text/markdown",
            "storage_provider": "object-storage",
            "locator": {"provider": "s3", "bucket_or_repository": "agent-artifacts", "object_key": "tenants/default/projects/demo/results/report.md", "version_id": "v1"},
            "content_digest": DIGESTS["Artifact"],
            "size_bytes": 4096,
            "encryption": {"encrypted": False},
            "classification": "internal",
            "provenance": {"task_ref": obj_ref("Task"), "run_ref": obj_ref("AgentRun"), "actor": actor("agent")},
            "schema_ref": schema_ref("programming-result"),
            "retention_policy": {"retain_days": 365, "legal_hold": False},
            "access_policy_ref": ref("PermissionProfile"),
        },
        {"phase": "available"},
        False,
    )

    event = base(
        "Event",
        {
            "specversion": "1.0",
            "id": IDS["Event"],
            "source": "/services/agent-runtime",
            "type": "agent_run.skill_activated",
            "subject": IDS["AgentRun"],
            "time": NOW,
            "datacontenttype": "application/json",
            "dataschema": "https://schemas.agent-platform.local/events/skill-activated/1.0.0",
            "subject_ref": obj_ref("AgentRun"),
            "sequence": 42,
            "trace": {"trace_id": "0123456789abcdef0123456789abcdef", "span_id": "0123456789abcdef", "correlation_id": "corr_task-001"},
            "schema_ref": schema_ref("event-skill-activated"),
            "data": {"skill_ref": ref("SkillManifest")},
        },
        {"phase": "recorded"},
        False,
    )

    return {
        "agent-spec": agent_spec,
        "skill-manifest": skill,
        "tool-manifest": tool,
        "prompt-package": prompt,
        "model-policy": model,
        "context-policy": context,
        "loop-profile": loop,
        "permission-profile": permission,
        "task": task,
        "agent-run": run,
        "checkpoint": checkpoint,
        "tool-call": tool_call,
        "approval": approval,
        "artifact": artifact,
        "event": event,
    }


def invalid_examples() -> dict[str, dict[str, Any]]:
    valid = valid_examples()
    invalid: dict[str, dict[str, Any]] = {}

    def add(name: str, target: str, error: str, mutate) -> None:
        payload = deepcopy(valid[target])
        mutate(payload)
        invalid[name] = {"target_model": target, "expected_error_code": error, "payload": payload}

    add("agent-spec-extra-field", "agent-spec", "EXTRA_FIELD_FORBIDDEN", lambda p: p.update({"undeclared": True}))
    add("skill-hermes-active", "skill-manifest", "HERMES_PROPOSAL_NOT_ACTIVATABLE", lambda p: p["spec"]["provenance"].update({"type": "hermes_proposal"}))

    def invalid_tool(p: dict[str, Any]) -> None:
        p["spec"]["side_effect"] = "external_write"
        p["spec"]["idempotency"] = {"supported": False, "key_scope": "none", "duplicate_semantics": "not_applicable"}
    add("tool-side-effect-without-idempotency", "tool-manifest", "IDEMPOTENCY_REQUIRED", invalid_tool)

    def invalid_prompt(p: dict[str, Any]) -> None:
        p["spec"]["fragments"][1]["order"] = p["spec"]["fragments"][0]["order"]
    add("prompt-duplicate-order", "prompt-package", "PROMPT_ORDER_DUPLICATE", invalid_prompt)

    def invalid_model(p: dict[str, Any]) -> None:
        p["spec"]["routes"][0]["provider"] = "unapproved-provider"
    add("model-provider-not-allowlisted", "model-policy", "MODEL_PROVIDER_NOT_ALLOWED", invalid_model)

    def invalid_context(p: dict[str, Any]) -> None:
        p["spec"]["token_budget"]["total_tokens"] = 10000
    add("context-budget-overflow", "context-policy", "CONTEXT_BUDGET_EXCEEDED", invalid_context)
    add("loop-zero-iterations", "loop-profile", "LOOP_HARD_LIMIT_REQUIRED", lambda p: p["spec"].update({"max_iterations": 0}))
    add("permission-default-allow", "permission-profile", "DEFAULT_DENY_REQUIRED", lambda p: p["spec"].update({"default_decision": "allow"}))
    add("task-missing-idempotency-key", "task", "TASK_IDEMPOTENCY_REQUIRED", lambda p: p["spec"].pop("idempotency_key"))
    add("run-latest-dependency", "agent-run", "EXACT_VERSION_REQUIRED", lambda p: p["spec"]["resolved_dependencies"]["prompt_package_ref"].update({"version": "latest"}))

    def invalid_dynamic_sequence(p: dict[str, Any]) -> None:
        p["spec"]["dynamic_dependency_activations"][1]["sequence"] = 3
    add("run-dynamic-activation-sequence-gap", "agent-run", "DYNAMIC_ACTIVATION_SEQUENCE_INVALID", invalid_dynamic_sequence)

    def invalid_dynamic_duplicate(p: dict[str, Any]) -> None:
        p["spec"]["dynamic_dependency_activations"][1]["resource_ref"] = deepcopy(
            p["spec"]["dynamic_dependency_activations"][0]["resource_ref"]
        )
    add("run-dynamic-activation-duplicate", "agent-run", "DYNAMIC_DEPENDENCY_DUPLICATE", invalid_dynamic_duplicate)

    def invalid_model_current(p: dict[str, Any]) -> None:
        p["spec"]["current_model_selection"]["model"] = "gpt-balanced"
    add("run-model-current-mismatch", "agent-run", "MODEL_SELECTION_CURRENT_MISMATCH", invalid_model_current)

    def invalid_model_fallback_trigger(p: dict[str, Any]) -> None:
        fallback = deepcopy(p["spec"]["model_selection_history"][0])
        fallback.update({
            "sequence": 2,
            "route_id": "fallback-model",
            "model": "gpt-balanced",
            "selected_at": LATER,
            "selection_reason": "fallback",
            "event_ref": event_ref(EVENT_2),
        })
        p["spec"]["model_selection_history"].append(fallback)
        p["spec"]["current_model_selection"] = deepcopy(fallback)
    add("run-model-fallback-missing-trigger", "agent-run", "MODEL_FALLBACK_TRIGGER_REQUIRED", invalid_model_fallback_trigger)
    add("checkpoint-zero-sequence", "checkpoint", "CHECKPOINT_SEQUENCE_INVALID", lambda p: p["spec"].update({"sequence": 0}))

    def invalid_tool_call(p: dict[str, Any]) -> None:
        p["spec"]["tool_snapshot"]["side_effect"] = "external_send"
        p["spec"].pop("idempotency_key", None)
    add("tool-call-side-effect-without-key", "tool-call", "TOOL_CALL_IDEMPOTENCY_REQUIRED", invalid_tool_call)

    add("approval-one-time-used-twice", "approval", "APPROVAL_ALREADY_CONSUMED", lambda p: p["spec"].update({"usage_count": 2}))
    add("artifact-signed-locator", "artifact", "ARTIFACT_LOCATOR_SECRET", lambda p: p["spec"]["locator"].update({"object_key": "report.md?X-Amz-Signature=secret"}))
    add("event-zero-sequence", "event", "EVENT_SEQUENCE_INVALID", lambda p: p["spec"].update({"sequence": 0}))
    return invalid
