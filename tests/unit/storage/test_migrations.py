import sqlite3

import pytest

from agentgauge.storage.migrations import MIGRATIONS, StorageError, migrate, schema_version


@pytest.fixture
def conn() -> sqlite3.Connection:
    return sqlite3.connect(":memory:")


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def test_fresh_database_is_version_zero(conn: sqlite3.Connection) -> None:
    assert schema_version(conn) == 0


def test_migrate_creates_schema_and_records_version(conn: sqlite3.Connection) -> None:
    migrate(conn)
    assert {"runs", "case_results", "schema_migrations"} <= tables(conn)
    assert schema_version(conn) == len(MIGRATIONS)
    applied = conn.execute("SELECT version, applied_at FROM schema_migrations").fetchall()
    assert [v for v, _ in applied] == list(range(1, len(MIGRATIONS) + 1))
    assert all(ts.endswith("+00:00") for _, ts in applied)


def test_migrate_is_idempotent(conn: sqlite3.Connection) -> None:
    migrate(conn)
    migrate(conn)
    assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(MIGRATIONS)


def test_only_pending_migrations_are_applied(conn: sqlite3.Connection) -> None:
    one = ((1, "CREATE TABLE a (x INTEGER);"),)
    two = (*one, (2, "CREATE TABLE b (y INTEGER);"))
    migrate(conn, one)
    conn.execute("INSERT INTO a VALUES (7)")
    conn.commit()
    migrate(conn, two)
    assert {"a", "b"} <= tables(conn)
    assert conn.execute("SELECT x FROM a").fetchall() == [(7,)]
    assert schema_version(conn) == 2


def test_failed_migration_rolls_back_and_reports(conn: sqlite3.Connection) -> None:
    good = ((1, "CREATE TABLE a (x INTEGER);"),)
    migrate(conn, good)
    bad = (*good, (2, "CREATE TABLE b (y INTEGER);\nTHIS IS NOT SQL;"))
    with pytest.raises(StorageError, match="migration 2 failed"):
        migrate(conn, bad)
    assert "b" not in tables(conn)
    assert schema_version(conn) == 1
    assert not conn.in_transaction


def test_database_newer_than_code_is_refused(conn: sqlite3.Connection) -> None:
    migrate(conn, ((1, "CREATE TABLE a (x INTEGER);"), (2, "CREATE TABLE b (y INTEGER);")))
    with pytest.raises(StorageError, match="newer than this agentgauge supports"):
        migrate(conn, ((1, "CREATE TABLE a (x INTEGER);"),))


@pytest.mark.parametrize(
    "migrations",
    [
        ((2, "SELECT 1;"),),
        ((1, "SELECT 1;"), (3, "SELECT 1;")),
        ((1, "SELECT 1;"), (1, "SELECT 1;")),
    ],
)
def test_migration_versions_must_be_sequential(
    conn: sqlite3.Connection, migrations: tuple[tuple[int, str], ...]
) -> None:
    with pytest.raises(ValueError, match="in order"):
        migrate(conn, migrations)


def test_case_results_cascade_when_a_run_is_deleted(conn: sqlite3.Connection) -> None:
    migrate(conn)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("INSERT INTO runs VALUES ('r', 's', 'm', '2026-01-01T00:00:00+00:00', NULL)")
    conn.execute(
        "INSERT INTO case_results (run_id, position, case_id, passed, scores_json) "
        "VALUES ('r', 0, 'c', 1, '[]')"
    )
    conn.execute("DELETE FROM runs WHERE run_id = 'r'")
    assert conn.execute("SELECT COUNT(*) FROM case_results").fetchone()[0] == 0
