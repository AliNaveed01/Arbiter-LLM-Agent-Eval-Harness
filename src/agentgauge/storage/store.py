"""SQLite-backed storage for runs and their case results."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import TypeAdapter

from agentgauge.core.models import RunResult, Score
from agentgauge.storage.migrations import StorageError, migrate

_SCORES = TypeAdapter(tuple[Score, ...])


def _to_text(moment: datetime) -> str:
    """UTC ISO-8601 with fixed precision, so text order matches time order."""
    if moment.tzinfo is None:
        raise StorageError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


class RunStore:
    """Persists :class:`RunResult` objects in a SQLite file (or in memory).

    Opening the store creates the file and parent directories if needed and
    applies any pending schema migrations.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(path)
            self._conn.execute("PRAGMA foreign_keys = ON")
            migrate(self._conn)
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open run store at {path}: {exc}") from exc

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def save_run(self, run: RunResult) -> None:
        """Store ``run`` and all its case results atomically."""
        started = _to_text(run.started_at)
        finished = _to_text(run.finished_at) if run.finished_at else None
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO runs (run_id, suite_name, model, started_at, finished_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (run.run_id, run.suite_name, run.model, started, finished),
                )
                self._conn.executemany(
                    "INSERT INTO case_results (run_id, position, case_id, passed, error, "
                    "latency_ms, cost_usd, output_json, scores_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            run.run_id,
                            position,
                            result.case_id,
                            int(result.passed),
                            result.error,
                            result.latency_ms,
                            result.cost_usd,
                            result.output.model_dump_json() if result.output else None,
                            _scores_json(result.scores),
                        )
                        for position, result in enumerate(run.results)
                    ],
                )
        except sqlite3.IntegrityError as exc:
            raise StorageError(f"run {run.run_id} is already stored") from exc


def _scores_json(scores: tuple[Score, ...]) -> str:
    return _SCORES.dump_json(scores).decode()
