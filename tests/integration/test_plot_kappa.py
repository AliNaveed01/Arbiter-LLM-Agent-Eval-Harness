"""The kappa chart script: reads result files, draws a PNG."""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "plot_kappa.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plot_kappa", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


def write(path: Path, model: str, kappa: float | None, ci: list[float] | None) -> None:
    body: dict[str, Any] = {"model": model, "judge": {"kappa": kappa, "kappa_ci": ci}}
    path.write_text(json.dumps(body), encoding="utf-8")


def test_points_are_ordered_by_model_size_then_variant(tmp_path: Path) -> None:
    write(tmp_path / "qwen3-4b-thinking-off.json", "qwen3:4b", 0.5, [0.2, 0.8])
    write(tmp_path / "qwen3-0.6b-thinking-off.json", "qwen3:0.6b", -0.1, [-0.2, 0.0])
    write(tmp_path / "qwen3-0.6b-thinking-on.json", "qwen3:0.6b", 0.3, [0.0, 0.6])
    write(tmp_path / "qwen3-0.6b.json", "qwen3:0.6b", 0.07, [-0.3, 0.4])
    points = load_script().load_points(tmp_path)
    assert [(p.model, p.variant) for p in points] == [
        ("qwen3:0.6b", "thinking on (first run)"),
        ("qwen3:0.6b", "thinking on"),
        ("qwen3:0.6b", "thinking off"),
        ("qwen3:4b", "thinking off"),
    ]
    assert points[0].low == -0.3 and points[0].high == 0.4


def test_a_run_without_kappa_is_loaded_but_not_drawn(tmp_path: Path) -> None:
    write(tmp_path / "m-thinking-on.json", "m:1b", None, None)
    write(tmp_path / "m-thinking-off.json", "m:1b", 0.2, [0.0, 0.4])
    script = load_script()
    points = script.load_points(tmp_path)
    assert points[0].kappa is None
    out = tmp_path / "chart.png"
    script.draw(points, out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_main_writes_the_png_from_a_results_folder(tmp_path: Path, monkeypatch: Any) -> None:
    write(tmp_path / "a-thinking-on.json", "a:1b", 0.4, [0.1, 0.7])
    out = tmp_path / "out" / "chart.png"
    monkeypatch.setattr("sys.argv", ["plot_kappa", "--results", str(tmp_path), "--out", str(out)])
    load_script().main()
    assert out.exists()
