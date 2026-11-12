import re

import pytest

from agentgauge.report.html import esc, tag
from agentgauge.report.page import CSP, page


def test_the_page_is_a_complete_html5_document() -> None:
    out = page("Run report", tag("h1", "Hello"))
    assert out.startswith('<!doctype html>\n<html lang="en">')
    assert '<meta charset="utf-8">' in out
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in out
    assert "<title>Run report</title>" in out
    assert "<main>\n<h1>Hello</h1>\n</main>" in out
    assert out.endswith("</html>\n")


def test_the_page_cannot_run_scripts_or_fetch_anything() -> None:
    out = page("t", tag("p", "x"))
    assert "<script" not in out.lower()
    assert (
        f'content="{esc(CSP)}"' in out and "default-src 'none'" in CSP and "script-src" not in CSP
    )
    assert not re.search(r"(https?:)?//", out), "no external URLs"
    assert "url(" not in out and "@import" not in out


def test_the_title_is_escaped() -> None:
    assert "<title>&lt;/title&gt;&lt;script&gt;</title>" in page("</title><script>", tag("p"))


def test_themes_follow_the_system_or_are_forced() -> None:
    auto = page("t", tag("p"))
    assert "data-theme" not in auto.split("<style>")[0]
    assert "prefers-color-scheme:dark" in auto
    assert '<html lang="en" data-theme="dark">' in page("t", tag("p"), theme="dark")
    assert '<html lang="en" data-theme="light">' in page("t", tag("p"), theme="light")


def test_both_themes_define_the_same_colour_roles() -> None:
    style = page("t", tag("p")).split("<style>")[1]
    light = re.search(r":root\{color-scheme:light dark;([^}]*)\}", style)
    dark = re.search(r':root\[data-theme="dark"\]\{color-scheme:dark;([^}]*)\}', style)
    assert light and dark
    roles = lambda block: set(re.findall(r"--[a-z]+(?=:)", block))  # noqa: E731
    assert roles(light.group(1)) == roles(dark.group(1)) and len(roles(light.group(1))) >= 10


def test_the_page_has_print_styles_and_wraps_long_text() -> None:
    style = page("t", tag("p"))
    assert "@media print" in style and "overflow-wrap:anywhere" in style


def test_an_unknown_theme_is_refused() -> None:
    with pytest.raises(ValueError, match="theme"):
        page("t", tag("p"), theme="sepia")  # type: ignore[arg-type]
