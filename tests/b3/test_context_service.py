import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import path_config  # noqa: F401
from agent_platform_contracts.policies import canonical_sha256
from context.context_service import ContextService, TokenBudgetExceeded


class TestContextService(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(
            (path_config.B0_EXAMPLES / "valid" / "context-policy.json").read_text(encoding="utf-8")
        )

    def _descriptor(self, extra_sources=None):
        return {
            "run_ref": {"kind": "AgentRun", "id": "run_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f422"},
            "model_call_sequence": 1,
            "policy_ref": {
                "kind": "ContextPolicy",
                "id": "cpo_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f416",
                "version": "1.0.0",
                "digest": canonical_sha256({"p": 1}),
            },
            "artifact_ref": {
                "id": "art_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f427",
                "digest": canonical_sha256({"a": 1}),
            },
            "redaction_summary": {"secret_count": 0, "pii_count": 0},
            "sources": [
                {
                    "type": "task",
                    "content": "用户咨询",
                    "priority": 100,
                    "provenance": ["tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421"],
                },
                {
                    "type": "agent_spec",
                    "content": "售前咨询 Agent 定义",
                    "priority": 90,
                    "provenance": ["agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411"],
                },
                {
                    "type": "prompt",
                    "content": "你是一个专业的电商售前客服",
                    "priority": 80,
                    "provenance": ["prm_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f414"],
                },
            ]
            + (extra_sources or []),
        }

    def test_build_valid_context(self):
        service = ContextService(self.policy)
        package = service.build(self._descriptor())
        self.assertTrue(package["total_tokens"] > 0)
        self.assertEqual(len(package["sections"]), 3)
        self.assertEqual(package["sections"][0]["type"], "task")

    def test_deduplication(self):
        service = ContextService(self.policy)
        descriptor = self._descriptor(
            extra_sources=[
                {
                    "type": "task",
                    "content": "用户咨询",
                    "priority": 50,
                    "provenance": ["tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f422"],
                }
            ]
        )
        package = service.build(descriptor)
        self.assertEqual(len(package["sections"]), 3)

    def test_budget_exceeded(self):
        policy = json.loads(json.dumps(self.policy))
        policy["spec"]["token_budget"]["total_tokens"] = 2
        service = ContextService(policy)
        with self.assertRaises(TokenBudgetExceeded):
            service.build(self._descriptor())


if __name__ == "__main__":
    unittest.main()
