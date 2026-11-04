from pathlib import Path

import pytest

from agentgauge.calibration import Label, LabelLoadError, load_labels


def _write(tmp_path: Path, text: str, name: str = "labels.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_list(tmp_path: Path) -> None:
    text = "- case_id: a\n  label: 1\n  annotator: ana\n- case_id: b\n  label: 0\n"
    path = _write(tmp_path, text)
    assert load_labels(path) == (
        Label(case_id="a", label=1, annotator="ana"),
        Label(case_id="b", label=0),
    )


def test_yaml_mapping_with_labels_key(tmp_path: Path) -> None:
    path = _write(tmp_path, "labels:\n  - case_id: a\n    label: 3\n")
    assert load_labels(path) == (Label(case_id="a", label=3),)


def test_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = _write(
        tmp_path, '{"case_id": "a", "label": 2}\n\n{"case_id": "b", "label": 5}\n', "l.jsonl"
    )
    assert [label.label for label in load_labels(path)] == [2, 5]


@pytest.mark.parametrize(("raw", "expected"), [("true", 1), ("false", 0), ("pass", 1), ("Fail", 0)])
def test_binary_conveniences(tmp_path: Path, raw: str, expected: int) -> None:
    assert load_labels(_write(tmp_path, f"- case_id: a\n  label: {raw}\n"))[0].label == expected


def test_yaml_errors_point_at_the_offending_line(tmp_path: Path) -> None:
    path = _write(tmp_path, "- case_id: a\n  label: 1\n- case_id: b\n  label: maybe\n")
    with pytest.raises(LabelLoadError, match=r"labels\.yaml:4: label") as info:
        load_labels(path)
    assert info.value.line == 4


def test_mapping_form_errors_point_at_the_line(tmp_path: Path) -> None:
    path = _write(tmp_path, "labels:\n  - case_id: a\n    label: 1\n    mood: odd\n")
    with pytest.raises(LabelLoadError) as info:
        load_labels(path)
    assert info.value.line == 4


def test_jsonl_errors_report_the_line(tmp_path: Path) -> None:
    path = _write(tmp_path, '{"case_id": "a", "label": 1}\n{"case_id": "b"}\n', "l.jsonl")
    with pytest.raises(LabelLoadError, match=r"l\.jsonl:2: label") as info:
        load_labels(path)
    assert info.value.line == 2
    bad = _write(tmp_path, '{"case_id": "a", "label": 1}\n{oops\n', "m.jsonl")
    with pytest.raises(LabelLoadError, match="invalid JSON") as info:
        load_labels(bad)
    assert info.value.line == 2


def test_duplicate_case_ids_name_both_lines(tmp_path: Path) -> None:
    path = _write(tmp_path, "- case_id: a\n  label: 1\n- case_id: a\n  label: 0\n")
    with pytest.raises(LabelLoadError, match=r"labelled twice \(first at line 1\)") as info:
        load_labels(path)
    assert info.value.line == 3


def test_item_that_is_not_a_mapping(tmp_path: Path) -> None:
    with pytest.raises(LabelLoadError) as info:
        load_labels(_write(tmp_path, "- case_id: a\n  label: 1\n- just a string\n"))
    assert info.value.line == 3


@pytest.mark.parametrize("text", ["", "[]", "labels: []", "just text", "a: 1"])
def test_empty_or_misshapen_files(tmp_path: Path, text: str) -> None:
    with pytest.raises(LabelLoadError, match=r"no labels found|top level"):
        load_labels(_write(tmp_path, text))


def test_invalid_yaml_unsupported_and_missing(tmp_path: Path) -> None:
    with pytest.raises(LabelLoadError, match="invalid YAML") as info:
        load_labels(_write(tmp_path, "- case_id: [a\n"))
    assert info.value.line == 1
    with pytest.raises(LabelLoadError, match="unsupported file type"):
        load_labels(_write(tmp_path, "x", "labels.csv"))
    with pytest.raises(LabelLoadError, match="cannot read file"):
        load_labels(tmp_path / "missing.yaml")


def test_float_and_string_scores_are_rejected(tmp_path: Path) -> None:
    for raw in ("3.5", '"3"'):
        with pytest.raises(LabelLoadError, match="label"):
            load_labels(_write(tmp_path, f"- case_id: a\n  label: {raw}\n"))
