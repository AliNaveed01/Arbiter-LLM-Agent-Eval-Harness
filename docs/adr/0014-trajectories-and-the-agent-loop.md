# 14. Trajectories and the agent loop

Date: 2026-11-05

## Status

Accepted

## Context

Single-decision scoring cannot tell whether an agent took the right route: which tools, in what order, with what arguments, and whether it stopped. Milestone 3 adds a multi-step tool loop and scorers over the resulting sequence.

## Decision

- A `Trajectory` is the `assistant` and `tool` messages produced while the agent ran, plus a `stop_reason` (`final` or `max_steps`). It reuses `Message`, so the same data is what gets sent back to the provider on each step and what OpenTelemetry traces are converted into. `tool_calls` and `steps` are derived, not stored.
- `ModelOutput.trajectory` is optional. For an agent run `text` is the final answer, and latency, token counts and cost are summed over steps, so existing reporting stays meaningful. Scorers keep the `score(case, output)` signature; trajectory scorers read `output.trajectory`.
- An agent run is opt-in: a suite with an `agent` block (`max_steps`, default 8) runs each case as a loop. Suites without it behave as before, including a single tool-call decision per case.
- Tools are not executed. `tool_mocks` script their results: a mock matches on tool name and, optionally, arguments (strings compared ignoring case and edge whitespace); the first match wins. A call nothing matches, or whose arguments are not a JSON object, gets an `error:` result that the model sees, rather than aborting the run. That keeps runs deterministic and offline, and the model's reaction to an error is itself part of what is being tested. Real tool execution is out of scope.
- The loop ends when the model answers without a tool call, or after `max_steps` model calls (`stop_reason: max_steps`). A provider error inside the loop fails the case, as it does elsewhere.
- `trajectory_match` compares the call sequence with `case.metadata["expected_trajectory"]` in `exact`, `in_order` (default) or `any_order` mode, with optional argument checking, and scores the fraction of expected calls matched. `trajectory_budget` passes when the number of calls is within a limit and the agent finished.
- Argument comparison is shared with the `tool_call` scorer.

## Consequences

- Tool results are canned, so a model that would have chosen differently given a real result is not tested. Mocks can still model failures, empty results and changes of plan.
- Parallel tool calls in one step are answered in order and appear in order in the trajectory; `in_order` treats them as sequential.
- Greedy matching is exact for equality-based comparison but is not a general alignment algorithm; `trajectory_match` does not award partial credit for near-miss arguments.
