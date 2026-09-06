"""Deterministic policy helpers required by the B0 conformance suite.

实现权限、幂等、租约等策略函数。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable


# ============================================================
# 解析生命周期常量
# ============================================================

# 新 Run 可解析的状态
NEW_RUN_RESOLVABLE_PHASES = frozenset({"active"})

# 恢复 Run 可解析的状态（包括已冻结的 deprecated）
RESUME_RUN_RESOLVABLE_PHASES = frozenset({"active", "deprecated"})

# 终态
TERMINAL_RUN_PHASES = frozenset({"succeeded", "failed", "cancelled", "timed_out"})


# ============================================================
# 规范化 JSON 和摘要
# ============================================================

def canonical_json(value: Any) -> bytes:
    """
    返回稳定的 UTF-8 JSON 字节序列，用于哈希和签名。
    
    规则：
    - 排序键
    - 紧凑分隔符
    - 不允许 NaN
    - UTF-8 编码
    """
    return json.dumps(
        value, 
        ensure_ascii=False, 
        sort_keys=True, 
        separators=(",", ":"), 
        allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """
    计算规范化 JSON 的 SHA-256 摘要
    
    Args:
        value: 任意可 JSON 序列化的值
    
    Returns:
        str: "sha256:" + 十六进制摘要
    """
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


# ============================================================
# 权限决策
# ============================================================

def combine_permission_decisions(decisions: Iterable[str]) -> str:
    """
    应用 Deny 优先的交集语义合并权限决策。
    
    规则：
    - 任何一层 deny，最终结果就是 deny
    - 没有 deny 但有 require_approval，最终结果就是 require_approval
    - 全部 allow，最终结果才是 allow
    - 空列表返回 deny
    
    Args:
        decisions: 决策列表（allow/deny/require_approval）
    
    Returns:
        str: 最终决策
    """
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


# ============================================================
# 幂等键
# ============================================================

def scoped_task_idempotency_key(tenant_id: str, source_type: str, key: str) -> str:
    """
    生成作用域化的 Task 幂等键
    
    Args:
        tenant_id: 租户 ID
        source_type: 来源类型
        key: 原始幂等键
    
    Returns:
        str: SHA-256 摘要
    """
    return canonical_sha256({
        "tenant_id": tenant_id, 
        "source_type": source_type, 
        "idempotency_key": key
    })


def scoped_tool_idempotency_key(tool_id: str, target_resource: str, key: str) -> str:
    """
    生成作用域化的 Tool 幂等键
    
    Args:
        tool_id: 工具 ID
        target_resource: 目标资源
        key: 原始幂等键
    
    Returns:
        str: SHA-256 摘要
    """
    return canonical_sha256({
        "tool_id": tool_id, 
        "target_resource": target_resource, 
        "idempotency_key": key
    })


# ============================================================
# 自动重试
# ============================================================

def can_auto_retry(
    *, 
    retryable: bool, 
    safe_to_retry: bool, 
    tool_allows_retry: bool, 
    state: str
) -> bool:
    """
    检查是否可以自动重试
    
    条件：
    - retryable: 错误可重试
    - safe_to_retry: 重试安全（不会重复副作用）
    - tool_allows_retry: 工具允许重试
    - state != "unknown": 不是不确定状态
    
    Args:
        retryable: 是否可重试
        safe_to_retry: 重试是否安全
        tool_allows_retry: 工具是否允许重试
        state: 当前状态
    
    Returns:
        bool: 是否可以自动重试
    """
    return retryable and safe_to_retry and tool_allows_retry and state != "unknown"


# ============================================================
# 租约
# ============================================================

def lease_allows_commit(
    *, 
    fencing_token: int, 
    current_fencing_token: int, 
    expires_at: datetime, 
    now: datetime | None = None
) -> bool:
    """
    检查租约是否允许提交
    
    条件：
    - fencing_token 匹配当前令牌
    - 当前时间未过期
    
    Args:
        fencing_token: 提交时的令牌
        current_fencing_token: 当前有效令牌
        expires_at: 租约过期时间
        now: 当前时间（可选，默认使用 UTC 现在）
    
    Returns:
        bool: 是否允许提交
    """
    observed_now = now or datetime.now(timezone.utc)
    return fencing_token == current_fencing_token and observed_now < expires_at


# ============================================================
# 定义对象解析
# ============================================================

def definition_is_resolvable(*, definition_phase: str, purpose: str) -> bool:
    """
    应用定义对象生命周期解析规则
    
    新 Run：只能解析 active 状态
    恢复 Run：可以解析 active 和 deprecated 状态
    
    Args:
        definition_phase: 定义对象当前状态
        purpose: 解析目的（new_run/resume_run）
    
    Returns:
        bool: 是否可解析
    """
    if purpose == "new_run":
        return definition_phase in NEW_RUN_RESOLVABLE_PHASES
    if purpose == "resume_run":
        return definition_phase in RESUME_RUN_RESOLVABLE_PHASES
    raise ValueError("unknown resolution purpose")


# ============================================================
# 动态依赖激活历史
# ============================================================

def activation_history_is_append_only(previous: list[Any], current: list[Any]) -> bool:
    """
    检查动态依赖激活历史是否只追加
    
    规则：
    - 当前列表长度 >= 历史列表长度
    - 当前列表的前缀必须完全匹配历史列表
    
    Args:
        previous: 历史记录
        current: 当前记录
    
    Returns:
        bool: 是否只追加
    """
    return len(current) >= len(previous) and current[: len(previous)] == previous


# ============================================================
# 模型切换边界
# ============================================================

def model_switch_boundary(
    *,
    run_phase: str,
    route_in_fallback_chain: bool,
    trigger_error_allowed: bool,
    frozen_dependencies_unchanged: bool,
    policy_constraints_satisfied: bool,
    budget_available: bool,
) -> str:
    """
    分类模型切换：同一 Run 内的 Fallback 还是需要新 Run
    
    同一 Run 的条件：
    - Run 不在终态
    - 目标路由在回退链中
    - 触发错误允许回退
    - 冻结依赖未变
    - 策略约束满足
    - 预算可用
    
    Args:
        run_phase: 当前 Run 状态
        route_in_fallback_chain: 目标路由是否在回退链中
        trigger_error_allowed: 触发错误是否允许回退
        frozen_dependencies_unchanged: 冻结依赖是否未变
        policy_constraints_satisfied: 策略约束是否满足
        budget_available: 预算是否可用
    
    Returns:
        str: "same_run_fallback" 或 "new_run_required"
    """
    same_run = (
        run_phase not in TERMINAL_RUN_PHASES
        and route_in_fallback_chain
        and trigger_error_allowed
        and frozen_dependencies_unchanged
        and policy_constraints_satisfied
        and budget_available
    )
    return "same_run_fallback" if same_run else "new_run_required"


print("policies.py 创建完成！")
print("已定义：canonical_sha256, combine_permission_decisions, can_auto_retry, lease_allows_commit 等策略函数")
