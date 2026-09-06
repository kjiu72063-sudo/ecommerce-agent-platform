"""B0 契约包一致性测试

测试所有 Schema、示例、状态机和策略函数的正确性。
"""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

# 测试路径
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
VALID_DIR = ROOT / "examples" / "valid"
INVALID_DIR = ROOT / "examples" / "invalid"
STATE_MACHINES_DIR = ROOT / "state-machines"


class SchemaStructureTests(unittest.TestCase):
    """Schema 结构测试"""

    def test_all_schema_files_exist(self):
        """测试所有 Schema 文件存在"""
        expected_common = ["common-types.schema.json", "standard-error.schema.json"]
        expected_definitions = [
            "agent-spec.schema.json", "skill-manifest.schema.json",
            "tool-manifest.schema.json", "prompt-package.schema.json",
            "model-policy.schema.json", "context-policy.schema.json",
            "loop-profile.schema.json", "permission-profile.schema.json"
        ]
        expected_runtime = [
            "task.schema.json", "agent-run.schema.json",
            "checkpoint.schema.json", "tool-call.schema.json",
            "approval.schema.json", "artifact.schema.json", "event.schema.json"
        ]

        common_files = [f.name for f in (SCHEMA_DIR / "common").glob("*.schema.json")]
        definition_files = [f.name for f in (SCHEMA_DIR / "definitions").glob("*.schema.json")]
        runtime_files = [f.name for f in (SCHEMA_DIR / "runtime").glob("*.schema.json")]

        self.assertEqual(sorted(common_files), sorted(expected_common))
        self.assertEqual(sorted(definition_files), sorted(expected_definitions))
        self.assertEqual(sorted(runtime_files), sorted(expected_runtime))

    def test_schema_version_and_closed(self):
        """测试 Schema 版本和严格模式"""
        for schema_dir in [SCHEMA_DIR / "common", SCHEMA_DIR / "definitions", SCHEMA_DIR / "runtime"]:
            for path in schema_dir.glob("*.schema.json"):
                with self.subTest(path=path.name):
                    schema = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        schema.get("$schema"),
                        "https://json-schema.org/draft/2020-12/schema"
                    )
                    self.assertEqual(schema.get("x-contract-version"), "0.2.0")


class ValidExampleTests(unittest.TestCase):
    """有效示例测试"""

    def test_all_valid_examples_exist(self):
        """测试所有有效示例存在"""
        expected = [
            "agent-spec.json", "skill-manifest.json", "tool-manifest.json",
            "prompt-package.json", "model-policy.json", "context-policy.json",
            "loop-profile.json", "permission-profile.json",
            "task.json", "agent-run.json", "checkpoint.json",
            "tool-call.json", "approval.json", "artifact.json", "event.json"
        ]
        actual = [f.name for f in VALID_DIR.glob("*.json")]
        self.assertEqual(sorted(actual), sorted(expected))

    def test_valid_examples_have_correct_structure(self):
        """测试有效示例结构正确"""
        for path in VALID_DIR.glob("*.json"):
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("api_version", data)
                self.assertIn("kind", data)
                self.assertIn("metadata", data)
                self.assertIn("spec", data)
                self.assertIn("status", data)
                self.assertEqual(data["api_version"], "agent-platform/v1alpha1")


class InvalidExampleTests(unittest.TestCase):
    """无效示例测试"""

    def test_invalid_examples_have_expected_error(self):
        """测试无效示例有预期错误码"""
        for path in INVALID_DIR.glob("*.json"):
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("target_model", data)
                self.assertIn("expected_error_code", data)
                self.assertIn("description", data)
                self.assertIn("payload", data)

                # 验证错误码格式
                error_code = data["expected_error_code"]
                self.assertRegex(error_code, r"^[A-Z][A-Z0-9_]{2,127}$")


class StateMachineTests(unittest.TestCase):
    """状态机测试"""

    def test_all_state_machine_files_exist(self):
        """测试所有状态机文件存在"""
        expected = [
            "definition.json", "task.json", "agent-run.json",
            "tool-call.json", "approval.json", "artifact.json"
        ]
        actual = [f.name for f in STATE_MACHINES_DIR.glob("*.json")]
        self.assertEqual(sorted(actual), sorted(expected))

    def test_state_machine_structure(self):
        """测试状态机结构"""
        for path in STATE_MACHINES_DIR.glob("*.json"):
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("name", data)
                self.assertIn("description", data)
                self.assertIn("transitions", data)
                self.assertIn("terminal_states", data)
                self.assertIn("initial_state", data)

    def test_terminal_states_have_no_transitions(self):
        """测试终态没有迁移"""
        for path in STATE_MACHINES_DIR.glob("*.json"):
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                transitions = data["transitions"]
                terminal_states = data["terminal_states"]

                for state in terminal_states:
                    self.assertIn(state, transitions)
                    self.assertEqual(
                        transitions[state], [],
                        f"Terminal state {state} should have no transitions"
                    )

    def test_initial_state_exists(self):
        """测试初始状态存在"""
        for path in STATE_MACHINES_DIR.glob("*.json"):
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn(data["initial_state"], data["transitions"])


class PolicyTests(unittest.TestCase):
    """策略函数测试"""

    def test_canonical_json_deterministic(self):
        """测试规范化 JSON 确定性"""
        from src.agent_platform_contracts.policies import canonical_json

        first = {"b": 2, "a": ["中文", 1]}
        second = {"a": ["中文", 1], "b": 2}
        self.assertEqual(canonical_json(first), canonical_json(second))

    def test_canonical_sha256_deterministic(self):
        """测试 SHA-256 摘要确定性"""
        from src.agent_platform_contracts.policies import canonical_sha256

        first = {"b": 2, "a": ["中文", 1]}
        second = {"a": ["中文", 1], "b": 2}
        self.assertEqual(canonical_sha256(first), canonical_sha256(second))

    def test_combine_permission_decisions_deny_priority(self):
        """测试权限决策 Deny 优先"""
        from src.agent_platform_contracts.policies import combine_permission_decisions

        self.assertEqual(combine_permission_decisions(["allow", "require_approval", "deny"]), "deny")
        self.assertEqual(combine_permission_decisions(["allow", "require_approval"]), "require_approval")
        self.assertEqual(combine_permission_decisions(["allow", "allow"]), "allow")
        self.assertEqual(combine_permission_decisions([]), "deny")

    def test_can_auto_retry_unknown_state(self):
        """测试 unknown 状态不能自动重试"""
        from src.agent_platform_contracts.policies import can_auto_retry

        self.assertFalse(can_auto_retry(
            retryable=True, safe_to_retry=True,
            tool_allows_retry=True, state="unknown"
        ))
        self.assertTrue(can_auto_retry(
            retryable=True, safe_to_retry=True,
            tool_allows_retry=True, state="failed"
        ))

    def test_definition_is_resolvable(self):
        """测试定义对象解析规则"""
        from src.agent_platform_contracts.policies import definition_is_resolvable

        # 新 Run 只能解析 active
        self.assertTrue(definition_is_resolvable(definition_phase="active", purpose="new_run"))
        self.assertFalse(definition_is_resolvable(definition_phase="deprecated", purpose="new_run"))

        # 恢复 Run 可以解析 active 和 deprecated
        self.assertTrue(definition_is_resolvable(definition_phase="active", purpose="resume_run"))
        self.assertTrue(definition_is_resolvable(definition_phase="deprecated", purpose="resume_run"))
        self.assertFalse(definition_is_resolvable(definition_phase="blocked", purpose="resume_run"))


class ResourceModelTests(unittest.TestCase):
    """资源模型测试"""

    def test_fifteen_resource_models(self):
        """测试 15 个资源模型"""
        from src.agent_platform_contracts.models import RESOURCE_MODELS
        self.assertEqual(len(RESOURCE_MODELS), 15)

    def test_definition_and_runtime_kinds(self):
        """测试定义对象和运行对象分类"""
        from src.agent_platform_contracts.models import DEFINITION_KINDS

        definition_kinds = {
            "AgentSpec", "SkillManifest", "ToolManifest", "PromptPackage",
            "ModelPolicy", "ContextPolicy", "LoopProfile", "PermissionProfile"
        }
        self.assertEqual(DEFINITION_KINDS, definition_kinds)


class IdempotencyTests(unittest.TestCase):
    """幂等性测试"""

    def test_scoped_task_idempotency_key(self):
        """测试 Task 幂等键作用域"""
        from src.agent_platform_contracts.policies import scoped_task_idempotency_key

        key_a = scoped_task_idempotency_key("ten_a", "api", "request-1")
        key_b = scoped_task_idempotency_key("ten_b", "api", "request-1")
        self.assertNotEqual(key_a, key_b)

    def test_scoped_tool_idempotency_key(self):
        """测试 Tool 幂等键作用域"""
        from src.agent_platform_contracts.policies import scoped_tool_idempotency_key

        key_a = scoped_tool_idempotency_key("tol_a", "resource:a", "request-1")
        key_b = scoped_tool_idempotency_key("tol_a", "resource:b", "request-1")
        self.assertNotEqual(key_a, key_b)


class LeaseTests(unittest.TestCase):
    """租约测试"""

    def test_lease_allows_commit(self):
        """测试租约提交检查"""
        from src.agent_platform_contracts.policies import lease_allows_commit

        expires = datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc)
        now = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)

        # 有效租约
        self.assertTrue(lease_allows_commit(
            fencing_token=2, current_fencing_token=2,
            expires_at=expires, now=now
        ))

        # 过期令牌
        self.assertFalse(lease_allows_commit(
            fencing_token=1, current_fencing_token=2,
            expires_at=expires, now=now
        ))

        # 过期时间
        self.assertFalse(lease_allows_commit(
            fencing_token=2, current_fencing_token=2,
            expires_at=expires, now=expires
        ))


if __name__ == "__main__":
    unittest.main()
