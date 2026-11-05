# 13. Tool-use benchmark

Date: 2026-11-05

## Status

Accepted

## Context

We want numbers for how small local models behave as agents and as judges, on the author's own hardware, using agentgauge itself. Multi-turn agent trajectories are a later milestone, so the benchmark has to measure what the current library can: single-step tool use and judging.

## Decision

- A `Suite` has `tools`, offered to the model on every case. The runner passes them in the `CompletionRequest`.
- The `tool_call` scorer reads the expectation from `case.metadata["expected_tool_call"]`: `{name, arguments}` for a required call, `null` for "must not call a tool". Exactly one call is required when one is expected. String arguments compare ignoring case and edge whitespace; everything else compares exactly. Arguments that are not a JSON object are reported as `malformed_arguments`; they are never repaired. Each score records an `outcome` (`ok`, `no_call`, `unexpected_call`, `extra_calls`, `wrong_tool`, `wrong_arguments`, `malformed_arguments`).
- The benchmark has two parts, run from `benchmarks/run_benchmark.py` (a script, not part of the installed package):
  - **Tool use**: twelve prompts and three tools. Nine need one specific call, three need none. *Agent pass rate* is the share of all twelve that pass. *Tool-call accuracy* is the share of the nine that pass. The gap between them is restraint.
  - **Judging**: thirty fixed question and answer pairs with human verdicts (15 correct, 15 wrong), judged by the model under test through `llm_judge` with a binary factual-accuracy rubric. Reported as Cohen's kappa against the human labels with the seeded 95% bootstrap interval.
- Everything runs at temperature 0 with a fixed seed (42) and `max_tokens` 2048, one case at a time, so latency is not distorted by concurrency. The judge cache is off so latency is real.
- A malformed response is a result. A tool call the adapter cannot parse is recorded as an error on the case, an empty reply as `no_call`, an invalid judge verdict as a judging problem. Nothing is retried or repaired beyond the judge's single built-in retry; a judge that returns invalid verdicts is judged on the cases it did answer, and the count is reported.
- Hardware (architecture, chip, RAM), the server version and the model size are recorded with the numbers.

## Consequences

- "Agent" here means one decision, not a loop. The numbers say nothing about multi-step planning or recovery.
- Twelve tool cases and thirty judge cases are small. Percentages move by 8 and 3 points per case, and the kappa interval is wide. Treat the results as a smoke test and a comparison between models, not as a leaderboard.
- Temperature 0 with a seed makes a run repeatable on the same machine and server version; it does not promise identical output across hardware or versions.
- A model that emits reasoning instead of content, or hides its tool call somewhere the OpenAI-compatible response does not carry it, will score zero. That is the intended behaviour: it is what a user of that endpoint would see.
