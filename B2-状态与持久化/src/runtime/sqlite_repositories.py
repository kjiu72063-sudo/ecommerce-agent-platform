"""SQLite persistence adapters for B2 runtime resources."""
from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from .in_memory_repositories import (
    InMemoryTaskRepository, InMemoryRunRepository, InMemoryEventRepository, InMemoryCheckpointRepository,
)


class SQLiteRuntimeStore:
    def __init__(self, database: str | Path = "b2_runtime.sqlite3"):
        self.database = str(database)
        self.db = sqlite3.connect(self.database)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, content TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, content TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            content TEXT NOT NULL, UNIQUE(subject_id, sequence)
        );
        CREATE TABLE IF NOT EXISTS run_versions (
            run_id TEXT NOT NULL, spec_snapshot TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            content TEXT NOT NULL, UNIQUE(run_id, sequence)
        );
        """)
        self._transaction_depth = 0
        self.db.commit()

    @asynccontextmanager
    async def transaction(self):
        outermost = self._transaction_depth == 0
        if outermost:
            self.db.execute("BEGIN")
        self._transaction_depth += 1
        try:
            yield self
            self._transaction_depth -= 1
            if outermost:
                self.db.commit()
        except Exception:
            self._transaction_depth = max(0, self._transaction_depth - 1)
            if outermost:
                self.db.rollback()
            raise

    def commit_if_needed(self):
        if self._transaction_depth == 0:
            self.db.commit()

    def close(self):
        self.db.close()


class SQLiteTaskRepository(InMemoryTaskRepository):
    def __init__(self, database: str | Path = "b2_runtime.sqlite3", store=None):
        super().__init__()
        self.store = store or SQLiteRuntimeStore(database)
        for row in self.store.db.execute("SELECT content FROM tasks"):
            task = json.loads(row[0])
            self._tasks[task["metadata"]["id"]] = task

    async def create_task(self, task: dict) -> str:
        result = await super().create_task(task)
        try:
            self.store.db.execute("INSERT INTO tasks VALUES (?,?)", (result, json.dumps(task, ensure_ascii=False, sort_keys=True)))
            self.store.commit_if_needed()
        except Exception:
            self.store.db.rollback(); self._tasks.pop(result, None); raise
        return result

    async def update_task_status(self, task_id, phase, updates=None):
        ok = await super().update_task_status(task_id, phase, updates)
        if ok:
            self.store.db.execute("UPDATE tasks SET content=? WHERE id=?", (json.dumps(self._tasks[task_id], ensure_ascii=False, sort_keys=True), task_id))
            self.store.commit_if_needed()
        return ok


class SQLiteRunRepository(InMemoryRunRepository):
    def __init__(self, database: str | Path = "b2_runtime.sqlite3", store=None):
        super().__init__(); self.store = store or SQLiteRuntimeStore(database)
        for row in self.store.db.execute("SELECT content FROM runs"):
            run = json.loads(row[0]); self._runs[run["metadata"]["id"]] = run

    async def create_run(self, run: dict) -> str:
        result = await super().create_run(run)
        try:
            self.store.db.execute("INSERT INTO runs VALUES (?,?)", (result, json.dumps(run, ensure_ascii=False, sort_keys=True)))
            self.store.commit_if_needed()
        except Exception:
            self.store.db.rollback(); self._runs.pop(result, None); raise
        return result

    async def update_run_status(self, run_id, phase, updates=None):
        ok = await super().update_run_status(run_id, phase, updates)
        if ok:
            self.store.db.execute("UPDATE runs SET content=? WHERE id=?", (json.dumps(self._runs[run_id], ensure_ascii=False, sort_keys=True), run_id)); self.store.commit_if_needed()
        return ok

    async def save_version(self, run_id: str, spec_snapshot: dict) -> None:
        await super().save_version(run_id, spec_snapshot)
        item = self._run_versions[run_id][-1]
        self.store.db.execute("INSERT INTO run_versions VALUES (?,?,?)",
                              (run_id, json.dumps(spec_snapshot, ensure_ascii=False, sort_keys=True), item["created_at"]))
        self.store.commit_if_needed()

    async def get_versions(self, run_id: str) -> list[dict]:
        rows = self.store.db.execute(
            "SELECT spec_snapshot, created_at FROM run_versions WHERE run_id=? ORDER BY rowid", (run_id,)).fetchall()
        return [{"run_id": run_id, "spec_snapshot": json.loads(row["spec_snapshot"]), "created_at": row["created_at"]} for row in rows]


class SQLiteCheckpointRepository(InMemoryCheckpointRepository):
    def __init__(self, database: str | Path = "b2_runtime.sqlite3", store=None):
        super().__init__(); self.store = store or SQLiteRuntimeStore(database)
        for row in self.store.db.execute("SELECT content FROM checkpoints ORDER BY run_id, sequence"):
            checkpoint = json.loads(row[0])
            self._checkpoints[checkpoint["metadata"]["id"]] = checkpoint

    async def create_checkpoint(self, checkpoint: dict) -> str:
        result = await super().create_checkpoint(checkpoint)
        checkpoint_id = checkpoint["metadata"]["id"]
        run_id = checkpoint["spec"]["run_ref"]["id"]
        sequence = checkpoint["spec"]["sequence"]
        try:
            self.store.db.execute("INSERT INTO checkpoints VALUES (?,?,?,?)", (checkpoint_id, run_id, sequence, json.dumps(checkpoint, ensure_ascii=False, sort_keys=True)))
            self.store.commit_if_needed()
        except Exception:
            self.store.db.rollback(); self._checkpoints.pop(checkpoint_id, None); raise
        return result


class SQLiteEventRepository(InMemoryEventRepository):
    def __init__(self, database: str | Path = "b2_runtime.sqlite3", store=None):
        super().__init__(); self.store = store or SQLiteRuntimeStore(database)
        for row in self.store.db.execute("SELECT content FROM events ORDER BY subject_id, sequence"):
            self._events.append(json.loads(row[0]))

    async def save_event(self, event: dict) -> str:
        event_id = event["metadata"]["id"]
        subject_id = event["spec"]["subject_ref"]["id"]
        sequence = event["spec"]["sequence"]
        self.store.db.execute("INSERT INTO events VALUES (?,?,?,?)", (event_id, subject_id, sequence, json.dumps(event, ensure_ascii=False, sort_keys=True)))
        self.store.commit_if_needed(); self._events.append(copy.deepcopy(event)); return event_id

    async def get_next_sequence(self, subject_id: str) -> int:
        row = self.store.db.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM events WHERE subject_id=?", (subject_id,)).fetchone()
        return int(row[0])
