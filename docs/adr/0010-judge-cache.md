# 10. Judge cache

Date: 2026-11-04

## Status

Accepted

## Context

Judging costs a model call per case per scorer. Reruns of an unchanged suite, and repeated calibration while tuning thresholds, should not pay again, and should produce byte-identical scores even though a hosted model may not be perfectly deterministic.

## Decision

- Accepted judge replies are cached in a SQLite file, default `.agentgauge/judge-cache.db`, separate from the run database so either can be deleted on its own. It uses the same migration mechanism as the run store.
- The key is a SHA-256 over canonical JSON of the judge model name, the generation params, the prompt version and the fully rendered messages. Because the rendered prompt is included, editing criteria, a custom template, the case or the output changes the key even when `prompt_version` was not bumped.
- Only replies that passed verdict validation are cached, under the key of the original prompt, so a retried reply is cached too and a failed judgement never is. The first reply stored for a key is kept (`INSERT OR IGNORE`), which keeps results stable.
- The cache stores the raw reply, not the parsed score. A hit is parsed again against the current scale, and an entry that no longer parses is treated as a miss. Parsing is cheap and this keeps the cache free of scoring logic.
- A cached score records `cached: true` and `attempts: 0` in its details; everything else, including `raw_output`, matches the original.
- `cache` on the scorer is `true` (default path), a path, a `JudgeCache` or `false`. The scorer closes a cache it opened itself and leaves a supplied one open.
- The judge's own params are part of the key. Provider-level default params that are not passed on the request are not, which is why the scorer always sends its effective params explicitly.

## Consequences

- Reruns are free and deterministic until the judge model, params, prompt or inputs change.
- Switching provider while keeping the same model name (for example a different endpoint serving the same name) will hit the cache; delete the file to force fresh judgements.
- The cache grows without bound; there is no eviction. It is a plain file, safe to delete.
- The default path is relative to the working directory, like the run database.
