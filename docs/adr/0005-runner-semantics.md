# 5. Runner semantics

Date: 2026-11-03

## Status

Accepted

## Context

Issue #8 requires an async runner with a concurrency limit, failure isolation and per-case latency and cost. It leaves open what counts as a failure, what latency means when a provider retries, and how a run reports a case that never produced output.

## Decision

- `run_suite(suite, provider, *, concurrency=8, params=None)` returns a `RunResult`. Cases run concurrently under an anyio `CapacityLimiter`; results are returned in suite order regardless of completion order.
- **Failures are data.** An exception from the provider or from a scorer is recorded in `CaseResult.error` as `ExceptionType: message`, and the run continues. Only `Exception` is caught: cancellation and `KeyboardInterrupt` still propagate, so Ctrl-C and timeouts around a run work.
- A provider failure leaves `output` empty and `scores` empty. A scorer failure keeps the output and the scores from the other scorers, and the error names the scorer. Either way `CaseResult.passed` is false.
- A **failed score is not an error**: a scorer that judges the output wrong returns `passed=False` and the case has no `error`.
- **Configuration errors are not isolated.** Scorers are created before any case runs, so an unknown scorer or invalid params raises immediately and no provider calls are made.
- **Latency** on `CaseResult` is the wall-clock time the runner waited for the provider, including the adapter's retries and backoff, and is recorded for failed cases too. This differs from `ModelOutput.latency_ms`, which is the single successful request. **Cost** is copied from `ModelOutput.cost_usd`, and is empty when the provider reports none.
- The run id is a random UUID4 hex string; timestamps are timezone-aware UTC.

## Consequences

- A run always produces a result, so partial results are stored and comparable.
- Callers must check `error` as well as scores; `passed` does that for them.
- Retries are invisible except through latency; a later change can add an attempt count to `ModelOutput`.
- There is no per-case timeout beyond the provider's own; callers can wrap `run_suite` in `anyio.move_on_after`.
