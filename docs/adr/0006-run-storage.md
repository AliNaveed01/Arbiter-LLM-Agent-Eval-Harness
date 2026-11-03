# 6. Run storage

Date: 2026-11-03

## Status

Accepted

## Context

Issue #9 asks for a SQLite store with `list_runs`, `get_run` and a versioned schema, without fixing the table layout, how ids and timestamps are stored, or how a too-new database is handled.

## Decision

- Two tables: `runs` (one row per run) and `case_results` (one row per case, keyed by `(run_id, position)` so suite order is preserved). Case output and scores are stored as JSON columns because they are only ever read back whole; `passed`, `error`, latency and cost are real columns so summaries need no JSON parsing.
- `passed` is computed when a run is saved (`CaseResult.passed`) and stored, so listing is a single aggregate query.
- **Migrations** are an ordered tuple of `(version, SQL)`. Opening the store applies pending ones, each in its own transaction together with its row in `schema_migrations`, so a failed migration leaves the previous version intact. Versions must be 1, 2, 3, ... with no gaps.
- **A database newer than the code is refused** with a clear error rather than written to, since an old agentgauge cannot know what a newer schema means.
- **Timestamps** are stored as UTC ISO-8601 text with fixed microsecond precision, so text ordering equals time ordering. Naive datetimes are rejected rather than guessed at.
- **Run ids** are full UUID hex strings. `get_run` also accepts a unique prefix (as git does for commit ids), since typing 32 characters in the CLI is unreasonable. An ambiguous prefix is an error; an unknown id raises `RunNotFoundError`. `LIKE` wildcards in user input are escaped.
- `save_run` is atomic and rejects a duplicate run id. There is no update or delete operation in M1; runs are immutable records.
- `list_runs(limit=None)` returns `RunSummary` objects (identity, timing, total/passed/errored case counts), newest first.
- The store is synchronous: SQLite calls are fast and local, and the CLI calls it after a run completes.

## Consequences

- Adding a column or table is a new migration, never an edit to an old one.
- Everything in `output_json` and `scores_json` is only queryable by loading it. If M4's comparison needs per-score queries, a later migration can add a `scores` table.
- One connection per `RunStore`; it is not safe to share across threads.
