"""B1 DependencyResolver 单元与集成测试。"""

import asyncio
import sys
import unittest
from pathlib import Path

import path_config  # noqa: F401

from registry import InMemoryDefinitionRepository
from registry.dependency_resolver import (
    DependencyResolver,
    DependencyCycleError,
    DependencyResolveError,
)


def run(coro):
    return asyncio.run(coro)


def make_obj(object_id, version, phase="active"):
    return {"metadata": {"id": object_id, "version": version}, "status": {"phase": phase}}


class StubRepo:
    """手写 stub：返回固定的对象与依赖，便于精准断言解析行为。"""

    def __init__(self, objects, dependencies):
        self.objects = {obj["metadata"]["id"]: obj for obj in objects}
        self.dependencies = dependencies  # list[dict(target_id, target_version)]

    async def get_by_id(self, object_id):
        return self.objects.get(object_id)

    async def get_dependencies(self, object_id, version):
        return [dep for dep in self.dependencies if dep.get("source_id") == object_id]


class TestDependencyResolverUnit(unittest.TestCase):
    def test_topological_order_dependency_first(self):
        # A -> B -> C，后序收集应得到 [C, B, A]
        a = make_obj("a1", "1.0.0")
        b = make_obj("b1", "1.0.0")
        c = make_obj("c1", "1.0.0")
        deps = [
            {"source_id": "a1", "target_id": "b1", "target_version": "1.0.0"},
            {"source_id": "b1", "target_id": "c1", "target_version": "1.0.0"},
        ]
        repo = StubRepo([a, b, c], deps)
        result = run(DependencyResolver(repo).resolve("a1", "1.0.0"))
        self.assertEqual(result["topological_order"], ["c1", "b1", "a1"])
        self.assertEqual(len(result["nodes"]), 3)
        self.assertEqual(len(result["edges"]), 2)

    def test_circular_dependency_rejected(self):
        x = make_obj("x1", "1.0.0")
        y = make_obj("y1", "1.0.0")
        deps = [
            {"source_id": "x1", "target_id": "y1", "target_version": "1.0.0"},
            {"source_id": "y1", "target_id": "x1", "target_version": "1.0.0"},
        ]
        repo = StubRepo([x, y], deps)
        with self.assertRaises(DependencyCycleError):
            run(DependencyResolver(repo).resolve("x1", "1.0.0"))

    def test_version_mismatch_rejected(self):
        obj = make_obj("p1", "1.0.0")
        deps = [{"source_id": "root", "target_id": "p1", "target_version": "2.0.0"}]
        repo = StubRepo([obj], deps)
        with self.assertRaises(DependencyResolveError):
            run(DependencyResolver(repo).resolve("root", "1.0.0"))

    def test_missing_target_rejected(self):
        repo = StubRepo([], [{"source_id": "root", "target_id": "ghost", "target_version": "1.0.0"}])
        with self.assertRaises(DependencyResolveError):
            run(DependencyResolver(repo).resolve("root", "1.0.0"))

    def test_not_resolvable_phase_rejected(self):
        draft = make_obj("d1", "1.0.0", phase="draft")
        deps = [{"source_id": "root", "target_id": "d1", "target_version": "1.0.0"}]
        repo = StubRepo([draft], deps)
        with self.assertRaises(DependencyResolveError):
            run(DependencyResolver(repo).resolve("root", "1.0.0"))

    def test_resume_run_accepts_deprecated(self):
        root = make_obj("root", "1.0.0")
        deprecated = make_obj("d1", "1.0.0", phase="deprecated")
        deps = [{"source_id": "root", "target_id": "d1", "target_version": "1.0.0"}]
        repo = StubRepo([root, deprecated], deps)
        # new_run 拒绝 deprecated
        with self.assertRaises(DependencyResolveError):
            run(DependencyResolver(repo).resolve("root", "1.0.0", purpose="new_run"))
        # resume_run 接受 deprecated
        result = run(DependencyResolver(repo).resolve("root", "1.0.0", purpose="resume_run"))
        self.assertIn("d1", result["topological_order"])


class TestDependencyResolverIntegration(unittest.TestCase):
    def test_resolve_graph_over_in_memory_repository(self):
        repo = InMemoryDefinitionRepository()
        tool = make_obj("tol_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f413", "1.0.0")
        skill = make_obj("skl_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f412", "1.0.0")
        agent = make_obj("agt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f411", "1.0.0")
        run(repo.create(tool))
        run(repo.create(skill))
        run(repo.create(agent))
        run(repo.save_dependency(skill["metadata"]["id"], "1.0.0", tool["metadata"]["id"], "1.0.0", "tool"))
        run(repo.save_dependency(agent["metadata"]["id"], "1.0.0", skill["metadata"]["id"], "1.0.0", "skill"))
        result = run(DependencyResolver(repo).resolve(agent["metadata"]["id"], "1.0.0"))
        self.assertEqual(result["topological_order"], [tool["metadata"]["id"], skill["metadata"]["id"], agent["metadata"]["id"]])
        self.assertEqual(len(result["edges"]), 2)


if __name__ == "__main__":
    unittest.main()
