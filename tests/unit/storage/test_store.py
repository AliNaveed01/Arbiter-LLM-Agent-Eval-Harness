import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from agentgauge.core import (
    CaseResult,
    Message,
    ModelOutput,
    RunResult,
    Score,
    ToolCall,
    Trajectory,
)
from agentgauge.storage import RunNotFoundError, RunStore, StorageError
from agentgauge.storage.migrations import MIGRATIONS, migrate, schema_version

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def passing(case_id: str) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        output=ModelOutput(
            text="4",
            latency_ms=12.5,
            prompt_tokens=5,
            completion_tokens=1,
            cost_usd=0.001,
            tool_calls=(ToolCall(id="t1", name="calc", arguments='{"x": 2}'),),
            raw={"id": "resp-1"},
        ),
        scores=(
            Score(scorer="exact_match", value=1.0, passed=True),
            Score(scorer="contains", value=1.0, passed=True, reason=None),
        ),
        latency_ms=20.0,
        cost_usd=0.001,
    )


def failing(case_id: str) -> CaseResult:
    output = ModelOutput(text="5", latency_ms=1.0)
    score = Score(scorer="exact_match", value=0.0, passed=False, reason="expected '4'")
    return CaseResult(case_id=case_id, output=output, scores=(score,), latency_ms=2.0)


def errored(case_id: str) -> CaseResult:
    return CaseResult(case_id=case_id, error="TimeoutError: slow", latency_ms=30000.0)


def make_run(
    run_id: str = "r1",
    started: datetime = T0,
    results: tuple[CaseResult, ...] | None = None,
) -> RunResult:
    return RunResult(
        run_id=run_id,
        suite_name="basic",
        model="fake",
        started_at=started,
        finished_at=started + timedelta(seconds=3),
        results=(passing("a"), failing("b"), errored("c")) if results is None else results,
    )


@pytest.fixture
def store() -> RunStore:
    return RunStore()


def test_round_trip_preserves_everything(store: RunStore) -> None:
    run = make_run()
    store.save_run(run)
    assert store.get_run("r1") == run


def test_case_order_is_preserved(store: RunStore) -> None:
    run = make_run(results=tuple(passing(f"c{i}") for i in (3, 1, 2, 0)))
    store.save_run(run)
    assert [r.case_id for r in store.get_run("r1").results] == ["c3", "c1", "c2", "c0"]


def test_unfinished_run_and_empty_run_round_trip(store: RunStore) -> None:
    run = make_run(results=()).model_copy(update={"finished_at": None})
    store.save_run(run)
    assert store.get_run("r1") == run


def test_data_survives_reopening_the_file(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    with RunStore(path) as first:
        first.save_run(make_run())
    with RunStore(path) as second:
        assert second.get_run("r1") == make_run()


def test_parent_directories_are_created(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "runs.db"
    with RunStore(path) as store:
        store.save_run(make_run())
    assert path.exists()


def test_opening_applies_migrations(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    RunStore(path).close()
    assert schema_version(sqlite3.connect(path)) >= 1


def test_timestamps_round_trip_as_utc_instants(store: RunStore) -> None:
    plus_five = timezone(timedelta(hours=5))
    run = make_run(started=datetime(2026, 11, 3, 17, 0, tzinfo=plus_five))
    store.save_run(run)
    loaded = store.get_run("r1")
    assert loaded.started_at == run.started_at
    assert loaded.started_at.utcoffset() == timedelta(0)


def test_naive_timestamps_are_rejected(store: RunStore) -> None:
    with pytest.raises(StorageError, match="timezone-aware"):
        store.save_run(make_run(started=datetime(2026, 11, 3, 12, 0)))
    assert store.list_runs() == []


def test_saving_the_same_run_twice_fails_and_keeps_the_original(store: RunStore) -> None:
    store.save_run(make_run())
    with pytest.raises(StorageError, match="already stored"):
        store.save_run(make_run(results=(passing("only"),)))
    assert store.get_run("r1") == make_run()


def test_failure_while_saving_rolls_back_the_whole_run(
    store: RunStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(self: ModelOutput, **kwargs: object) -> str:
        raise RuntimeError("cannot serialise")

    monkeypatch.setattr(ModelOutput, "model_dump_json", explode)
    with pytest.raises(RuntimeError, match="cannot serialise"):
        store.save_run(make_run())  # the runs row is inserted before the cases fail
    monkeypatch.undo()
    assert store.list_runs() == []
    store.save_run(make_run())  # the id is free again
    assert store.get_run("r1") == make_run()


def test_list_runs_is_newest_first_with_outcome_counts(store: RunStore) -> None:
    store.save_run(make_run("old", T0))
    store.save_run(make_run("new", T0 + timedelta(hours=1), results=(passing("a"),)))
    store.save_run(make_run("empty", T0 + timedelta(minutes=30), results=()))
    summaries = store.list_runs()
    assert [s.run_id for s in summaries] == ["new", "empty", "old"]
    old = summaries[2]
    assert (old.total_cases, old.passed_cases, old.errored_cases) == (3, 1, 1)
    assert (old.suite_name, old.model, old.started_at) == ("basic", "fake", T0)
    assert old.finished_at == T0 + timedelta(seconds=3)
    empty = summaries[1]
    assert (empty.total_cases, empty.passed_cases, empty.errored_cases) == (0, 0, 0)


def test_list_runs_limit_and_empty_store(store: RunStore) -> None:
    assert store.list_runs() == []
    for i in range(5):
        store.save_run(make_run(f"r{i}", T0 + timedelta(minutes=i)))
    assert [s.run_id for s in store.list_runs(limit=2)] == ["r4", "r3"]
    assert len(store.list_runs()) == 5


def test_list_runs_orders_by_instant_not_by_text(store: RunStore) -> None:
    whole_second = T0
    with_micros = T0 + timedelta(microseconds=5)
    store.save_run(make_run("a", with_micros))
    store.save_run(make_run("b", whole_second))
    assert [s.run_id for s in store.list_runs()] == ["a", "b"]


def test_unfinished_run_listing(store: RunStore) -> None:
    store.save_run(make_run(results=()).model_copy(update={"finished_at": None}))
    assert store.list_runs()[0].finished_at is None


def test_get_run_accepts_a_unique_prefix(store: RunStore) -> None:
    store.save_run(make_run("abc123"))
    store.save_run(make_run("abd456"))
    assert store.get_run("abc").run_id == "abc123"
    assert store.get_run("abd456").run_id == "abd456"


def test_ambiguous_prefix_is_an_error(store: RunStore) -> None:
    store.save_run(make_run("abc123"))
    store.save_run(make_run("abc456"))
    with pytest.raises(StorageError, match="ambiguous"):
        store.get_run("abc")


@pytest.mark.parametrize("missing", ["zzz", "", "abc1234"])
def test_unknown_or_empty_id_is_not_found(store: RunStore, missing: str) -> None:
    store.save_run(make_run("abc123"))
    with pytest.raises(RunNotFoundError, match="no run matches"):
        store.get_run(missing)


@pytest.mark.parametrize("wildcard", ["%", "_", "a%", "a_c", "\\"])
def test_like_wildcards_are_matched_literally(store: RunStore, wildcard: str) -> None:
    store.save_run(make_run("abc123"))
    with pytest.raises(RunNotFoundError):
        store.get_run(wildcard)


def test_run_not_found_is_a_storage_error() -> None:
    assert issubclass(RunNotFoundError, StorageError)


def test_context_manager_closes_the_connection() -> None:
    with RunStore() as store:
        pass
    with pytest.raises(sqlite3.ProgrammingError):
        store.list_runs()


def test_database_from_a_newer_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    RunStore(path).close()
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO schema_migrations VALUES (999, '2030-01-01T00:00:00+00:00')")
    conn.commit()
    conn.close()
    with pytest.raises(StorageError, match="newer than this agentgauge supports"):
        RunStore(path)


def test_unopenable_path_is_a_storage_error(tmp_path: Path) -> None:
    with pytest.raises(StorageError, match="cannot open run store"):
        RunStore(tmp_path)  # a directory, not a database file


class SpyConnection:
    """Wraps a real connection and records whether it was closed."""

    def __init__(self, real: sqlite3.Connection) -> None:
        self._real = real
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self._real.close()

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def test_connection_is_closed_when_opening_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "runs.db"
    RunStore(path).close()
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO schema_migrations VALUES (999, '2030-01-01T00:00:00+00:00')")
    conn.commit()
    conn.close()

    spies: list[SpyConnection] = []
    real_connect = sqlite3.connect

    def spying_connect(*args: object, **kwargs: object) -> SpyConnection:
        spy = SpyConnection(real_connect(*args, **kwargs))  # pyright: ignore[reportArgumentType, reportCallIssue]
        spies.append(spy)
        return spy

    monkeypatch.setattr(sqlite3, "connect", spying_connect)
    with pytest.raises(StorageError):
        RunStore(path)
    assert [spy.closed for spy in spies] == [True]


def test_connection_is_closed_on_sqlite_errors_while_opening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spies: list[SpyConnection] = []
    real_connect = sqlite3.connect

    def spying_connect(*args: object, **kwargs: object) -> SpyConnection:
        spy = SpyConnection(real_connect(*args, **kwargs))  # pyright: ignore[reportArgumentType, reportCallIssue]
        spies.append(spy)
        return spy

    monkeypatch.setattr(sqlite3, "connect", spying_connect)
    monkeypatch.setattr(
        "agentgauge.storage.store.migrate",
        lambda conn: (_ for _ in ()).throw(sqlite3.OperationalError("disk I/O error")),
    )
    with pytest.raises(StorageError, match="disk I/O error"):
        RunStore(tmp_path / "runs.db")
    assert [spy.closed for spy in spies] == [True]


def test_score_details_round_trip_through_the_store(store: RunStore) -> None:
    score = Score(scorer="llm_judge", value=4.0, passed=True, details={"raw_output": '{"a": 1}'})
    run = RunResult(
        run_id="d1",
        suite_name="s",
        model="m",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=(CaseResult(case_id="c", scores=(score,)),),
    )
    store.save_run(run)
    assert store.get_run("d1").results[0].scores[0].details == {"raw_output": '{"a": 1}'}


def _agent_output() -> ModelOutput:
    call = ToolCall(id="1", name="search", arguments='{"q": "cats"}')
    return ModelOutput(
        text="found",
        latency_ms=12.0,
        trajectory=Trajectory(
            messages=(
                Message(role="assistant", content="", tool_calls=(call,)),
                Message(role="tool", content="3 results", tool_call_id="1"),
                Message(role="assistant", content="found"),
            ),
            stop_reason="final",
        ),
    )


def test_trajectories_round_trip_and_live_in_their_own_column(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    output = _agent_output()
    run = RunResult(
        run_id="t1",
        suite_name="s",
        model="m",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        results=(
            CaseResult(case_id="agent", output=output),
            CaseResult(case_id="plain", output=ModelOutput(text="x", latency_ms=1.0)),
            CaseResult(case_id="failed", error="boom"),
        ),
    )
    with RunStore(path) as store:
        store.save_run(run)
        assert store.get_run("t1") == run
    conn = sqlite3.connect(path)
    rows = {
        case_id: (output_json, trajectory_json)
        for case_id, output_json, trajectory_json in conn.execute(
            "SELECT case_id, output_json, trajectory_json FROM case_results"
        )
    }
    assert "trajectory" not in rows["agent"][0] and rows["agent"][1] is not None
    assert rows["plain"][1] is None and rows["failed"] == (None, None)


def test_a_database_created_before_migration_two_still_opens(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    migrate(conn, MIGRATIONS[:1])
    conn.execute(
        "INSERT INTO runs VALUES ('old1', 's', 'm', '2026-01-01T00:00:00.000000+00:00', NULL)"
    )
    conn.execute(
        "INSERT INTO case_results (run_id, position, case_id, passed, error, latency_ms, "
        "cost_usd, output_json, scores_json) VALUES "
        "('old1', 0, 'c', 1, NULL, 1.0, NULL, "
        '\'{"text": "hi", "latency_ms": 1.0}\', \'[]\')'
    )
    conn.commit()
    assert schema_version(conn) == 1
    conn.close()

    with RunStore(path) as store:
        old = store.get_run("old1")
        assert old.results[0].output is not None and old.results[0].output.trajectory is None
        store.save_run(
            RunResult(
                run_id="new1",
                suite_name="s",
                model="m",
                started_at=datetime(2026, 1, 2, tzinfo=UTC),
                results=(CaseResult(case_id="a", output=_agent_output()),),
            )
        )
        assert store.get_run("new1").results[0].output == _agent_output()
    assert schema_version(sqlite3.connect(path)) == 2
