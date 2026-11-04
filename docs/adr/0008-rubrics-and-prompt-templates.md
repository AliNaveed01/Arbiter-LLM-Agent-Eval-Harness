# 8. Rubrics and prompt templates

Date: 2026-11-04

## Status

Accepted

## Context

An LLM judge is only as trustworthy as its instructions. Changing a prompt changes the judge, so a prompt needs a version, and a rubric needs a precise scale so that scores can be compared with human labels later.

## Decision

- A `Rubric` has a `name`, one or more `criteria`, a `scale`, a `prompt_version`, an optional custom `template` and an optional `pass_at` threshold.
- A `Scale` is binary (scores 0 and 1) or ordinal (1 to N, 2 <= N <= 10). In YAML it is written `binary` or just the number of levels.
- `pass_at` is the lowest passing score. The default is 1 for binary and `N // 2 + 1` for ordinal, so 3 of 4 and 3 of 5 pass at 3.
- Prompt templates are versioned. `v1` is built in. A rubric names a built-in `prompt_version`, or supplies its own `template` and uses `prompt_version` as the label for it. An unknown version without a template is a validation error.
- Templates use `$placeholder` substitution (`string.Template`) with a closed set of placeholders: `rubric`, `criteria`, `scale`, `input`, `expected`, `output`. Unknown placeholders and stray `$` are rejected when the rubric is loaded, not when the first case runs. `$` rather than `{}` so JSON braces in a prompt need no escaping.
- The system message is fixed and carries the reply format (`{"score": <integer>, "reasoning": "..."}`). A template controls only the user message, so a custom template cannot break verdict parsing.
- Rendering is a pure function of rubric, case and output, which the judge cache relies on.
- Rubrics load from YAML with `file:line` errors, sharing the YAML helpers with the suite loader.

## Consequences

- Bumping `prompt_version` (or editing a custom template) is how a team changes the judge deliberately; cached verdicts and calibration results then belong to the new version.
- Built-in templates must never be edited in place: add `v2` instead.
- Only one criterion list and one scale per rubric; multi-dimension judging is done with several `llm_judge` scorers.
