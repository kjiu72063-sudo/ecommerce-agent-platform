import asyncio
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import path_config
from runtime.in_memory_repositories import InMemoryRunRepository, InMemoryEventRepository, InMemoryCheckpointRepository
from runtime.sqlite_repositories import (
    SQLiteRuntimeStore, SQLiteRunRepository, SQLiteEventRepository, SQLiteCheckpointRepository,
)
from runtime.run_service import RunService
from runtime.checkpoint_service import CheckpointService


def run(coro):
    return asyncio.run(coro)


class TestRunService(unittest.TestCase):
    def test_run_lifecycle_in_memory(self):
        runs = InMemoryRunRepository()
        events = InMemoryEventRepository()
        service = RunService(runs, events)
        payload = json.loads((path_config.B0_EXAMPLES / "valid" / "agent-run.json").read_text(encoding="utf-8"))
        run_id = payload["metadata"]["id"]
        created = run(service.create_run(payload, {"actor_type": "system", "actor_id": "test"}))
        self.assertEqual(created["phase"], "created")
        self.assertEqual(run(service.resolve_run(run_id))["phase"], "resolving")
        self.assertEqual(run(service.ready_run(run_id))["phase"], "ready")
        self.assertEqual(run(service.start_run(run_id))["phase"], "running")
        self.assertEqual(run(service.wait_run(run_id, "waiting_tool"))["phase"], "waiting_tool")
        self.assertEqual(run(service.start_run(run_id))["phase"], "running")
        self.assertEqual(run(service.complete_run(run_id))["phase"], "succeeded")
        events_stream = run(events.get_events(run_id))
        self.assertEqual(events_stream[-1]["spec"]["type"], "run.succeeded")

    def test_run_lifecycle_sqlite_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "runtime.sqlite3"
            store = SQLiteRuntimeStore(db)
            runs = SQLiteRunRepository(store=store)
            events = SQLiteEventRepository(store=store)
            service = RunService(runs, events)
            payload = json.loads((path_config.B0_EXAMPLES / "valid" / "agent-run.json").read_text(encoding="utf-8"))
            run_id = payload["metadata"]["id"]
            run(service.create_run(payload, {"actor_type": "system", "actor_id": "test"}))
            run(service.resolve_run(run_id))
            run(service.ready_run(run_id))
            run(service.start_run(run_id))
            store.close()

            reopened = SQLiteRuntimeStore(db)
            restored = run(SQLiteRunRepository(store=reopened).get_run(run_id))
            self.assertEqual(restored["status"]["phase"], "running")
            self.assertEqual(len(run(SQLiteEventRepository(store=reopened).get_events(run_id))), 4)
            reopened.close()


class TestCheckpointService(unittest.TestCase):
    def test_checkpoint_create_and_latest(self):
        checkpoints = InMemoryCheckpointRepository()
        service = CheckpointService(checkpoints)
        payload = json.loads((path_config.B0_EXAMPLES / "valid" / "checkpoint.json").read_text(encoding="utf-8"))
        checkpoint_id = payload["metadata"]["id"]
        run_id = payload["spec"]["run_ref"]["id"]
        result = run(service.create_checkpoint(payload))
        self.assertEqual(result["id"], checkpoint_id)
        latest = run(service.get_latest_checkpoint(run_id))
        self.assertEqual(latest["metadata"]["id"], checkpoint_id)
        self.assertEqual(run(service.get_checkpoint(checkpoint_id))["status"]["phase"], "committed")

    def test_checkpoint_sqlite_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "runtime.sqlite3"
            store = SQLiteRuntimeStore(db)
            service = CheckpointService(SQLiteCheckpointRepository(store=store))
            payload = json.loads((path_config.B0_EXAMPLES / "valid" / "checkpoint.json").read_text(encoding="utf-8"))
            checkpoint_id = payload["metadata"]["id"]
            run_id = payload["spec"]["run_ref"]["id"]
            run(service.create_checkpoint(payload))
            store.close()

            reopened = SQLiteRuntimeStore(db)
            restored = run(SQLiteCheckpointRepository(store=reopened).get_checkpoint(checkpoint_id))
            self.assertEqual(restored["metadata"]["id"], checkpoint_id)
            self.assertEqual(run(SQLiteCheckpointRepository(store=reopened).get_latest_checkpoint(run_id))["metadata"]["id"], checkpoint_id)
            reopened.close()


if __name__ == "__main__":
    unittest.main()
