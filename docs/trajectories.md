# Trajectories: scoring how an agent got there

A final answer can be right for the wrong reasons, or wrong because of one bad step. A trajectory is the record of what an agent did: each model step, the tool calls it made with their arguments, and the results it was given. agentgauge can run an agent loop against scripted tools, score the sequence of tool calls, and import traces recorded elsewhere through OpenTelemetry.

## Running an agent

Add an `agent` block to a suite and each case runs as a loop instead of a single model call:

1. The model is asked, with the suite's `tools`.
2. If it replies with tool calls, each is answered from the suite's `tool_mocks` and the results go back to the model.
3. The loop ends when the model replies without a tool call, or after `max_steps` model calls (default 8).

Tools are not executed. A mock matches a call by tool name and, optionally, arguments (strings compared ignoring case and edge whitespace); the first match wins. A call that no mock answers, or whose arguments are not a JSON object, gets an `error:` result that the model sees, so how a model reacts to a failing tool is part of what you test.

The output carries the final answer, with latency, token counts and cost summed over the steps, and the trajectory. The runs database stores it, and `runs show --trajectory` prints it:

```bash
uv run agentgauge run examples/agent/suite.yaml
uv run agentgauge runs show <run id> --trajectory
```

```text
book-cheapest  3 step(s), 2 tool call(s), stopped: final
   1  call       search_flights {"origin": "Oslo", "destination": "Rome"}
      result     FL100 $200 (nonstop); FL200 $350 (one stop)
   2  call       book_flight {"flight_id": "FL100"}
      result     Confirmed: FL100
   3  assistant  Booked FL100 for $200.
never-finishes  4 step(s), 4 tool call(s), stopped: max_steps
```

`examples/agent/suite.yaml` scripts its "model" with a fake provider: a response can be a list, and the n-th item answers the n-th step. With a real model you set `provider` as usual and the same suite applies.

## Scoring the route

| Scorer | Passes when |
| --- | --- |
| `trajectory_match` | the agent's tool calls match `metadata.expected_trajectory`, a list of `{name, arguments}`. `mode: exact` needs the same calls in the same order and no extras; `in_order` (default) needs the expected calls in order, extras allowed between; `any_order` needs every expected call, in any order. `check_args: false` compares names only. |
| `trajectory_budget` | the agent made at most `max_calls` tool calls and finished (`require_final: false` drops that condition) |

`trajectory_match` scores the fraction of expected calls it found (1 or 0 for `exact`) and passes only when all were found. Both fail with a clear reason if the output has no trajectory, for example when the suite has no `agent` block.

## Importing OpenTelemetry traces

If your agent already emits OpenTelemetry GenAI spans, score what it actually did instead of re-running it:

```bash
uv run agentgauge import-otel examples/otel/traces.json --suite examples/otel/suite.yaml
```

The file is OTLP/JSON: one export document (`.json`), or one export per line (`.jsonl`). Each trace becomes one case, matched to the suite by an `agentgauge.case_id` attribute on any of its spans (add it as a span attribute in your instrumentation, or in the collector). The suite's scorers then run on the rebuilt trajectory and the result is stored like any other run.

What is read, from the [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (status: development at the time of writing, so names may change):

| Span | Attribute | Used for |
| --- | --- | --- |
| `gen_ai.operation.name` = `execute_tool` | `gen_ai.tool.name` (required) | the tool call's name |
| | `gen_ai.tool.call.id` | the call id (otherwise `span_<spanId>`) |
| | `gen_ai.tool.call.arguments` | arguments, as a JSON string or a structured value |
| | `gen_ai.tool.call.result` | the result the agent received |
| `gen_ai.operation.name` = `chat` | `gen_ai.output.messages` | the final answer: the text parts of the last message of the latest chat span that has the attribute |
| | `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | summed |
| | `gen_ai.response.model` or `gen_ai.request.model` | the run's model name |

Spans are ordered by start time, and latency is the time from the first span's start to the last span's end. Traces with no `chat` or `execute_tool` span are ignored and counted. A trace with no `agentgauge.case_id`, one naming a case that is not in the suite, or two traces for one case, is an error: matching is strict so a typo cannot silently drop a trace. Suite cases with no trace are left out of the run and counted.

`gen_ai.tool.call.arguments`, `.result` and `gen_ai.output.messages` are opt-in in the conventions, because they can contain sensitive data. If your instrumentation does not record them, argument checks and the final answer have nothing to work with.

## Limits

- Tool results are canned. A model that would have chosen differently given a real result is not tested, though mocks can model failures and empty results.
- `trajectory_match` compares tool calls only; it does not judge the model's intermediate text, and it gives no partial credit for near-miss arguments.
- The importer reads the subset above. Span events, multi-choice responses and other span shapes are ignored, not interpreted.
- Imported traces carry no tool descriptions or provider settings, so they can be scored but not replayed.
