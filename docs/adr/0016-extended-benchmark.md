# 16. Extended benchmark: thinking switch, loop suite, chart

Date: 2026-11-10

## Status

Accepted. Extends [ADR 0013](0013-tool-use-benchmark.md).

## Context

The first benchmark ran one model with its default behaviour and measured single decisions. Two questions were left open: whether the model's reasoning mode explains its empty tool-call replies, and whether single-decision accuracy predicts behaviour in the multi-step loop added in M3.

## Decision

- **Thinking switch.** `ProviderConfig` and `OpenAICompatProvider` take an `extra_body` mapping that is merged into every request. A key the adapter sets itself (model, messages, temperature and so on) may not be overridden; that raises a `ProviderError` instead of changing the experiment silently. The benchmark's `--thinking off` sends `{"reasoning_effort": "none"}`.
- **Why `reasoning_effort` and not `think`.** Measured against Ollama 0.40.14: on `/v1/chat/completions`, `"think": false` is ignored (reasoning text still came back and `content` was empty), while `"reasoning_effort": "none"` removed the reasoning and returned the answer. The native `/api/chat` honours `"think": false` with the same effect. Qwen3's `/no_think` prompt suffix was also ignored on the OpenAI endpoint. So `reasoning_effort: "none"` is the OpenAI-compatible equivalent of `think: false`, and the results record which one was sent.
- **It does not work on every model.** On `qwen3:4b` no switch removed the reasoning: `reasoning_effort: "none"` and the native `think: false` both returned empty `reasoning` but the model then reasoned in `content` instead (the reply began "Okay, the user asked...", with a literal `</think>` in some replies), `"think": false` on `/v1` was ignored, and a `/no_think` suffix or system message only shortened it. The 4b "thinking off" row therefore records what an application would receive when it asks for thinking off, not a model that stopped thinking. It is reported as a finding and not worked around.
- **Loop suite.** `benchmarks/data/agent_loop_suite.yaml` has eight tasks run through the agent loop with scripted tool results (`tool_mocks`): independent calls, calls that depend on an earlier result, a conditional that must not fire, and a task needing no tool. Scored by `trajectory_match` in `exact` mode plus `trajectory_budget` (at most three calls, must finish). The mocks make the model the only variable.
- **Result files.** One JSON per model and thinking mode, named `<model>-thinking-on|off.json`. The first benchmark's `qwen3-0.6b.json` is kept as it was, and charted as its own row ("first run"), so a repeat with the same settings is visible next to the original.
- **Chart.** `scripts/plot_kappa.py` draws kappa with its interval per model and mode from the result files, with matplotlib, a dev-only dependency never imported by the package. The PNG is committed with the script.

## Consequences

- `extra_body` is a general escape hatch for server-specific options; it is not validated against any server, so a wrong key is the server's problem to reject or ignore. The benchmark checks that the option worked by comparing outputs, not by trusting the request.
- The loop suite has eight tasks and canned tool results. It measures route-following in a clean setting, not recovery from tool errors or real tool behaviour.
- Runs are repeatable within a session but not guaranteed across days: the first benchmark and its re-run on the same settings differ on a few cases. Differences of one or two cases between rows are within that noise.
