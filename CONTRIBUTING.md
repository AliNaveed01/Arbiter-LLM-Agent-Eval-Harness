# Contributing

Workflow is trunk-based: one issue, one short-lived branch, one PR, rebase-merged into a protected `main`.

## Setup

```bash
uv sync
git config core.hooksPath .githooks
uv run pre-commit install
```

## Conventions

| Area | Rule |
| --- | --- |
| Branches | `feat/<issue#>-<slug>`, `fix/…`, `chore/…`, `docs/…`, `test/…`, `ci/…`. Branch from latest `main` and keep it alive under 2 days |
| Commits | Conventional Commits (`feat(runner): add async concurrency limit`). One logical change each, typically 3–8 per PR. Imperative, under 72 chars |
| PRs | Title in Conventional Commit format, body says `Closes #N`, plus what changed, how it was tested and any trade-offs. Under ~400 changed lines |
| Merge | Rebase-merge only. No squash, no merge commits. Delete the branch after merge |
| Quality gate | ruff (lint + format), pyright strict on `src/`, pytest with ≥85% coverage on new code. All green before merge |
| Releases | release-please reads commit types, then bumps semver, writes the CHANGELOG and tags the release |
| Decisions | Any non-obvious design choice gets an ADR in `docs/adr/NNNN-title.md` |

## Before you push

```bash
uv run ruff check --fix . && uv run ruff format . && uv run pyright && uv run pytest
```
