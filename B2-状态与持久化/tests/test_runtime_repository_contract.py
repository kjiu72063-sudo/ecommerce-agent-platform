import asyncio
import json
import tempfile
import unittest
from pathlib import Path
import sys
import path_config
from runtime.in_memory_repositories import InMemoryTaskRepository, InMemoryEventRepository
from runtime.sqlite_repositories import SQLiteRuntimeStore, SQLiteTaskRepository, SQLiteEventRepository


def run(coro):
    return asyncio.run(coro)


class TaskRepositoryContractMixin:
    def make_repo(self):
        raise NotImplementedError

    def test_task_persistence_contract(self):
        task_repo, store, cleanup = self.make_repo()
        try:
            task = json.loads((path_config.B0_EXAMPLES / "valid" / "task.json").read_text(encoding="utf-8"))
            task["spec"]["idempotency_key"] = "ten_test:api:idem-001"
            task_id = run(task_repo.create_task(task))
            first = run(task_repo.get_task(task_id))
            first["metadata"]["id"] = "mutated"
            self.assertNotEqual(run(task_repo.get_task(task_id))["metadata"]["id"], "mutated")
            self.assertTrue(run(task_repo.update_task_status(task_id, "validated")))
            self.assertEqual(run(task_repo.get_task(task_id))["status"]["phase"], "validated")
            self.assertIsNotNone(run(task_repo.find_by_idempotency_key("ten_test", "api", "idem-001")))
        finally:
            cleanup()


class TestInMemoryTaskRepository(TaskRepositoryContractMixin, unittest.TestCase):
    def make_repo(self):
        return InMemoryTaskRepository(), None, lambda: None


class TestSQLiteTaskRepository(TaskRepositoryContractMixin, unittest.TestCase):
    def make_repo(self):
        tmp = tempfile.TemporaryDirectory()
        store = SQLiteRuntimeStore(Path(tmp.name) / "runtime.sqlite3")
        return SQLiteTaskRepository(store=store), store, lambda: (store.close(), tmp.cleanup())


class EventRepositoryContractMixin:
    def make_repo(self):
        raise NotImplementedError

    def test_event_sequence_contract(self):
        repo, store, cleanup = self.make_repo()
        try:
            subject = "tsk_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f421"
            for sequence in (1, 2):
                event_id = f"evt_0198f6d0-7ef0-7b0e-a0d3-5f9c96c7f42{sequence}"
                event = {"metadata": {"id": event_id}, "spec": {"subject_ref": {"id": subject}, "sequence": sequence}}
                run(repo.save_event(event))
            self.assertEqual(run(repo.get_next_sequence(subject)), 3)
            self.assertEqual([e["spec"]["sequence"] for e in run(repo.get_events(subject))], [1, 2])
        finally:
            cleanup()


class TestInMemoryEventRepository(EventRepositoryContractMixin, unittest.TestCase):
    def make_repo(self):
        return InMemoryEventRepository(), None, lambda: None


class TestSQLiteEventRepository(EventRepositoryContractMixin, unittest.TestCase):
    def make_repo(self):
        tmp = tempfile.TemporaryDirectory()
        store = SQLiteRuntimeStore(Path(tmp.name) / "runtime.sqlite3")
        return SQLiteEventRepository(store=store), store, lambda: (store.close(), tmp.cleanup())
