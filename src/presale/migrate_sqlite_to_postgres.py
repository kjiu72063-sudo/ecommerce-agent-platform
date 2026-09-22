"""Copy the presale SQLite database into the PostgreSQL adapters.

Only the six presale tables move. B1 registry and B2 runtime databases are
separate files and are intentionally left untouched. Re-running replaces rows
by primary key, so a partial copy can be resumed.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .adapters.postgres import PostgresPresaleStore

_TABLES = (
    (
        "presale_questions",
        ("id", "tenant_id", "idempotency_key", "content"),
        "(tenant_id, idempotency_key)",
    ),
    (
        "presale_idempotency",
        ("tenant_id", "idempotency_key", "content"),
        "(tenant_id, idempotency_key)",
    ),
    (
        "presale_evidence",
        ("run_ref", "tenant_id", "content", "source_row"),
        "(source_row)",
    ),
    (
        "presale_answers",
        ("run_ref", "tenant_id", "content"),
        "(run_ref)",
    ),
    (
        "presale_dispositions",
        ("answer_id", "tenant_id", "content"),
        "(answer_id)",
    ),
    (
        "presale_traces",
        ("run_ref", "tenant_id", "content"),
        "(run_ref)",
    ),
)


class MigrationRefused(RuntimeError):
    """The target is not safe to write with the requested options."""


def _password(dsn: str) -> str:
    return unquote(urlparse(dsn).password or "")


def _read_rows(connection: sqlite3.Connection, table: str, columns: tuple[str, ...]) -> list[dict]:
    payload = tuple(column for column in columns if column != "source_row")
    names = ", ".join(payload)
    rowid = ", rowid AS source_row" if "source_row" in columns else ""
    try:
        found = connection.execute(f"SELECT {names}{rowid} FROM {table}").fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return []
        raise
    return [{column: row[column] for column in columns} for row in found]


def _upsert(table: str, columns: tuple[str, ...], conflict: str | None) -> str:
    names = ", ".join(columns)
    content_at = columns.index("content") + 1
    values = ", ".join(
        f"${index}::jsonb" if index == content_at else f"${index}"
        for index in range(1, len(columns) + 1)
    )
    statement = f"INSERT INTO {table} ({names}) VALUES ({values})"
    if conflict is None:
        return statement
    assignments = ", ".join(
        f"{column} = EXCLUDED.{column}" for column in columns if column not in conflict
    )
    # content is the only mutable payload; key columns stay in the conflict target.
    if not assignments:
        assignments = "content = EXCLUDED.content"
    return f"{statement} ON CONFLICT {conflict} DO UPDATE SET {assignments}"


async def migrate(
    *,
    sqlite_path: str | Path,
    dsn: str,
    allow_default_password: bool = False,
) -> dict[str, int]:
    """Copy every presale row. Returns the number of rows written per table."""
    if _password(dsn) == "presale" and not allow_default_password:
        raise MigrationRefused(
            "target uses the default presale password; pass --allow-default-password "
            "only for a local development database"
        )
    source = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    store = PostgresPresaleStore(dsn)
    counts: dict[str, int] = {}
    try:
        pool = await store._ensure_init()
        async with pool.acquire() as conn:
            for table, columns, conflict in _TABLES:
                rows = _read_rows(source, table, columns)
                statement = _upsert(table, columns, conflict)
                async with conn.transaction():
                    for row in rows:
                        await conn.execute(statement, *[row[column] for column in columns])
                counts[table] = len(rows)
    finally:
        source.close()
        await store.close()
    return counts


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="presale-migrate-pg",
        description="Copy the six presale SQLite tables into PostgreSQL.",
    )
    parser.add_argument("--sqlite", required=True, help="source presale SQLite file")
    parser.add_argument("--dsn", required=True, help="target PostgreSQL DSN")
    parser.add_argument(
        "--allow-default-password",
        action="store_true",
        help="allow the local development password 'presale'",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    counts: dict[str, Any] = asyncio.run(
        migrate(
            sqlite_path=args.sqlite,
            dsn=args.dsn,
            allow_default_password=args.allow_default_password,
        )
    )
    for table, count in counts.items():
        print(f"{table} {count}")


if __name__ == "__main__":
    main()
