# 3. Scorer interface and registry

Date: 2026-11-03

## Status

Accepted

## Context

Suite files reference scorers by name, and some scorers need configuration (a regex pattern, a numeric tolerance, a JSON Schema). Later milestones add scorers that call a model (the LLM judge), so the interface must not assume scoring is instant.

## Decision

- A scorer implements `name` and `async score(case, output) -> Score`. It is async so that judge scorers fit the same interface as deterministic ones; deterministic scorers simply never await.
- Output the scorer judges wrong yields a failing `Score` (`passed=False`, with a `reason`). A scorer raises only for problems with the scorer or its inputs; the runner records that as a case error.
- `Suite.scorers` is a tuple of `ScorerSpec(name, params)`. In YAML an entry is either a bare name (`exact_match`) or a mapping with `name` and `params`.
- Scorers live in a process-wide registry keyed by name. `register_scorer(name)` decorates a class or factory; `create_scorer(spec)` calls it with `params` as keyword arguments. Unknown names and invalid params raise `ScorerConfigError`, which the CLI reports as a configuration error before any case runs.
- Registering a duplicate name is an error, so a typo cannot silently replace a built-in.
- Reference values come from the case (`TestCase.expected`); everything else is scorer params.

## Consequences

- New scorers are added without touching the loader or runner.
- Misconfiguration surfaces before the run starts, not halfway through.
- A global registry is simple but shared state; tests clean up with `unregister_scorer`.
- Params are untyped dicts at the suite boundary; each scorer validates its own.
