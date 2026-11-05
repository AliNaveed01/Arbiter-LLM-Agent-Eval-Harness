"""Schema versioning: ordered migrations tracked in a ``schema_migrations`` table."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

Migration = tuple[int, str]

_INITIAL_SCHEMA = """
CREATE TABLE runs (
    run_id      TEXT PRIMARY KEY,
    suite_name  TEXT NOT NULL,
    model       TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE case_results (
    run_id      TEXT    NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    case_id     TEXT    NOT NULL,
    passed      INTEGER NOT NULL,
    error       TEXT,
    latency_ms  REAL,
    cost_usd    REAL,
    output_json TEXT,
    scores_json TEXT    NOT NULL,
    PRIMARY KEY (run_id, position)
);

CREATE INDEX idx_runs_started_at ON runs (started_at);
"""

_ADD_TRAJECTORY = """
ALTER TABLE case_results ADD COLUMN trajectory_json TEXT;
"""

MIGRATIONS: tuple[Migration, ...] = ((1, _INITIAL_SCHEMA), (2, _ADD_TRAJECTORY))


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
