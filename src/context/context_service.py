"""B3 Context 引擎最小闭环

按 authoritative B0 的 ContextPackage 组装确定性来源上下文：
来源列表 → 去重 → 优先级排序 → Token 预算分配 → 校验输出。
RAG、Memory、多模态素材等来源留待后续适配器。
"""

from __future__ import annotations

from agent_platform_contracts.models import ContextPackage
from agent_platform_contracts.policies import canonical_sha256


class TokenBudgetExceeded(Exception):
    """上下文 token 总量或单来源超预算。"""


def estimate_tokens(text: str) -> int:
    """确定性 token 估算：约 3 字符一个 token。"""
    return max(1, len(text) // 3)


class ContextService:
    """Context 组装服务。

    输入一个显式 source descriptor，包含契约要求的 run/policy/artifact 引用
    和来源内容；输出通过 B0 校验的 ContextPackage。
    """

    def __init__(self, policy: dict):
        self.policy = policy

    def build(self, descriptor: dict) -> dict:
        sources = descriptor["sources"]
        budget = self.policy["spec"]["token_budget"]
        total_limit = budget["total_tokens"]
        per_source = budget.get("per_source", {})

        sections = []
        for src in sources:
            src_type = src["type"]
            content = src["content"]
            provenance = src.get("provenance", [])
            token_count = estimate_tokens(content)
            per_limit = per_source.get(src_type, total_limit)
            if token_count > per_limit:
                raise TokenBudgetExceeded(
                    f"source '{src_type}' uses {token_count} tokens, limit {per_limit}"
                )
            content_digest = canonical_sha256({"content": content})
            sections.append(
                {
                    "type": src_type,
                    "priority": src.get("priority", 0),
                    "token_count": token_count,
                    "provenance_refs": provenance,
                    "content_digest": content_digest,
                }
            )

        # 去重 + 优先级排序
        seen = set()
        unique = []
        for section in sorted(sections, key=lambda s: s["priority"], reverse=True):
            if section["content_digest"] in seen:
                continue
            seen.add(section["content_digest"])
            unique.append(section)

        total = sum(s["token_count"] for s in unique)
        if total > total_limit:
            raise TokenBudgetExceeded(f"context uses {total} tokens, limit {total_limit}")

        package = {
            "run_ref": descriptor["run_ref"],
            "model_call_sequence": descriptor["model_call_sequence"],
            "policy_ref": descriptor["policy_ref"],
            "sections": unique,
            "total_tokens": total,
            "redaction_summary": descriptor["redaction_summary"],
            "artifact_ref": descriptor["artifact_ref"],
            "content_digest": canonical_sha256({"sections": unique, "total_tokens": total}),
        }
        return ContextPackage.model_validate(package).model_dump(mode="json")
