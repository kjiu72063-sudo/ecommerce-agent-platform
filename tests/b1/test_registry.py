"""B1 能力注册中心 - 测试用例"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

# 使用统一路径配置
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from path_config import B0_EXAMPLES
from registry import DefinitionFilter, InMemoryDefinitionRepository, RegistryService


def load_valid_example(name: str) -> dict:
    """加载有效示例"""
    path = B0_EXAMPLES / "valid" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_async(coro):
    """运行异步函数"""
    return asyncio.run(coro)


class TestInMemoryRepository(unittest.TestCase):
    """内存版 Repository 测试"""

    def setUp(self):
        self.repo = InMemoryDefinitionRepository()

    def test_create_and_get(self):
        """测试创建和获取"""
        obj = {"metadata": {"id": "test_001"}, "kind": "Test"}
        obj_id = run_async(self.repo.create(obj))
        self.assertEqual(obj_id, "test_001")

        result = run_async(self.repo.get_by_id("test_001"))
        self.assertIsNotNone(result)
        self.assertEqual(result["kind"], "Test")

    def test_get_nonexistent(self):
        """测试获取不存在的对象"""
        result = run_async(self.repo.get_by_id("nonexistent"))
        self.assertIsNone(result)

    def test_create_duplicate_fails(self):
        """测试重复创建失败"""
        obj = {"metadata": {"id": "test_001"}, "kind": "Test"}
        run_async(self.repo.create(obj))

        with self.assertRaises(ValueError):
            run_async(self.repo.create(obj))

    def test_update_with_revision(self):
        """测试乐观并发更新"""
        obj = {
            "metadata": {"id": "test_001", "revision": 1},
            "kind": "Test",
            "status": {"phase": "draft"},
        }
        run_async(self.repo.create(obj))

        # 正确的 revision
        success = run_async(self.repo.update("test_001", 1, {"status": {"phase": "testing"}}))
        self.assertTrue(success)

        # 错误的 revision（已被其他人修改）
        success = run_async(self.repo.update("test_001", 1, {"status": {"phase": "active"}}))
        self.assertFalse(success)

    def test_list_by_filter(self):
        """测试按过滤器查询"""
        obj1 = {
            "metadata": {
                "id": "agt_001",
                "namespace": "dev",
                "key": "agent-1",
                "created_at": "2026-09-01T00:00:00Z",
            },
            "kind": "AgentSpec",
            "status": {"phase": "active"},
        }
        obj2 = {
            "metadata": {
                "id": "skl_001",
                "namespace": "dev",
                "key": "skill-1",
                "created_at": "2026-09-01T00:00:00Z",
            },
            "kind": "SkillManifest",
            "status": {"phase": "draft"},
        }

        run_async(self.repo.create(obj1))
        run_async(self.repo.create(obj2))

        # 按 kind 过滤
        filter = DefinitionFilter(kind="AgentSpec")
        results = run_async(self.repo.list_by_filter(filter))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["kind"], "AgentSpec")

        # 按 phase 过滤
        filter = DefinitionFilter(phase="draft")
        results = run_async(self.repo.list_by_filter(filter))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"]["phase"], "draft")


class TestRegistryService(unittest.TestCase):
    """注册中心服务测试"""

    def setUp(self):
        self.repo = InMemoryDefinitionRepository()
        self.service = RegistryService(self.repo)

    def test_register_definition(self):
        """测试注册定义对象"""
        payload = load_valid_example("agent-spec")

        result = run_async(
            self.service.register_definition(
                kind="agent-spec",
                payload=payload,
                actor={"actor_type": "user", "actor_id": "usr_test"},
            )
        )

        self.assertIn("id", result)
        self.assertIn("content_digest", result)
        self.assertTrue(result["content_digest"].startswith("sha256:"))

    def test_register_duplicate_fails(self):
        """测试重复注册失败"""
        payload = load_valid_example("agent-spec")

        run_async(
            self.service.register_definition(
                kind="agent-spec",
                payload=payload,
                actor={"actor_type": "user", "actor_id": "usr_test"},
            )
        )

        with self.assertRaises(ValueError):
            run_async(
                self.service.register_definition(
                    kind="agent-spec",
                    payload=payload,
                    actor={"actor_type": "user", "actor_id": "usr_test"},
                )
            )

    def test_transition_state(self):
        """测试状态迁移"""
        payload = load_valid_example("agent-spec")
        # 修改初始状态为 draft
        payload["status"]["phase"] = "draft"

        result = run_async(
            self.service.register_definition(
                kind="agent-spec",
                payload=payload,
                actor={"actor_type": "user", "actor_id": "usr_test"},
            )
        )

        obj_id = result["id"]

        # draft -> testing
        result = run_async(self.service.transition_state(obj_id, "testing", reason="开始测试"))
        self.assertEqual(result["phase"], "testing")

        # testing -> awaiting_approval
        result = run_async(
            self.service.transition_state(obj_id, "awaiting_approval", reason="测试通过")
        )
        self.assertEqual(result["phase"], "awaiting_approval")

    def test_invalid_transition_fails(self):
        """测试非法状态迁移失败"""
        payload = load_valid_example("agent-spec")

        result = run_async(
            self.service.register_definition(
                kind="agent-spec",
                payload=payload,
                actor={"actor_type": "user", "actor_id": "usr_test"},
            )
        )

        obj_id = result["id"]

        # active -> draft（不允许）
        with self.assertRaises(ValueError):
            run_async(self.service.transition_state(obj_id, "draft", reason="非法迁移"))

    def test_get_definition(self):
        """测试获取定义对象"""
        payload = load_valid_example("agent-spec")

        result = run_async(
            self.service.register_definition(
                kind="agent-spec",
                payload=payload,
                actor={"actor_type": "user", "actor_id": "usr_test"},
            )
        )

        obj = run_async(self.service.get_definition(result["id"]))
        self.assertIsNotNone(obj)
        self.assertEqual(obj["kind"], "AgentSpec")

    def test_list_definitions(self):
        """测试查询定义对象列表"""
        # 注册 AgentSpec
        agent_spec = load_valid_example("agent-spec")
        run_async(
            self.service.register_definition(
                kind="agent-spec",
                payload=agent_spec,
                actor={"actor_type": "user", "actor_id": "usr_test"},
            )
        )

        # 查询所有
        results = run_async(self.service.list_definitions(DefinitionFilter()))
        self.assertEqual(len(results), 1)

        # 按 kind 查询
        results = run_async(self.service.list_definitions(DefinitionFilter(kind="AgentSpec")))
        self.assertEqual(len(results), 1)

        # 按不存在的 kind 查询
        results = run_async(self.service.list_definitions(DefinitionFilter(kind="ToolManifest")))
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
