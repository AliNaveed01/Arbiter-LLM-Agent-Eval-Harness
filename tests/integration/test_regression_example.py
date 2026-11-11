"""examples/regression: two runs of one suite, compared through the CLI."""

import json
from pathlib import Path

from typer.testing import CliRunner

from agentgauge.cli import app

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "regression"
runner = CliRunner(env={"COLUMNS": "200"})


def run_both(tmp_path: Path) -> Path:
    db = tmp_path / "runs.db"
    for name in ("baseline", "candidate"):
        result = runner.invoke(app, ["run", str(EXAMPLE / f"{name}.yaml"), "--db", str(db)])
        assert result.exit_code == 0, result.output
    return db


def test_the_candidate_is_a_significant_regression(tmp_path: Path) -> None:
    db = run_both(tmp_path)
    result = runner.invoke(
        app, ["compare", "previous", "latest", "--db", str(db), "--format", "json"]
    )
    assert result.exit_code == 1, result.output
    data = json.loads(result.output)
    assert data["verdict"] == "regression" and data["cases"] == 12
    assert data["regressed"] == ["japan", "canada", "egypt", "norway", "kenya", "chile", "greece"]
    assert data["improved"] == []
    assert abs(data["p_value"] - 2 / 128) < 1e-12  # 7 of 7 discordant cases one way
    assert abs(data["delta"] + 7 / 12) < 1e-12


def test_accepting_a_big_enough_drop_lets_it_pass(tmp_path: Path) -> None:
    db = run_both(tmp_path)
    result = runner.invoke(
        app, ["compare", "previous", "latest", "--db", str(db), "--max-drop", "0.6"]
    )
    assert result.exit_code == 0 and "No significant change" in result.output
