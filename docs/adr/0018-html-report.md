# 18. HTML report

Date: 2026-11-12

## Status

Accepted

## Context

A table in a terminal is enough to gate a pull request, but not to look through a run: read what the model said, follow an agent's steps, or show a regression to someone who will not run the tool. v1.0 needs a report that can be attached to a CI job or opened from an email.

## Decision

- **One self-contained HTML file.** `agentgauge report RUN` writes a single file with its CSS inline, its chart as inline SVG, and no scripts, fonts or images. It opens from disk, in an email attachment or a CI artifact, and keeps working offline.
- **Standard library only.** No template engine and no new dependency. The report is built from a few small functions.
- **Escaping has one path.** Model output, case ids, tool arguments and error messages are untrusted. `report/html.py` is the only place text becomes markup: `tag()` and `text()` escape everything that is not already `Markup`, and `Markup` is produced only by those functions. Element and attribute names are validated. Tests feed a script tag through every part of the report and assert it never appears as markup.
- **A Content-Security-Policy as a second layer.** The page declares `default-src 'none'; style-src 'unsafe-inline'; img-src data:`. Even if escaping were wrong somewhere, no script could run and nothing could be fetched.
- **No JavaScript at all.** Expanding a case uses `<details>`, navigation uses anchors, and the chart is static SVG with a text alternative. That keeps the page safe and accessible; the cost is no sorting or filtering in the browser.
- **Meaning never rests on colour.** Pass, fail and error carry an icon and a word. The chart has a title, an `aria-label` and a caption stating the same numbers as the table.
- **Themes use the system setting by default**, with CSS variables for both, and `--theme light|dark` to force one. Print styles drop the page chrome and `--expand` opens every case.
- **The report shows a comparison but does not gate.** `report --baseline` embeds the same comparison `compare` makes, using the same functions for the sentences and numbers, but never changes the exit code. Gating stays in `compare`, so a report generated for reading cannot fail a job by accident.

## Consequences

- A run does not store its case inputs, so the report shows outputs, scores, errors and trajectories but not the prompt. Showing prompts needs the suite file at report time or a storage change; it is left for later.
- Everything is inlined, so a run with very large outputs makes a large file. Long text is kept whole inside scrollable blocks rather than truncated.
- Without JavaScript the report cannot sort or filter its table. For large suites that is a real limit.
- Closed `<details>` do not print; `--expand` exists for that.
