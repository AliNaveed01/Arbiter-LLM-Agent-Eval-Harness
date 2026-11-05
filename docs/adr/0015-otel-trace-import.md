# 15. Importing OpenTelemetry GenAI traces

Date: 2026-11-05

## Status

Accepted

## Context

Teams that already instrument their agents with OpenTelemetry have the trajectory recorded; re-running the agent to score it would be slower, costlier and not the same run. The GenAI semantic conventions are the vendor-neutral way to record it, but they are still in development, so what we read must be small and stated.

## Decision

- `agentgauge import-otel TRACES --suite SUITE` reads OTLP/JSON (`.json`, or `.jsonl` with one export per line), rebuilds one trajectory per trace and scores it with the suite's scorers. The result is stored as an ordinary run, so `runs show --trajectory` works on it.
- Only a documented subset is read: `execute_tool` spans (`gen_ai.tool.name`, `.call.id`, `.call.arguments`, `.call.result`) for the calls, and `chat` spans for the final answer (`gen_ai.output.messages`), token usage and model. Spans are ordered by start time. Everything else is ignored rather than interpreted, so a convention change makes the importer miss data, not invent it.
- The suite case for a trace is named by an `agentgauge.case_id` span attribute. Matching is strict: a trace without it, naming an unknown case, or a second trace for the same case is an error (exit 2), because a silently dropped trace would flatter the results. Suite cases with no trace are left out and counted; traces with no GenAI spans are ignored and counted.
- The tool call, not the model request, is the unit: each `execute_tool` span becomes an assistant message with one call followed by its result. Parallelism recorded in the trace is therefore flattened to start-time order.
- The final answer comes from the latest chat span that carries `gen_ai.output.messages`, not simply the latest span, because an outer chat span can end at the same instant as the inner one that answered.
- Argument and result attributes are opt-in in the conventions because they may hold sensitive data. If a trace lacks them, the importer yields empty arguments (`{}`) and results; argument checks then fail visibly instead of passing vacuously.
- Imported traces are scored and stored but cannot be replayed.

## Carryovers from M2

- `calibrate --fail-under K` exits 1 when kappa is below K or undefined, so calibration can gate a pipeline. Without it a low kappa still only warns (ADR 0012).
- A relative `rubric` file path in an `llm_judge` scorer is resolved against the suite file's directory when the file exists there, otherwise left alone so existing paths relative to the working directory keep working.

## Consequences

- If the GenAI conventions rename an attribute, imports from newer instrumentation lose that field until the importer is updated; the docs name the version-sensitive attributes.
- Latency of an imported trace is wall-clock from the first span's start to the last span's end, which includes any time the agent spent outside model and tool calls.
