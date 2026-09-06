"""B2 状态与持久化 - 测试用例"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

import path_config
from path_config import B0_EXAMPLES

from runtime import TaskService, InMemoryTaskRepository, InMemoryEventRepository, TaskFilter


def load_valid_example(name: str) -> dict:
    path = B0_EXAMPLES / "valid" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_async(coro):
    return asyncio.run(coro)


class TestTaskService(unittest.TestCase):

    def setUp(self):
        self.task_repo = InMemoryTaskRepository()
        self.event_repo = InMemoryEventRepository()
        self.service = TaskService(self.task_repo, self.event_repo)

    def test_create_task(self):
        payload = load_valid_example("task")
        result = run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        self.assertIn("id", result)
        self.assertEqual(result["phase"], "created")

    def test_create_duplicate_task(self):
        payload = load_valid_example("task")
        run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        result = run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        self.assertEqual(result["status"], "already_exists")

    def test_task_lifecycle(self):
        payload = load_valid_example("task")
        result = run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        task_id = result["id"]

        # created -> validated
        result = run_async(self.service.validate_task(task_id, {"actor_type": "user", "actor_id": "usr_test"}))
        self.assertEqual(result["phase"], "validated")

        # validated -> queued
        result = run_async(self.service.queue_task(task_id))
        self.assertEqual(result["phase"], "queued")

        # queued -> running
        result = run_async(self.service.start_task(task_id))
        self.assertEqual(result["phase"], "running")

        # running -> succeeded
        result = run_async(self.service.complete_task(task_id))
        self.assertEqual(result["phase"], "succeeded")

    def test_invalid_transition(self):
        payload = load_valid_example("task")
        result = run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        task_id = result["id"]

        # created -> running (not allowed)
        with self.assertRaises(ValueError):
            run_async(self.service.start_task(task_id))

    def test_cancel_task(self):
        payload = load_valid_example("task")
        result = run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        task_id = result["id"]

        result = run_async(self.service.cancel_task(task_id, reason="用户取消"))
        self.assertEqual(result["phase"], "cancelled")

    def test_fail_task(self):
        payload = load_valid_example("task")
        result = run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        task_id = result["id"]

        # created -> validated -> queued -> running -> failed
        run_async(self.service.validate_task(task_id, {"actor_type": "user", "actor_id": "usr_test"}))
        run_async(self.service.queue_task(task_id))
        run_async(self.service.start_task(task_id))

        result = run_async(self.service.fail_task(task_id, "INTERNAL_ERROR", "测试错误"))
        self.assertEqual(result["phase"], "failed")

    def test_events_published(self):
        payload = load_valid_example("task")
        result = run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))
        task_id = result["id"]

        events = run_async(self.event_repo.get_events(task_id))
        self.assertGreater(len(events), 0)
        self.assertEqual(events[0]['spec']['type'], 'task.created')


class TestTaskFilter(unittest.TestCase):

    def setUp(self):
        self.task_repo = InMemoryTaskRepository()
        self.event_repo = InMemoryEventRepository()
        self.service = TaskService(self.task_repo, self.event_repo)

    def test_filter_by_phase(self):
        payload = load_valid_example("task")
        run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))

        results = run_async(self.service.list_tasks(TaskFilter(phase="created")))
        self.assertEqual(len(results), 1)

        results = run_async(self.service.list_tasks(TaskFilter(phase="running")))
        self.assertEqual(len(results), 0)

    def test_filter_by_domain(self):
        payload = load_valid_example("task")
        run_async(self.service.create_task(
            payload=payload,
            actor={"actor_type": "user", "actor_id": "usr_test"}
        ))

        results = run_async(self.service.list_tasks(TaskFilter(domain="development")))
        self.assertEqual(len(results), 1)

        results = run_async(self.service.list_tasks(TaskFilter(domain="ecommerce")))
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
