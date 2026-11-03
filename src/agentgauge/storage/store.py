"""SQLite-backed storage for runs and their case results."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from pydantic import BaseModel, ConfigDict, TypeAdapter

from agentgauge.core.models import CaseResult, ModelOutput, RunResult, Score
from agentgauge.storage.migrations import StorageError, migrate

_SCORES = TypeAdapter(tuple[Score, ...])


def _to_text(moment: datetime) -> str:
    """UTC ISO-8601 with fixed precision, so text order matches time order."""
    if moment.tzinfo is None:
        raise StorageError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


class RunSummary(BaseModel):
    """One row of a run listing: identity, timing and outcome counts."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    suite_name: str
    model: str
    started_at: datetime
    finished_at: datetime | None
    total_cases: int
    passed_cases: int
    errored_cases: int


class RunNotFoundError(StorageError):
    """No stored run matches the given id."""


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

    def list_runs(self, limit: int | None = None) -> list[RunSummary]:
        """Summaries of stored runs, newest first, optionally capped at ``limit``."""
        rows = self._conn.execute(
            "SELECT r.run_id, r.suite_name, r.model, r.started_at, r.finished_at, "
            "COUNT(c.position), COALESCE(SUM(c.passed), 0), "
            "COALESCE(SUM(c.error IS NOT NULL), 0) "
            "FROM runs r LEFT JOIN case_results c ON c.run_id = r.run_id "
            "GROUP BY r.run_id ORDER BY r.started_at DESC, r.run_id LIMIT ?",
            (-1 if limit is None else limit,),
        ).fetchall()
        return [
            RunSummary(
                run_id=run_id,
                suite_name=suite_name,
                model=model,
                started_at=datetime.fromisoformat(started),
                finished_at=datetime.fromisoformat(finished) if finished else None,
                total_cases=total,
                passed_cases=passed,
                errored_cases=errored,
            )
            for run_id, suite_name, model, started, finished, total, passed, errored in rows
        ]

    def get_run(self, run_id: str) -> RunResult:
        """Load a run by full id or by a unique id prefix.

        Raises :class:`RunNotFoundError` if nothing matches and
        :class:`StorageError` if the prefix is ambiguous.
        """
        escaped = run_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self._conn.execute(
            "SELECT run_id, suite_name, model, started_at, finished_at FROM runs "
            "WHERE run_id LIKE ? ESCAPE '\\' ORDER BY run_id LIMIT 2",
            (escaped + "%",),
        ).fetchall()
        if not run_id or not rows:
            raise RunNotFoundError(f"no run matches {run_id!r}")
        if len(rows) > 1:
            raise StorageError(f"run id prefix {run_id!r} is ambiguous; use more characters")
        full_id, suite_name, model, started, finished = rows[0]
        cases = self._conn.execute(
            "SELECT case_id, error, latency_ms, cost_usd, output_json, scores_json "
            "FROM case_results WHERE run_id = ? ORDER BY position",
            (full_id,),
        ).fetchall()
        return RunResult(
            run_id=full_id,
            suite_name=suite_name,
            model=model,
            started_at=datetime.fromisoformat(started),
            finished_at=datetime.fromisoformat(finished) if finished else None,
            results=tuple(
                CaseResult(
                    case_id=case_id,
                    output=ModelOutput.model_validate_json(output_json) if output_json else None,
                    scores=_SCORES.validate_json(scores_json),
                    error=error,
                    latency_ms=latency_ms,
                    cost_usd=cost_usd,
                )
                for case_id, error, latency_ms, cost_usd, output_json, scores_json in cases
            ),
        )


def _scores_json(scores: tuple[Score, ...]) -> str:
    return _SCORES.dump_json(scores).decode()
