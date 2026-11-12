"""An inline SVG of the pass-rate change and its interval, drawn against zero."""

from __future__ import annotations

from agentgauge.compare import Comparison
from agentgauge.compare.format import interval, points
from agentgauge.report.html import Markup, join, tag

WIDTH, HEIGHT = 480, 96
LEFT, RIGHT = 36, 36
AXIS_Y = 56
STEPS = (5, 10, 20, 25, 50, 100)
MARK = {"regression": "mark-fail", "improvement": "mark-pass", "unchanged": "mark-flat"}


def axis_extent(c: Comparison) -> int:
    """The half-width of the axis in percentage points: a round number that holds the interval."""
    reach = max(abs(c.delta_ci[0]), abs(c.delta_ci[1]), abs(c.delta)) * 100
    return next((step for step in STEPS if step >= reach * 1.1), 100)


def description(c: Comparison) -> str:
    """The text alternative: the same numbers the drawing shows."""
    return (
        f"Change in pass rate {points(c.delta)}, 95% interval "
        f"{interval(*c.delta_ci, unit=' points')}; zero means no change."
    )


def _x(value_points: float, extent: int) -> float:
    return LEFT + (value_points + extent) / (2 * extent) * (WIDTH - LEFT - RIGHT)


def _tick(value: int, extent: int) -> Markup:
    x = _x(value, extent)
    label = "0" if value == 0 else f"{value:+d}"
    return join(
        [
            tag("line", x1=f"{x:.1f}", x2=f"{x:.1f}", y1=AXIS_Y - 6, y2=AXIS_Y + 6, class_="axis"),
            tag("text", label, x=f"{x:.1f}", y=AXIS_Y + 24, text_anchor="middle", font_size=12),
        ]
    )


def change_chart(c: Comparison) -> Markup:
    """The change in pass rate as a dot, its 95% interval as a whisker, and a line at zero."""
    extent = axis_extent(c)
    low, high = (_x(v * 100, extent) for v in c.delta_ci)
    centre = _x(c.delta * 100, extent)
    zero = _x(0, extent)
    mark = MARK[c.verdict]
    drawing = tag(
        "svg",
        tag("title", description(c)),
        tag("line", x1=LEFT, x2=WIDTH - RIGHT, y1=AXIS_Y, y2=AXIS_Y, class_="axis"),
        join(_tick(v, extent) for v in (-extent, 0, extent)),
        tag("line", x1=f"{zero:.1f}", x2=f"{zero:.1f}", y1=16, y2=AXIS_Y + 6, class_="zero"),
        tag(
            "line",
            x1=f"{low:.1f}",
            x2=f"{high:.1f}",
            y1=AXIS_Y,
            y2=AXIS_Y,
            class_=f"whisker {mark}",
        ),
        tag("circle", cx=f"{centre:.1f}", cy=AXIS_Y, r=6, class_=f"dot {mark}"),
        tag(
            "text",
            f"{points(c.delta)}",
            x=f"{centre:.1f}",
            y=34,
            text_anchor="middle",
            font_size=13,
        ),
        viewBox=f"0 0 {WIDTH} {HEIGHT}",
        role="img",
        aria_label=description(c),
        width="100%",
        style=f"max-width:{WIDTH}px",
    )
    caption = tag(
        "figcaption",
        "Change in pass rate, candidate minus baseline, in percentage points, "
        "with its 95% interval.",
        class_="muted",
    )
    return tag("figure", drawing, caption, class_="chart")
