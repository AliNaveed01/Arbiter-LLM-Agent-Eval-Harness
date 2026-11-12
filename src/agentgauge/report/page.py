"""The page around a report: one self-contained HTML document, no scripts, no requests."""

from __future__ import annotations

from typing import Literal

from agentgauge.report.html import Markup, esc

Theme = Literal["auto", "light", "dark"]
THEMES: tuple[Theme, ...] = ("auto", "light", "dark")

# No script can run and nothing can be fetched, whatever a case's text contains.
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:"

_LIGHT = (
    "--surface:#fcfcfb;--raised:#f4f3f0;--ink:#0b0b0b;--muted:#52514e;--line:#e4e3df;"
    "--accent:#2a78d6;--good:#1a7f37;--bad:#c9372c;--warn:#8a5a00;--before:#2a78d6;--after:#eb6834;"
)
_DARK = (
    "--surface:#1a1a19;--raised:#242423;--ink:#f0efec;--muted:#c3c2b7;--line:#3a3a38;"
    "--accent:#3987e5;--good:#3fb950;--bad:#f0675d;--warn:#d9a441;--before:#3987e5;--after:#d95926;"
)

STYLE = f"""
:root{{color-scheme:light dark;{_LIGHT}}}
@media (prefers-color-scheme:dark){{:root:where(:not([data-theme="light"])){{{_DARK}}}}}
:root[data-theme="light"]{{color-scheme:light;{_LIGHT}}}
:root[data-theme="dark"]{{color-scheme:dark;{_DARK}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--surface);color:var(--ink);
  font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}
main{{max-width:60rem;margin:0 auto;padding:1.5rem 16px 3rem}}
h1{{font-size:1.5rem;margin:0 0 .25rem}}
h2{{font-size:1.15rem;margin:2rem 0 .75rem}}
p{{margin:.5rem 0}}
.muted{{color:var(--muted)}}
code,pre{{font:.875rem/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
.scroll{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%}}
th,td{{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:.85rem}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}
.stats{{display:flex;flex-wrap:wrap;gap:.75rem;margin:1rem 0;padding:0;list-style:none}}
.stats li{{background:var(--raised);border-radius:8px;padding:.6rem .9rem;min-width:7rem}}
.stats b{{display:block;font-size:1.25rem;font-variant-numeric:tabular-nums}}
.status{{font-weight:600;white-space:nowrap}}
.pass{{color:var(--good)}}
.fail{{color:var(--bad)}}
.error{{color:var(--warn)}}
details.case{{border:1px solid var(--line);border-radius:8px;margin:.5rem 0}}
details.case>summary{{cursor:pointer;padding:.5rem .75rem;list-style-position:inside}}
details.case[open]>summary{{border-bottom:1px solid var(--line)}}
.body{{padding:.25rem .75rem .75rem}}
.step{{border-left:3px solid var(--line);padding-left:.75rem;margin:.5rem 0}}
pre{{margin:.25rem 0 .75rem;padding:.6rem .75rem;background:var(--raised);border-radius:6px;
  white-space:pre-wrap;overflow-wrap:anywhere;max-height:24rem;overflow:auto}}
.label{{color:var(--muted);font-size:.8rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.04em;margin-top:.75rem}}
svg text{{fill:var(--ink)}}
svg .axis{{stroke:var(--muted);stroke-width:1}}
svg .zero{{stroke:var(--ink);stroke-width:1;stroke-dasharray:3 3}}
svg .whisker{{stroke-width:3;stroke-linecap:round}}
svg .mark-fail{{stroke:var(--bad);fill:var(--bad)}}
svg .mark-pass{{stroke:var(--good);fill:var(--good)}}
svg .mark-flat{{stroke:var(--accent);fill:var(--accent)}}
svg .dot{{stroke:var(--surface);stroke-width:2}}
figure.chart{{margin:1rem 0}}
figure.chart figcaption{{font-size:.85rem}}
@media print{{
  body{{background:#fff;color:#000}}
  main{{max-width:none;padding:0}}
  pre{{max-height:none;overflow:visible}}
  details.case{{break-inside:avoid}}
}}
"""


def page(title: str, body: Markup, *, theme: Theme = "auto") -> str:
    """A complete HTML5 document around ``body``.

    ``theme`` follows the reader's system setting (``auto``) or forces ``light`` or ``dark``.
    """
    if theme not in THEMES:
        raise ValueError(f"theme must be one of {list(THEMES)}, got {theme!r}")
    attribute = "" if theme == "auto" else f' data-theme="{theme}"'
    return (
        f'<!doctype html>\n<html lang="en"{attribute}>\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{esc(CSP)}">\n'
        f"<title>{esc(title)}</title>\n<style>{STYLE}</style>\n</head>\n"
        f"<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n"
    )
