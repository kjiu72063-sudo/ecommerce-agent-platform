"""Authoritative B0 state-transition tables."""

from __future__ import annotations

from dataclasses import dataclass


class StateTransitionError(ValueError):
    code = "STATE_TRANSITION_NOT_ALLOWED"


STATE_MACHINES: dict[str, dict[str, tuple[str, ...]]] = {
    "definition": {
        "proposed": ("draft",),
        "draft": ("testing",),
        "testing": ("awaiting_approval", "draft"),
        "awaiting_approval": ("approved", "draft"),
        "approved": ("active",),
        "active": ("deprecated", "blocked"),
        "deprecated": ("archived",),
        "blocked": ("active",),
        "archived": (),
    },
    "task": {
        "created": ("validated", "cancelled", "expired"),
        "validated": ("queued", "failed", "cancelled", "expired"),
        "queued": ("running", "suspended", "cancelled", "expired"),
        "running": (
            "waiting_input",
            "waiting_approval",
            "suspended",
            "succeeded",
            "failed",
            "cancelled",
            "expired",
        ),
        "waiting_input": ("queued", "running", "cancelled", "expired"),
        "waiting_approval": ("queued", "running", "failed", "cancelled", "expired"),
        "suspended": ("queued", "cancelled", "expired"),
        "succeeded": (),
        "failed": (),
        "cancelled": (),
        "expired": (),
    },
    "agent-run": {
        "created": ("resolving", "cancelled"),
        "resolving": ("ready", "failed", "cancelled", "timed_out"),
        "ready": ("running", "cancelled", "timed_out"),
        "running": (
            "waiting_tool",
            "waiting_approval",
            "waiting_input",
            "checkpointed",
            "suspended",
            "succeeded",
            "failed",
            "cancelled",
            "timed_out",
        ),
        "waiting_tool": ("running", "checkpointed", "failed", "cancelled", "timed_out"),
        "waiting_approval": ("running", "checkpointed", "failed", "cancelled", "timed_out"),
        "waiting_input": ("running", "checkpointed", "failed", "cancelled", "timed_out"),
        "checkpointed": ("running", "suspended", "succeeded", "failed", "cancelled", "timed_out"),
        "suspended": ("ready", "running", "cancelled", "timed_out"),
        "succeeded": (),
        "failed": (),
        "cancelled": (),
        "timed_out": (),
    },
    "tool-call": {
        "proposed": ("validating", "cancelled"),
        "validating": ("denied", "waiting_approval", "scheduled", "failed", "cancelled"),
        "denied": (),
        "waiting_approval": ("approved", "rejected", "expired", "cancelled"),
        "approved": ("scheduled", "expired", "cancelled"),
        "rejected": (),
        "expired": (),
        "scheduled": ("executing", "cancelled"),
        "executing": ("succeeded", "failed", "cancelled", "unknown"),
        "succeeded": (),
        "failed": (),
        "cancelled": (),
        "unknown": (),
    },
    "approval": {
        "requested": ("pending", "expired", "revoked"),
        "pending": ("approved", "rejected", "expired", "revoked"),
        "approved": ("consumed", "expired", "revoked"),
        "rejected": (),
        "expired": (),
        "revoked": (),
        "consumed": (),
    },
    "artifact": {
        "pending_upload": ("available", "quarantined", "blocked", "deleted"),
        "available": ("quarantined", "blocked", "archived", "deleted"),
        "quarantined": ("available", "blocked", "archived", "deleted"),
        "blocked": ("archived", "deleted"),
        "archived": ("deleted",),
        "deleted": (),
    },
}


TERMINAL_STATES: dict[str, frozenset[str]] = {
    name: frozenset(state for state, targets in transitions.items() if not targets)
    for name, transitions in STATE_MACHINES.items()
}


@dataclass(frozen=True)
class TransitionResult:
    machine: str
    previous: str
    current: str
    event_required: bool = True


def transition(machine: str, current: str, target: str) -> TransitionResult:
    if machine not in STATE_MACHINES:
        raise StateTransitionError(f"unknown state machine: {machine}")
    transitions = STATE_MACHINES[machine]
    if current not in transitions:
        raise StateTransitionError(f"unknown state {current!r} for {machine}")
    if target not in transitions[current]:
        raise StateTransitionError(f"{machine} transition {current!r} -> {target!r} is not allowed")
    return TransitionResult(machine=machine, previous=current, current=target)
