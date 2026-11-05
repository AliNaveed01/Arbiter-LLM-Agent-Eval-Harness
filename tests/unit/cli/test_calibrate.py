from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from agentgauge.cli import app

runner = CliRunner(env={"COLUMNS": "200"})

CASES = ["q1", "q2", "q3", "q4", "q5", "q6"]


def make_suite(tmp_path: Path, verdicts: dict[str, str], scorers: list[Any] | None = None) -> Path:
    """A suite whose fake judge answers per case; ``verdicts`` maps case id to the raw reply."""
    judge = {
        "name": "llm_judge",
        "params": {
            "cache": False,
            "rubric": {"name": "quality", "criteria": ["is right"], "scale": "binary"},
            "judge": {
                "type": "fake",
                "model": "judge-1",
                "match": "contains",
                "responses": {f"answer to {case}": reply for case, reply in verdicts.items()},
            },
        },
    }
    suite = {
        "name": "demo",
        "provider": {
            "type": "fake",
            "model": "scripted",
            "responses": {case: f"answer to {case}" for case in CASES},
        },
        "scorers": scorers if scorers is not None else [judge],
        "cases": [{"id": case, "input": case, "expected": "a"} for case in CASES],
    }
    path = tmp_path / "suite.yaml"
    path.write_text(yaml.safe_dump(suite), encoding="utf-8")
    return path


def reply(score: int) -> str:
    return f'{{"score": {score}, "reasoning": "because"}}'


def make_labels(tmp_path: Path, labels: dict[str, int]) -> Path:
    path = tmp_path / "labels.yaml"
    path.write_text(
        yaml.safe_dump([{"case_id": k, "label": v} for k, v in labels.items()]), encoding="utf-8"
    )
    return path


def calibrate(suite: Path, labels: Path, *extra: str) -> tuple[int, str]:
    result = runner.invoke(app, ["calibrate", str(suite), "--labels", str(labels), *extra])
    return result.exit_code, " ".join(result.output.split())


HUMAN = {"q1": 1, "q2": 1, "q3": 1, "q4": 0, "q5": 0, "q6": 0}


def test_agreeing_judge_gets_a_clean_report(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    code, out = calibrate(make_suite(tmp_path, verdicts), make_labels(tmp_path, HUMAN))
    assert code == 0, out
    assert "calibration of demo judge judge-1" in out
    assert "cases compared 6" in out
    assert "accuracy 1.00" in out
    assert "kappa (none weighting) 1.00" in out
    assert "Confusion matrix" in out
    assert "Warning" not in out


def test_disagreeing_judge_triggers_the_trust_warning_but_exits_zero(tmp_path: Path) -> None:
    verdicts = {case: reply(1 - score) for case, score in HUMAN.items()}
    code, out = calibrate(make_suite(tmp_path, verdicts), make_labels(tmp_path, HUMAN))
    assert code == 0
    assert "Warning" in out
    assert "not trustworthy" in out


def test_only_labelled_cases_are_run_and_the_rest_are_reported(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    labels = make_labels(tmp_path, {"q1": 1, "q2": 1, "q4": 0, "q5": 0})
    code, out = calibrate(make_suite(tmp_path, verdicts), labels)
    assert code == 0
    assert "cases compared 4" in out
    assert "2 case(s) in the suite have no label" in out


def test_judge_errors_are_skipped_and_named(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    verdicts["q3"] = "not a verdict"
    code, out = calibrate(make_suite(tmp_path, verdicts), make_labels(tmp_path, HUMAN))
    assert code == 0
    assert "cases compared 5" in out
    assert "1 labelled case(s) not compared (judge error): q3" in out


def test_exit_one_when_no_case_could_be_judged(tmp_path: Path) -> None:
    verdicts = {case: "garbage" for case in HUMAN}
    code, out = calibrate(make_suite(tmp_path, verdicts), make_labels(tmp_path, HUMAN))
    assert code == 1
    assert "nothing to compare" in out


def test_labels_for_unknown_cases_are_a_configuration_error(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    labels = make_labels(tmp_path, {**HUMAN, "typo": 1})
    code, out = calibrate(make_suite(tmp_path, verdicts), labels)
    assert code == 2
    assert "not in the suite: typo" in out


def test_labels_off_the_scale_are_a_configuration_error(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    labels = make_labels(tmp_path, {**HUMAN, "q6": 4})
    code, out = calibrate(make_suite(tmp_path, verdicts), labels)
    assert code == 2
    assert "outside the judge's scale [0, 1] for: q6" in out


def test_bad_labels_file_reports_file_and_line(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    labels = tmp_path / "labels.yaml"
    text = "- case_id: q1\n  label: 1\n- case_id: q2\n  label: maybe\n"
    labels.write_text(text, encoding="utf-8")
    code, out = calibrate(make_suite(tmp_path, verdicts), labels)
    assert code == 2
    assert "labels.yaml:4" in out


def test_missing_scorer_and_ambiguous_scorer_are_configuration_errors(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    suite = make_suite(tmp_path, verdicts)
    labels = make_labels(tmp_path, HUMAN)
    code, out = calibrate(suite, labels, "--scorer", "nope")
    assert code == 2
    assert "no scorer named 'nope'" in out
    spec = yaml.safe_load(suite.read_text(encoding="utf-8"))["scorers"][0]
    doubled = make_suite(tmp_path, verdicts, scorers=[spec, spec])
    code, out = calibrate(doubled, labels)
    assert code == 2
    assert "more than one scorer named 'llm_judge'" in out


def test_a_scorer_that_is_not_a_judge_is_rejected(tmp_path: Path) -> None:
    suite = make_suite(tmp_path, {}, scorers=["exact_match"])
    code, out = calibrate(suite, make_labels(tmp_path, HUMAN), "--scorer", "exact_match")
    assert code == 2
    assert "does not report a scale" in out


def test_bad_judge_configuration_is_a_configuration_error(tmp_path: Path) -> None:
    broken = {"name": "llm_judge", "params": {"rubric": {"name": "x"}, "judge": {"type": "fake"}}}
    suite = make_suite(tmp_path, {}, scorers=[broken])
    code, out = calibrate(suite, make_labels(tmp_path, HUMAN))
    assert code == 2
    assert "rubric is invalid" in out


def test_missing_suite_file_is_a_configuration_error(tmp_path: Path) -> None:
    code, out = calibrate(tmp_path / "nope.yaml", make_labels(tmp_path, HUMAN))
    assert code == 2
    assert "cannot read file" in out


def test_labels_option_is_required(tmp_path: Path) -> None:
    suite = make_suite(tmp_path, {})
    result = runner.invoke(app, ["calibrate", str(suite)])
    assert result.exit_code == 2


def test_ordinal_rubric_reports_quadratic_weighting(tmp_path: Path) -> None:
    suite_path = make_suite(tmp_path, {case: reply(3) for case in CASES})
    data = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    params = data["scorers"][0]["params"]
    params["rubric"]["scale"] = 5
    judge = params["judge"]["responses"]
    for i, case in enumerate(CASES):
        judge[f"answer to {case}"] = reply(1 + i % 5)
    suite_path.write_text(yaml.safe_dump(data), encoding="utf-8")
    labels = make_labels(tmp_path, {case: 1 + i % 5 for i, case in enumerate(CASES)})
    code, out = calibrate(suite_path, labels)
    assert code == 0, out
    assert "quadratic weighting" in out


def test_fail_under_gates_on_kappa(tmp_path: Path) -> None:
    good = {case: reply(score) for case, score in HUMAN.items()}
    suite, labels = make_suite(tmp_path, good), make_labels(tmp_path, HUMAN)
    code, out = calibrate(suite, labels, "--fail-under", "0.6")
    assert code == 0 and "kappa (none weighting) 1.00" in out

    bad = {case: reply(1 - score) for case, score in HUMAN.items()}
    code, out = calibrate(make_suite(tmp_path, bad), labels, "--fail-under", "0.6")
    assert code == 1
    assert "kappa -1.00 is below --fail-under 0.6" in out
    assert "Warning" in out  # the report is still printed

    code, _ = calibrate(make_suite(tmp_path, bad), labels)
    assert code == 0  # without the option a low kappa only warns


def test_fail_under_treats_undefined_kappa_as_a_failure(tmp_path: Path) -> None:
    same = {case: reply(1) for case in HUMAN}
    ones = make_labels(tmp_path, {case: 1 for case in HUMAN})
    code, out = calibrate(make_suite(tmp_path, same), ones, "--fail-under", "0.0")
    assert code == 1 and "kappa undefined is below --fail-under" in out


def test_fail_under_must_be_a_valid_kappa(tmp_path: Path) -> None:
    verdicts = {case: reply(score) for case, score in HUMAN.items()}
    code, _ = calibrate(
        make_suite(tmp_path, verdicts), make_labels(tmp_path, HUMAN), "--fail-under", "2"
    )
    assert code == 2
