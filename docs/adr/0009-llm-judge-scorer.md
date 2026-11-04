# 9. The llm_judge scorer

Date: 2026-11-04

## Status

Accepted

## Context

A judge scorer asks a model to grade another model's output. It must fit the existing scorer interface, work with any provider, produce a verdict that can be compared with human labels, and leave enough behind to audit a score later.

## Decision

- `llm_judge` is a registered scorer configured from suite params: `rubric` (a mapping, or a path to a rubric YAML file, relative to the working directory) and `judge` (a provider block, same shape as a suite's `provider`). Programmatic use may pass a ready `provider` instead. Exactly one of `judge` and `provider` is required.
- The judge sees the rendered rubric prompt and replies with `{"score": <int>, "reasoning": "..."}`. The score must be on the rubric's scale. A Markdown code fence around the JSON is tolerated; any other text around it is not.
- A reply that is not a valid verdict is retried once. The retry sends the conversation so far, the bad reply, and a message naming the problem. A second invalid reply raises `JudgeError` carrying the raw reply, and the runner records it as an error on that case rather than as a failing score: a judge that could not judge is not evidence the output was bad.
- The judge runs at temperature 0 unless its params say otherwise. Provider-level failures are not retried here; providers already retry transient errors.
- `Score.value` is the raw score (0 or 1, or 1 to N); `passed` is `score >= rubric.threshold`; `reason` is the judge's reasoning.
- `Score` gains an optional `details` mapping. The judge records `judge_model`, `rubric`, `prompt_version`, `scale`, `raw_output` (the accepted reply) and `attempts`. Details are stored with the run and never affect pass or fail.
- Scorers may define `aclose`; the runner calls it when a run ends so a judge's HTTP client is released.

## Consequences

- Judge scoring is only as good as the judge, which is what calibration (a later decision record) measures.
- Rubric paths are resolved against the working directory, not the suite file; running from another directory needs an absolute path.
- Each judged case costs at least one extra model call, two when the first reply is malformed.
