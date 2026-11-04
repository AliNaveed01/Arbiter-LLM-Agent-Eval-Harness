from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.core import RunResult
from agentgauge.storage import RunStore

runner = CliRunner(env={"COLUMNS": "200"})

FAKE_SUITE = """\
name: arithmetic
provider:
  type: fake
  model: scripted
  responses:
    "2+2?": "4"
    "3+3?": "7"
scorers: [exact_match]
cases:
  - {id: add, input: "2+2?", expected: "4"}
  - {id: wrong, input: "3+3?", expected: "6"}
"""


def write(tmp_path: Path, text: str, name: str = "suite.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def invoke(tmp_path: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["run", *args, "--db", str(tmp_path / "runs.db")])
    return result.exit_code, result.output


def stored_runs(tmp_path: Path) -> int:
    with RunStore(tmp_path / "runs.db") as store:
        return len(store.list_runs())


def test_runs_a_suite_with_its_own_provider_and_stores_the_run(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)))
    assert code == 0, output
    assert "suite arithmetic  model scripted" in output
    assert "PASS" in output and "FAIL" in output
    assert "exact_match: expected '6'" in output
    assert "1/2 passed, 1 failed, 0 errors" in output
    assert "Stored as run" in output
    with RunStore(tmp_path / "runs.db") as store:
        (summary,) = store.list_runs()
        assert output.count(summary.run_id[:8]) == 2
        assert (summary.total_cases, summary.passed_cases) == (2, 1)


def test_failing_scores_do_not_change_the_exit_code(tmp_path: Path) -> None:
    code, _ = invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)))
    assert code == 0


def test_provider_errors_are_reported_per_case_with_exit_zero(tmp_path: Path) -> None:
    suite = FAKE_SUITE.replace('"3+3?": "7"', '"other": "x"')
    code, output = invoke(tmp_path, str(write(tmp_path, suite)))
    assert code == 0
    assert "ERROR" in output and "KeyError" in output
    assert "1/2 passed, 0 failed, 1 errors" in output


def test_model_option_overrides_the_suite(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)), "--model", "renamed")
    assert code == 0
    assert "model renamed" in output


def test_suite_without_provider_needs_options(tmp_path: Path) -> None:
    suite = write(tmp_path, '{"id": "a", "input": "q", "expected": "x"}\n', "cases.jsonl")
    code, output = invoke(tmp_path, str(suite))
    assert code == 2
    assert "error: no provider configured" in output
    assert stored_runs(tmp_path) == 0


def test_fake_provider_can_be_chosen_on_the_command_line(tmp_path: Path) -> None:
    suite = write(tmp_path, '{"id": "a", "input": "q", "expected": "x"}\n', "cases.jsonl")
    code, output = invoke(tmp_path, str(suite), "--provider", "fake")
    assert code == 0
    assert "model fake" in output and "KeyError" in output


@respx.mock
def test_openai_compatible_endpoint_via_options(tmp_path: Path) -> None:
    body = {"choices": [{"message": {"role": "assistant", "content": "x"}}], "usage": {}}
    route = respx.post("http://llm.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=body)
    )
    suite = write(
        tmp_path,
        '{"id": "a", "input": "q", "expected": "x"}\n{"id": "b", "input": "r"}\n',
        "cases.jsonl",
    )
    code, output = invoke(
        tmp_path,
        str(suite),
        "--model",
        "gpt-x",
        "--base-url",
        "http://llm.test/v1",
        "--concurrency",
        "2",
    )
    assert code == 0, output
    assert route.call_count == 2
    assert "model gpt-x" in output
    assert stored_runs(tmp_path) == 1


def test_missing_suite_file_is_a_config_error(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, str(tmp_path / "nope.yaml"))
    assert code == 2
    assert "error:" in output and "nope.yaml" in output and "cannot read file" in output


def test_invalid_suite_reports_file_and_line(tmp_path: Path) -> None:
    suite = write(tmp_path, "name: s\ncases:\n  - id: a\n")
    code, output = invoke(tmp_path, str(suite))
    assert code == 2
    assert f"{suite}:3:" in output.replace("\n", "")


def test_unknown_scorer_is_a_config_error_and_nothing_is_stored(tmp_path: Path) -> None:
    suite = write(tmp_path, FAKE_SUITE.replace("[exact_match]", "[nope]"))
    code, output = invoke(tmp_path, str(suite))
    assert code == 2
    assert "unknown scorer 'nope'" in output
    assert stored_runs(tmp_path) == 0


def test_invalid_provider_type_is_a_config_error(tmp_path: Path) -> None:
    code, output = invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)), "--provider", "pigeon")
    assert code == 2
    assert "invalid provider options" in output


def test_openai_compat_without_a_model_is_a_config_error(tmp_path: Path) -> None:
    suite = write(tmp_path, '{"id": "a", "input": "q"}\n', "cases.jsonl")
    code, output = invoke(tmp_path, str(suite), "--provider", "openai_compat")
    assert code == 2
    assert "needs a model" in output


def test_missing_api_key_variable_is_a_config_error(tmp_path: Path) -> None:
    suite = write(tmp_path, '{"id": "a", "input": "q"}\n', "cases.jsonl")
    code, output = invoke(tmp_path, str(suite), "--model", "m", "--api-key-env", "AG_NO_SUCH_KEY")
    assert code == 2
    assert "AG_NO_SUCH_KEY is not set" in output
    assert stored_runs(tmp_path) == 0


def test_unusable_database_is_a_config_error(tmp_path: Path) -> None:
    suite = write(tmp_path, FAKE_SUITE)
    result = runner.invoke(app, ["run", str(suite), "--db", str(tmp_path)])
    assert result.exit_code == 2
    assert "cannot open run store" in result.output


def test_concurrency_must_be_positive(tmp_path: Path) -> None:
    code, _ = invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)), "--concurrency", "0")
    assert code == 2


def test_database_path_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "from-env.db"
    monkeypatch.setenv("AGENTGAUGE_DB", str(db))
    result = runner.invoke(app, ["run", str(write(tmp_path, FAKE_SUITE))])
    assert result.exit_code == 0
    with RunStore(db) as store:
        assert len(store.list_runs()) == 1


def test_default_database_is_under_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTGAUGE_DB", raising=False)
    result = runner.invoke(app, ["run", str(write(tmp_path, FAKE_SUITE))])
    assert result.exit_code == 0
    assert (tmp_path / ".agentgauge" / "runs.db").exists()


def list_runs(tmp_path: Path, *args: str) -> tuple[int, str]:
    result = runner.invoke(app, ["runs", "list", "--db", str(tmp_path / "runs.db"), *args])
    return result.exit_code, result.output


def test_runs_list_shows_stored_runs_newest_first(tmp_path: Path) -> None:
    suite = str(write(tmp_path, FAKE_SUITE))
    invoke(tmp_path, suite)
    invoke(tmp_path, suite, "--model", "second")
    code, output = list_runs(tmp_path)
    assert code == 0
    assert output.index("second") < output.index("scripted")
    assert "arithmetic" in output
    assert "UTC" in output


def test_runs_list_limit(tmp_path: Path) -> None:
    suite = str(write(tmp_path, FAKE_SUITE))
    for name in ("first", "second", "third"):
        invoke(tmp_path, suite, "--model", name)
    code, output = list_runs(tmp_path, "--limit", "2")
    assert code == 0
    assert "third" in output and "second" in output and "first" not in output


def test_runs_list_on_an_empty_database(tmp_path: Path) -> None:
    code, output = list_runs(tmp_path)
    assert code == 0
    assert "No runs stored yet" in output


def test_runs_list_with_an_unusable_database_is_a_config_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["runs", "list", "--db", str(tmp_path)])
    assert result.exit_code == 2
    assert "cannot open run store" in result.output


def test_runs_list_limit_must_be_positive(tmp_path: Path) -> None:
    assert list_runs(tmp_path, "--limit", "0")[0] == 2


def test_runs_without_a_subcommand_shows_help() -> None:
    result = runner.invoke(app, ["runs"])
    assert "list" in result.output


def show(tmp_path: Path, run_id: str) -> tuple[int, str]:
    result = runner.invoke(app, ["runs", "show", run_id, "--db", str(tmp_path / "runs.db")])
    return result.exit_code, result.output


def stored_id(tmp_path: Path) -> str:
    with RunStore(tmp_path / "runs.db") as store:
        return store.list_runs()[0].run_id


def test_runs_show_prints_the_run_with_outputs(tmp_path: Path) -> None:
    invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)))
    code, output = show(tmp_path, stored_id(tmp_path))
    assert code == 0
    assert "suite arithmetic  model scripted" in output
    assert "Output" in output
    assert "exact_match=pass" in output and "exact_match=fail" in output
    assert "exact_match: expected '6'" in output
    assert "1/2 passed" in output


def test_runs_show_accepts_a_prefix(tmp_path: Path) -> None:
    invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)))
    run_id = stored_id(tmp_path)
    code, output = show(tmp_path, run_id[:8])
    assert code == 0
    assert run_id[:8] in output


def test_runs_show_unknown_id_exits_1(tmp_path: Path) -> None:
    invoke(tmp_path, str(write(tmp_path, FAKE_SUITE)))
    code, output = show(tmp_path, "zzzz")
    assert code == 1
    assert "error: no run matches 'zzzz'" in output


def test_runs_show_ambiguous_prefix_exits_1(tmp_path: Path) -> None:
    started = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    with RunStore(tmp_path / "runs.db") as store:
        for run_id in ("abc111", "abc222"):
            store.save_run(RunResult(run_id=run_id, suite_name="s", model="m", started_at=started))
    code, output = show(tmp_path, "abc")
    assert code == 1
    assert "ambiguous" in output
    assert show(tmp_path, "abc1")[0] == 0


def test_runs_show_with_an_unusable_database_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["runs", "show", "abc", "--db", str(tmp_path)])
    assert result.exit_code == 2
    assert "cannot open run store" in result.output
