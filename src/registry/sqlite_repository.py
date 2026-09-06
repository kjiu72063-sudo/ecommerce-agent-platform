"""B1 SQLite persistence backend.

The in-memory repository remains the prototype backend; this class adds a
small, dependency-free SQLite persistence adapter for local integration use.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from .in_memory_repository import InMemoryDefinitionRepository


class SQLiteDefinitionRepository(InMemoryDefinitionRepository):
    """SQLite-backed DefinitionRepository with the same public contract."""

    def __init__(self, database: str | Path = "b1_registry.sqlite3"):
        super().__init__()
        self.database = str(database)
        self._db = sqlite3.connect(self.database)
        self._db.row_factory = sqlite3.Row
        self._transaction_depth = 0
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS definitions (
                id TEXT PRIMARY KEY, namespace TEXT NOT NULL, object_key TEXT NOT NULL,
                version TEXT NOT NULL, revision INTEGER NOT NULL, kind TEXT NOT NULL,
                content TEXT NOT NULL, UNIQUE(namespace, object_key, version)
            );
            CREATE TABLE IF NOT EXISTS definition_versions (
                object_id TEXT NOT NULL, version TEXT NOT NULL, revision INTEGER NOT NULL,
                content_digest TEXT NOT NULL, spec_snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL, created_by TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS definition_dependencies (
                source_id TEXT NOT NULL, source_version TEXT NOT NULL,
                target_id TEXT NOT NULL, target_version TEXT NOT NULL,
                dependency_type TEXT NOT NULL,
                UNIQUE(source_id, source_version, target_id, target_version, dependency_type)
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
                resource_id TEXT NOT NULL, resource_kind TEXT NOT NULL,
                actor_type TEXT NOT NULL, actor_id TEXT NOT NULL, tenant_id TEXT,
                before_state TEXT, after_state TEXT, details TEXT, created_at TEXT NOT NULL
            );
            """
        )
        self._db.commit()
        self._load()

    async def get_audit_logs(
        self, resource_id: str = None, actor_id: str = None, limit: int = 100
    ) -> list[dict]:
        query = "SELECT * FROM audit_logs"
        conditions = []
        params = []
        if resource_id:
            conditions.append("resource_id = ?")
            params.append(resource_id)
        if actor_id:
            conditions.append("actor_id = ?")
            params.append(actor_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._db.execute(query, params).fetchall()
        logs = []
        for row in rows:
            item = {
                "id": row["id"],
                "action": row["action"],
                "resource_id": row["resource_id"],
                "resource_kind": row["resource_kind"],
                "actor_type": row["actor_type"],
                "actor_id": row["actor_id"],
                "tenant_id": row["tenant_id"],
                "before_state": json.loads(row["before_state"]) if row["before_state"] else None,
                "after_state": json.loads(row["after_state"]) if row["after_state"] else None,
                "details": json.loads(row["details"]) if row["details"] else None,
                "created_at": row["created_at"],
            }
            logs.append(item)
        return logs

    @asynccontextmanager
    async def transaction(self):
        outermost = self._transaction_depth == 0
        if outermost:
            self._db.execute("BEGIN")
        self._transaction_depth += 1
        try:
            yield self
            self._transaction_depth -= 1
            if outermost:
                self._db.commit()
        except Exception:
            self._transaction_depth = max(0, self._transaction_depth - 1)
            if outermost:
                self._db.rollback()
            raise

    def _commit_if_needed(self):
        if self._transaction_depth == 0:
            self._db.commit()

    @staticmethod
    def _j(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def _load(self):
        for row in self._db.execute("SELECT content FROM definitions"):
            obj = json.loads(row[0])
            self._objects[obj["metadata"]["id"]] = obj
        for row in self._db.execute("SELECT * FROM definition_versions ORDER BY rowid"):
            self._versions.setdefault(row["object_id"], []).append(
                {
                    "object_id": row["object_id"],
                    "version": row["version"],
                    "revision": row["revision"],
                    "content_digest": row["content_digest"],
                    "spec_snapshot": json.loads(row["spec_snapshot"]),
                    "created_at": row["created_at"],
                    "created_by": json.loads(row["created_by"]),
                }
            )
        for row in self._db.execute("SELECT * FROM definition_dependencies"):
            self._dependencies.append(dict(row))
        for row in self._db.execute("SELECT * FROM audit_logs ORDER BY id"):
            item = dict(row)
            for key in ("before_state", "after_state", "details"):
                item[key] = json.loads(item[key]) if item[key] else None
            self._audit_logs.append(item)

    async def create(self, obj: dict) -> str:
        result = await super().create(obj)
        try:
            meta = obj["metadata"]
            self._db.execute(
                "INSERT INTO definitions VALUES (?,?,?,?,?,?,?)",
                (
                    result,
                    meta["namespace"],
                    meta["key"],
                    meta["version"],
                    meta.get("revision", 1),
                    obj["kind"],
                    self._j(obj),
                ),
            )
            self._commit_if_needed()
        except Exception:
            self._db.rollback()
            self._objects.pop(result, None)
            raise
        return result

    async def update(self, id: str, expected_revision: int, updates: dict) -> bool:
        ok = await super().update(id, expected_revision, updates)
        if ok:
            obj = self._objects[id]
            meta = obj["metadata"]
            self._db.execute(
                "UPDATE definitions SET revision=?, content=? WHERE id=? AND revision=?",
                (meta["revision"], self._j(obj), id, expected_revision),
            )
            self._commit_if_needed()
        return ok

    async def delete(self, id: str) -> bool:
        ok = await super().delete(id)
        if ok:
            self._db.execute("DELETE FROM definitions WHERE id=?", (id,))
            self._commit_if_needed()
        return ok

    async def save_version(
        self, object_id, version, revision, content_digest, spec_snapshot, created_by
    ):
        await super().save_version(
            object_id, version, revision, content_digest, spec_snapshot, created_by
        )
        item = self._versions[object_id][-1]
        self._db.execute(
            "INSERT INTO definition_versions VALUES (?,?,?,?,?,?,?)",
            (
                object_id,
                version,
                revision,
                content_digest,
                self._j(spec_snapshot),
                item["created_at"],
                self._j(created_by),
            ),
        )
        self._commit_if_needed()

    async def save_dependency(
        self, source_id, source_version, target_id, target_version, dependency_type
    ):
        before = len(self._dependencies)
        await super().save_dependency(
            source_id, source_version, target_id, target_version, dependency_type
        )
        if len(self._dependencies) > before:
            self._db.execute(
                "INSERT OR IGNORE INTO definition_dependencies VALUES (?,?,?,?,?)",
                (source_id, source_version, target_id, target_version, dependency_type),
            )
            self._commit_if_needed()

    async def save_audit_log(
        self,
        action,
        resource_id,
        resource_kind,
        actor_type,
        actor_id,
        tenant_id=None,
        before_state=None,
        after_state=None,
        details=None,
    ):
        await super().save_audit_log(
            action,
            resource_id,
            resource_kind,
            actor_type,
            actor_id,
            tenant_id,
            before_state,
            after_state,
            details,
        )
        item = self._audit_logs[-1]
        self._db.execute(
            (
                "INSERT INTO audit_logs("
                "action,resource_id,resource_kind,actor_type,actor_id,tenant_id,"
                "before_state,after_state,details,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
            ),
            (
                action,
                resource_id,
                resource_kind,
                actor_type,
                actor_id,
                tenant_id,
                self._j(before_state) if before_state is not None else None,
                self._j(after_state) if after_state is not None else None,
                self._j(details or {}),
                item["created_at"],
            ),
        )
        self._commit_if_needed()

    def close(self):
        self._db.close()
