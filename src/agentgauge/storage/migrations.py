"""Schema versioning: ordered migrations tracked in a ``schema_migrations`` table."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

Migration = tuple[int, str]

MIGRATIONS: tuple[Migration, ...] = ()


class StorageError(Exception):
    """The run store could not complete an operation."""


def schema_version(conn: sqlite3.Connection) -> int:
    """The highest applied migration version, or 0 for a fresh database."""
    _ensure_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection, migrations: tuple[Migration, ...] = MIGRATIONS) -> None:
    """Apply every migration newer than the database's version, each atomically.

    Raises :class:`StorageError` if the database is newer than ``migrations``
    knows about, so an old agentgauge never writes to a schema it doesn't understand.
    """
    versions = [version for version, _ in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise ValueError("migration versions must be 1, 2, 3, ... in order")
    current = schema_version(conn)
    if current > len(migrations):
        raise StorageError(
            f"database schema version {current} is newer than this agentgauge supports "
            f"({len(migrations)}); upgrade agentgauge"
        )
    for version, script in migrations[current:]:
        applied_at = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            conn.executescript(
                f"BEGIN;\n{script}\n"
                f"INSERT INTO schema_migrations (version, applied_at) "
                f"VALUES ({version}, '{applied_at}');\nCOMMIT;"
            )
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.rollback()
            raise StorageError(f"migration {version} failed: {exc}") from exc


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.commit()
