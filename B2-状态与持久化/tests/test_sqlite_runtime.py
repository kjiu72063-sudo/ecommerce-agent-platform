import asyncio
import tempfile
import unittest
import json
from pathlib import Path

import sys
import path_config
from runtime.in_memory_repositories import InMemoryTaskRepository
from runtime.sqlite_repositories import SQLiteRuntimeStore, SQLiteTaskRepository, SQLiteEventRepository
from runtime.event_store import EventStore
from runtime.task_service import TaskService
from agent_platform_contracts.policies import canonical_sha256


def run(coro):
    return asyncio.run(coro)


class TestSQLiteRuntime(unittest.TestCase):
    def test_events_and_tasks_survive_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "runtime.sqlite3"
            store = SQLiteRuntimeStore(db)
            task_repo = SQLiteTaskRepository(store=store)
            event_repo = SQLiteEventRepository(store=store)
            service = TaskService(task_repo, event_repo)
            task = json.loads((path_config.B0_EXAMPLES / "valid" / "task.json").read_text(encoding="utf-8"))
            run(service.create_task(task, {"actor_type": "system", "actor_id": "test"}))
            service_task = run(service.validate_task(task["metadata"]["id"], {"actor_type": "system", "actor_id": "test"}))
            events = run(event_repo.get_events(task["metadata"]["id"]))
            self.assertEqual(len(events), 2)
            ids = [event["metadata"]["id"] for event in events]
            sequences = [event["spec"]["sequence"] for event in events]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(sequences, [1, 2])
            for event in events:
                self.assertEqual(event["metadata"]["id"], event["spec"]["id"])
                self.assertEqual(event["spec"]["schema_ref"]["digest"], canonical_sha256(event["spec"]["data"]))
            store.close()

            reopened = SQLiteRuntimeStore(db)
            self.assertIsNotNone(run(SQLiteTaskRepository(store=reopened).get_task(task["metadata"]["id"])))
            self.assertEqual(len(run(SQLiteEventRepository(store=reopened).get_events(task["metadata"]["id"]))), 2)
            reopened.close()


if __name__ == "__main__":
    unittest.main()
