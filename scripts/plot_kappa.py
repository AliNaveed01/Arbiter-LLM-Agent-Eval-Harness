"""Draw the kappa-by-model chart for docs/benchmarks from the result files.

Each point is a model acting as judge on the same 30 human-labelled answers; the whisker is the
95% bootstrap interval. Result files are named ``<model>-thinking-on.json`` and
``<model>-thinking-off.json``; a plain ``<model>.json`` is the first run of a model with
thinking on, kept as a separate row.

    uv run python scripts/plot_kappa.py
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs" / "benchmarks" / "results"
OUT = ROOT / "docs" / "benchmarks" / "kappa-by-model.png"
TRUSTED = 0.6

INK, MUTED, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"
BLUE, ORANGE = "#2a78d6", "#eb6834"  # categorical slots 1 and 2 of the reference palette


@dataclass(frozen=True)
class Point:
    model: str
    variant: str  # "thinking on", "thinking off" or "thinking on (first run)"
    kappa: float | None
    low: float | None
    high: float | None


STYLES: dict[str, tuple[str, str, bool]] = {
    "thinking on (first run)": (BLUE, "o", False),
    "thinking on": (BLUE, "o", True),
    "thinking off": (ORANGE, "s", True),
}


def _variant(path: Path) -> tuple[str, str]:
    stem = path.stem
    for suffix, variant in (("-thinking-on", "thinking on"), ("-thinking-off", "thinking off")):
        if stem.endswith(suffix):
            return stem[: -len(suffix)], variant
    return stem, "thinking on (first run)"


def load_points(results: Path) -> list[Point]:
    """One point per result file, ordered by model size then variant."""
    points: list[Point] = []
    for path in sorted(results.glob("*.json")):
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        judge = data["judge"]
        stem_model, variant = _variant(path)
        interval = judge.get("kappa_ci")
        points.append(
            Point(
                model=data.get("model", stem_model),
                variant=variant,
                kappa=judge.get("kappa"),
                low=interval[0] if interval else None,
                high=interval[1] if interval else None,
            )
        )
    order = list(STYLES)
    return sorted(points, key=lambda p: (_size(p.model), order.index(p.variant)))


def _size(model: str) -> float:
    tag = model.rsplit(":", 1)[-1].lower().rstrip("b")
    try:
        return float(tag)
    except ValueError:
        return float("inf")


def draw(points: list[Point], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    drawn = [p for p in points if p.kappa is not None and p.low is not None and p.high is not None]
    models = list(dict.fromkeys(p.model for p in points))
    variants = [v for v in STYLES if any(p.variant == v for p in drawn)]
    fig, ax = plt.subplots(figsize=(8, 1.6 + 1.5 * len(models)), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    spread = 0.26
    for p in drawn:
        assert p.kappa is not None and p.low is not None and p.high is not None
        color, marker, filled = STYLES[p.variant]
        slot = variants.index(p.variant) - (len(variants) - 1) / 2
        y = len(models) - 1 - models.index(p.model) + slot * spread
        ax.hlines(y, p.low, p.high, color=color, linewidth=2, zorder=2)
        ax.plot(
            p.kappa,
            y,
            marker,
            markersize=9,
            color=color,
            markerfacecolor=color if filled else SURFACE,
            markeredgewidth=2,
            zorder=3,
        )
        ax.annotate(
            f"{p.kappa:.2f}",
            (p.high, y),
            xytext=(7, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK,
        )
    ax.axvline(TRUSTED, color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax.axvline(0, color=GRID, linewidth=1, zorder=1)
    ax.text(
        TRUSTED, len(models) - 0.45, " agentgauge trusts a judge from 0.6", color=MUTED, fontsize=9
    )
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(list(reversed(models)), color=INK, fontsize=10)
    ax.set_xlim(-0.5, 1.0)
    ax.set_ylim(-0.6, len(models) - 0.3)
    ax.set_xlabel("Cohen's kappa against human labels (30 answers, 95% bootstrap interval)")
    ax.xaxis.label.set_color(MUTED)
    ax.tick_params(colors=MUTED, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8, zorder=0)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    handles = [
        plt.Line2D(
            [],
            [],
            color=STYLES[v][0],
            marker=STYLES[v][1],
            markerfacecolor=STYLES[v][0] if STYLES[v][2] else SURFACE,
            markeredgewidth=2,
            markersize=8,
            linewidth=2,
            label=v,
        )
        for v in variants
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False, labelcolor=INK, fontsize=9)
    ax.set_title("Judge agreement by model", loc="left", color=INK, fontsize=12, pad=12)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    points = load_points(args.results)
    draw(points, args.out)
    print(f"wrote {args.out} from {len(points)} result files")


if __name__ == "__main__":
    main()
