"""The README's examples are executable claims; keep them true."""

import re
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from agentgauge.cli import app
from agentgauge.core import load_suite
from agentgauge.scorers import available_scorers, create_scorer
from agentgauge.storage import RunStore

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text()
runner = CliRunner(env={"COLUMNS": "200"})


def fenced(language: str) -> list[str]:
    return re.findall(rf"```{language}\n(.*?)```", README, flags=re.DOTALL)


def test_quickstart_command_points_at_the_shipped_example() -> None:
    commands = "\n".join(fenced("bash"))
    assert "uv run agentgauge run examples/basic/suite.yaml" in commands
    assert (ROOT / "examples" / "basic" / "suite.yaml").is_file()


def test_suite_example_in_the_readme_is_valid(tmp_path: Path) -> None:
    (yaml_block,) = fenced("yaml")
    path = tmp_path / "readme-suite.yaml"
    path.write_text(yaml_block)
    suite = load_suite(path)
    assert suite.provider is not None and suite.provider.api_key_env == "MY_API_KEY"
    assert [create_scorer(spec).name for spec in suite.scorers] == [
        "exact_match",
        "numeric_tolerance",
    ]


def test_every_scorer_in_the_readme_table_is_registered() -> None:
    names = re.findall(r"^\| `(\w+)` \|", README, flags=re.MULTILINE)
    assert sorted(names) == [
        "contains",
        "exact_match",
        "json_schema",
        "llm_judge",
        "numeric_tolerance",
        "regex",
        "tool_call",
        "trajectory_budget",
        "trajectory_match",
    ]
    needs_params = {"json_schema", "llm_judge", "trajectory_budget"}
    assert needs_params <= set(available_scorers())
    for name in names:
        if name not in needs_params:
            create_scorer(name)


@respx.mock
def test_example_can_be_pointed_at_a_real_model_as_the_readme_says(tmp_path: Path) -> None:
    body = {"choices": [{"message": {"role": "assistant", "content": "4"}}], "usage": {}}
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=body)
    )
    suite = ROOT / "examples" / "basic" / "suite.yaml"
    result = runner.invoke(
        app,
        [
            "run",
            str(suite),
            "--provider",
            "openai_compat",
            "--model",
            "some-model",
            "--db",
            str(tmp_path / "runs.db"),
        ],
        env={"OPENAI_API_KEY": "sk-test", "COLUMNS": "200"},
    )
    assert result.exit_code == 0, result.output
    assert route.call_count == 4
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-test"
    assert "model some-model" in result.output
    with RunStore(tmp_path / "runs.db") as store:
        assert store.list_runs()[0].model == "some-model"
