"""Deterministic policy helpers required by the B0 conformance suite."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

NEW_RUN_RESOLVABLE_PHASES = frozenset({"active"})
RESUME_RUN_RESOLVABLE_PHASES = frozenset({"active", "deprecated"})
TERMINAL_RUN_PHASES = frozenset({"succeeded", "failed", "cancelled", "timed_out"})


def canonical_json(value: Any) -> bytes:
    """Return stable UTF-8 JSON bytes for hashing and signatures."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def combine_permission_decisions(decisions: Iterable[str]) -> str:
    """Apply deny-first intersection semantics to policy decisions."""
    normalized = tuple(decisions)
    if not normalized:
        return "deny"
    if any(decision == "deny" for decision in normalized):
        return "deny"
    if any(decision == "require_approval" for decision in normalized):
        return "require_approval"
    if all(decision == "allow" for decision in normalized):
        return "allow"
    raise ValueError("unknown permission decision")


def scoped_task_idempotency_key(tenant_id: str, source_type: str, key: str) -> str:
    return canonical_sha256(
        {"tenant_id": tenant_id, "source_type": source_type, "idempotency_key": key}
    )


def scoped_tool_idempotency_key(tool_id: str, target_resource: str, key: str) -> str:
    return canonical_sha256(
        {"tool_id": tool_id, "target_resource": target_resource, "idempotency_key": key}
    )


def can_auto_retry(
    *, retryable: bool, safe_to_retry: bool, tool_allows_retry: bool, state: str
) -> bool:
    return retryable and safe_to_retry and tool_allows_retry and state != "unknown"


def lease_allows_commit(
    *,
    fencing_token: int,
    current_fencing_token: int,
    expires_at: datetime,
    now: datetime | None = None,
) -> bool:
    observed_now = now or datetime.now(timezone.utc)
    return fencing_token == current_fencing_token and observed_now < expires_at


def definition_is_resolvable(*, definition_phase: str, purpose: str) -> bool:
    """Apply lifecycle rules for new resolution versus resume of a frozen Run."""
    if purpose == "new_run":
        return definition_phase in NEW_RUN_RESOLVABLE_PHASES
    if purpose == "resume_run":
        return definition_phase in RESUME_RUN_RESOLVABLE_PHASES
    raise ValueError("unknown resolution purpose")


def activation_history_is_append_only(previous: list[Any], current: list[Any]) -> bool:
    """Require persisted dynamic dependency history to retain its exact prior prefix."""
    return len(current) >= len(previous) and current[: len(previous)] == previous


def model_switch_boundary(
    *,
    run_phase: str,
    route_in_fallback_chain: bool,
    trigger_error_allowed: bool,
    frozen_dependencies_unchanged: bool,
    policy_constraints_satisfied: bool,
    budget_available: bool,
) -> str:
    """Classify a model switch as same-Run fallback or a new-Run restart."""
    same_run = (
        run_phase not in TERMINAL_RUN_PHASES
        and route_in_fallback_chain
        and trigger_error_allowed
        and frozen_dependencies_unchanged
        and policy_constraints_satisfied
        and budget_available
    )
    return "same_run_fallback" if same_run else "new_run_required"
