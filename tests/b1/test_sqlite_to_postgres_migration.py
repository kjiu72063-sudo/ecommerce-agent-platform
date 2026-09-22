"""SQLite → PostgreSQL migration: safety checks and idempotent copy."""

import asyncio
import sqlite3

import pytest

from presale.migrate_sqlite_to_postgres import MigrationRefused, _upsert, migrate


def test_default_password_is_refused(tmp_path):
    database = tmp_path / "presale.sqlite3"
    sqlite3.connect(database).close()

    with pytest.raises(MigrationRefused):
        asyncio.run(
            migrate(
                sqlite_path=database,
                dsn="postgresql://presale:presale@127.0.0.1:5432/presale",
            )
        )


def test_evidence_upsert_keeps_source_row():
    statement = _upsert(
        "presale_evidence",
        ("run_ref", "tenant_id", "content", "source_row"),
        "(source_row)",
    )
    assert "DELETE" not in statement
    assert "ON CONFLICT (source_row)" in statement
    assert "$3::jsonb" in statement


def _seed(path):
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE presale_questions (
            id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE TABLE presale_evidence (
            run_ref TEXT NOT NULL, tenant_id TEXT NOT NULL, content TEXT NOT NULL
        );
        """
    )
    db.execute(
        "INSERT INTO presale_questions VALUES (?, ?, ?, ?)",
        ("question-1", "tenant-demo", "key-12345678", '{"question_id":"question-1"}'),
    )
    db.execute(
        "INSERT INTO presale_evidence VALUES (?, ?, ?)",
        ("run_1", "tenant-demo", '{"locator":"spec"}'),
    )
    db.commit()
    db.close()


class _Conn:
    def __init__(self):
        self.statements = []

    async def execute(self, statement, *args):
        self.statements.append((statement, args))

    def transaction(self):
        return _Transaction()


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_exc):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _Acquire(self.conn)


def test_migrate_replaces_rows_on_replay(tmp_path, monkeypatch):
    database = tmp_path / "presale.sqlite3"
    _seed(database)
    conn = _Conn()

    class _Store:
        def __init__(self, _dsn):
            self.pool = _Pool(conn)

        async def _ensure_init(self):
            return self.pool

        async def close(self):
            return None

    monkeypatch.setattr("presale.migrate_sqlite_to_postgres.PostgresPresaleStore", _Store)

    first = asyncio.run(
        migrate(
            sqlite_path=database,
            dsn="postgresql://presale:secret@127.0.0.1:5432/presale",
        )
    )
    asyncio.run(
        migrate(
            sqlite_path=database,
            dsn="postgresql://presale:secret@127.0.0.1:5432/presale",
        )
    )

    assert first["presale_questions"] == 1
    assert first["presale_evidence"] == 1
    evidence = [item for item in conn.statements if "presale_evidence" in item[0]]
    assert len(evidence) == 2
    assert evidence[0][1][-1] == evidence[1][1][-1]
    assert all("ON CONFLICT" in statement for statement, _args in conn.statements)
    assert not any(statement.startswith("DELETE") for statement, _args in conn.statements)
