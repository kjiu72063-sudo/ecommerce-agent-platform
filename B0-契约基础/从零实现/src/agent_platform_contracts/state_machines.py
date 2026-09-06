"""Authoritative B0 state-transition tables.

定义 6 个状态机的合法迁移规则。
"""

from __future__ import annotations

from dataclasses import dataclass


class StateTransitionError(ValueError):
    """状态迁移错误"""
    code = "STATE_TRANSITION_NOT_ALLOWED"


# ============================================================
# 状态机定义
# ============================================================

STATE_MACHINES: dict[str, dict[str, tuple[str, ...]]] = {
    # 定义对象状态机（适用于 AgentSpec, SkillManifest 等）
    "definition": {
        "proposed": ("draft",),
        "draft": ("testing",),
        "testing": ("awaiting_approval", "draft"),
        "awaiting_approval": ("approved", "draft"),
        "approved": ("active",),
        "active": ("deprecated", "blocked"),
        "deprecated": ("archived",),
        "blocked": ("active",),
        "archived": (),  # 终态
    },
    
    # Task 状态机
    "task": {
        "created": ("validated", "cancelled", "expired"),
        "validated": ("queued", "failed", "cancelled", "expired"),
        "queued": ("running", "suspended", "cancelled", "expired"),
        "running": ("waiting_input", "waiting_approval", "suspended", "succeeded", "failed", "cancelled", "expired"),
        "waiting_input": ("queued", "running", "cancelled", "expired"),
        "waiting_approval": ("queued", "running", "failed", "cancelled", "expired"),
        "suspended": ("queued", "cancelled", "expired"),
        "succeeded": (),  # 终态
        "failed": (),     # 终态
        "cancelled": (),  # 终态
        "expired": (),    # 终态
    },
    
    # AgentRun 状态机
    "agent-run": {
        "created": ("resolving", "cancelled"),
        "resolving": ("ready", "failed", "cancelled", "timed_out"),
        "ready": ("running", "cancelled", "timed_out"),
        "running": ("waiting_tool", "waiting_approval", "waiting_input", "checkpointed", "suspended", "succeeded", "failed", "cancelled", "timed_out"),
        "waiting_tool": ("running", "checkpointed", "failed", "cancelled", "timed_out"),
        "waiting_approval": ("running", "checkpointed", "failed", "cancelled", "timed_out"),
        "waiting_input": ("running", "checkpointed", "failed", "cancelled", "timed_out"),
        "checkpointed": ("running", "suspended", "succeeded", "failed", "cancelled", "timed_out"),
        "suspended": ("ready", "running", "cancelled", "timed_out"),
        "succeeded": (),  # 终态
        "failed": (),     # 终态
        "cancelled": (),  # 终态
        "timed_out": (),  # 终态
    },
    
    # ToolCall 状态机
    "tool-call": {
        "proposed": ("validating", "cancelled"),
        "validating": ("denied", "waiting_approval", "scheduled", "failed", "cancelled"),
        "denied": (),  # 终态
        "waiting_approval": ("approved", "rejected", "expired", "cancelled"),
        "approved": ("scheduled", "expired", "cancelled"),
        "rejected": (),  # 终态
        "expired": (),   # 终态
        "scheduled": ("executing", "cancelled"),
        "executing": ("succeeded", "failed", "cancelled", "unknown"),
        "succeeded": (),  # 终态
        "failed": (),     # 终态
        "cancelled": (),  # 终态
        "unknown": (),    # 终态（不确定状态）
    },
    
    # Approval 状态机
    "approval": {
        "requested": ("pending", "expired", "revoked"),
        "pending": ("approved", "rejected", "expired", "revoked"),
        "approved": ("consumed", "expired", "revoked"),
        "rejected": (),  # 终态
        "expired": (),   # 终态
        "revoked": (),   # 终态
        "consumed": (),  # 终态
    },
    
    # Artifact 状态机
    "artifact": {
        "pending_upload": ("available", "quarantined", "blocked", "deleted"),
        "available": ("quarantined", "blocked", "archived", "deleted"),
        "quarantined": ("available", "blocked", "archived", "deleted"),
        "blocked": ("archived", "deleted"),
        "archived": ("deleted",),
        "deleted": (),  # 终态
    },
}


# ============================================================
# 终态集合
# ============================================================

TERMINAL_STATES: dict[str, frozenset[str]] = {
    name: frozenset(state for state, targets in transitions.items() if not targets)
    for name, transitions in STATE_MACHINES.items()
}


# ============================================================
# 状态迁移结果
# ============================================================

@dataclass(frozen=True)
class TransitionResult:
    """状态迁移结果"""
    machine: str
    previous: str
    current: str
    event_required: bool = True


# ============================================================
# 状态迁移函数
# ============================================================

def transition(machine: str, current: str, target: str) -> TransitionResult:
    """
    执行状态迁移
    
    Args:
        machine: 状态机名称（如 "task", "agent-run"）
        current: 当前状态
        target: 目标状态
    
    Returns:
        TransitionResult: 迁移结果
    
    Raises:
        StateTransitionError: 如果迁移不合法
    """
    if machine not in STATE_MACHINES:
        raise StateTransitionError(f"unknown state machine: {machine}")
    
    transitions = STATE_MACHINES[machine]
    
    if current not in transitions:
        raise StateTransitionError(f"unknown state {current!r} for {machine}")
    
    if target not in transitions[current]:
        raise StateTransitionError(f"{machine} transition {current!r} -> {target!r} is not allowed")
    
    return TransitionResult(machine=machine, previous=current, current=target)


def is_terminal(machine: str, state: str) -> bool:
    """
    检查状态是否为终态
    
    Args:
        machine: 状态机名称
        state: 状态名称
    
    Returns:
        bool: 是否为终态
    """
    if machine not in TERMINAL_STATES:
        raise StateTransitionError(f"unknown state machine: {machine}")
    return state in TERMINAL_STATES[machine]


def get_allowed_transitions(machine: str, current: str) -> tuple[str, ...]:
    """
    获取允许的状态迁移
    
    Args:
        machine: 状态机名称
        current: 当前状态
    
    Returns:
        tuple: 允许的目标状态列表
    """
    if machine not in STATE_MACHINES:
        raise StateTransitionError(f"unknown state machine: {machine}")
    
    transitions = STATE_MACHINES[machine]
    
    if current not in transitions:
        raise StateTransitionError(f"unknown state {current!r} for {machine}")
    
    return transitions[current]


print("state_machines.py 创建完成！")
print(f"已定义 {len(STATE_MACHINES)} 个状态机")
