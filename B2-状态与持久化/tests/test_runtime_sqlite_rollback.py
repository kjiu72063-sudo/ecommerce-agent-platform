import asyncio
import json
import tempfile
import unittest
from pathlib import Path
import sys
import path_config
from runtime.sqlite_repositories import SQLiteRuntimeStore, SQLiteTaskRepository, SQLiteEventRepository
from runtime.task_service import TaskService


class FailingEventRepository(SQLiteEventRepository):
    async def save_event(self, event):
        raise RuntimeError("event failure")


class TestRuntimeRollback(unittest.TestCase):
    def test_task_update_rolls_back_when_event_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "runtime.sqlite3"
            store = SQLiteRuntimeStore(db)
            tasks = SQLiteTaskRepository(store=store)
            events = FailingEventRepository(store=store)
            service = TaskService(tasks, events)
            payload = json.loads((path_config.B0_EXAMPLES / "valid" / "task.json").read_text(encoding="utf-8"))
            task_id = payload["metadata"]["id"]
            # Seed without an event, then make validation fail at event persistence.
            asyncio.run(tasks.create_task(payload))
            with self.assertRaises(RuntimeError):
                asyncio.run(service.start_task(task_id))
            store.close()
            reopened = SQLiteRuntimeStore(db)
            restored = asyncio.run(SQLiteTaskRepository(store=reopened).get_task(task_id))
            self.assertEqual(restored["status"]["phase"], payload["status"]["phase"])
            reopened.close()


if __name__ == "__main__":
    unittest.main()
