# 7. CLI behaviour and provider configuration in suites

Date: 2026-11-03

## Status

Accepted

## Context

Issue #10 requires `agentgauge run`, `runs list` and `runs show`, with Rich output and a non-zero exit on configuration errors. The acceptance criteria do not say how `run` learns which model to call, how API keys are supplied, or which outcomes count as errors. The M1 goal is that `agentgauge run suite.yaml` works as written.

## Decision

- **A suite may carry a `provider:` block** (`type`, `model`, `base_url`, `api_key_env`, `params`, and `responses` for the fake provider). `run` builds the provider from it, so a suite file is self-contained and reproducible. JSONL suites have no place for it and take options instead.
- **Command-line options override the block**: `--provider`, `--model`, `--base-url`, `--api-key-env`. With no block and no `--model`, `run` exits with a configuration error that says what to add.
- **API keys never live in suite files.** `api_key_env` names an environment variable. If it is set explicitly the variable must exist; if left unset, `OPENAI_API_KEY` is used when present and no key is sent otherwise, which suits local servers (a hosted endpoint then fails per case with a clear 401).
- **Exit codes**: 0 on a completed run, even if cases fail scoring or error; 2 for configuration problems (unreadable or invalid suite, unknown scorer, bad provider options, missing key variable, unusable database); 1 for `runs show` with an unknown or ambiguous id. Pass/fail gating of CI is M4's job and will use the statistical comparison, not `run`'s exit code.
- **Everything that can fail on configuration is checked before spending model calls**: the suite is loaded and the database opened first; scorers and the provider are built before the first case runs.
- **Storage location**: `.agentgauge/runs.db` in the working directory by default, overridable with `--db` or `AGENTGAUGE_DB`. The directory is gitignored.
- `runs list` shows the 20 newest runs by default; `runs show` accepts a unique id prefix and prints each case's output.
- Run ids are shown as their first 8 characters.

## Consequences

- Suites are portable but are coupled to one provider; comparing models means overriding `--model` or writing a second suite.
- A suite from an untrusted source can point `base_url` at any server. API keys are only sent to the endpoint the user configured, but users should read suites before running them.
- If an 8-character prefix ever becomes ambiguous, `runs show` says so and the full id (stored in the database) can be used.
