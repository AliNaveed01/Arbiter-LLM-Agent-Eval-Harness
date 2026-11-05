# Benchmarks: small local models as agents and as judges

What happens when you point agentgauge at a small model on a laptop: can it pick the right tool, and can it be trusted to grade answers? Measured on 2026-11-05 against a local [Ollama](https://ollama.com) server through its OpenAI-compatible endpoint.

## Results

| Model | Size | Kappa (95% CI) | Agent pass rate | Tool-call accuracy | Mean latency |
| --- | --- | --- | --- | --- | --- |
| qwen3:0.6b | 522 MB | 0.07 (-0.28 to 0.41) | 83% (10/12) | 78% (7/9) | 778 ms |

- **Kappa** is the model acting as judge on 30 answers a human labelled (see [calibration](../calibration.md)). agentgauge warns below 0.6.
- **Agent pass rate** is the share of 12 prompts handled correctly: 9 that need one specific tool call, and 3 where the right move is to call nothing.
- **Tool-call accuracy** is the share of the 9 that need a call where the model made exactly the right call with the right arguments.
- **Mean latency** is per case over the 12 tool-use prompts, run one at a time.

`qwen3:4b` was not run: `ollama list` showed only `qwen3:0.6b`, and the task was to run it only if installed.

## Interpretation

1. As a single-step tool user the 0.6B model is serviceable: 7 of 9 calls were exactly right, it never reached for a tool when none was needed (3 of 3), and it answered in under a second.
2. As a judge it is not usable: kappa 0.07 with an interval of -0.28 to 0.41 is indistinguishable from chance, and it agreed with the human label only 16 times in 30. Doing a task and grading it are different skills.
3. These are small samples (12 and 30 cases; one tool case moves the pass rate by 8 points) on one model, so read them as a smoke test, not a ranking; there is no larger model here to compare against.

## Findings

**Empty replies instead of tool calls (2 of 9 tool cases).** For "What is the weather in Paris right now?" and the Tokyo prompt, the endpoint returned `finish_reason: stop`, empty `content` and no `tool_calls`. The model's `reasoning` field says it will call `get_weather` with the city, but the call never reaches the response. agentgauge scores this as `no_call`, which is what an application calling this endpoint would see. It is not worked around: the adapter does not read `reasoning`, and a call written only in reasoning text is not a tool call. The third weather prompt, Lima, worked, so the failure is prompt-dependent rather than systematic.

**No malformed tool calls.** Every call that was returned parsed: no response was rejected by the adapter and no call had arguments that were not a JSON object. The `malformed_arguments` and `malformed_response` counts are zero.

**Judge verdicts were all valid, and still unreliable.** All 30 judge replies were valid verdicts; none was an error. The model called 19 of the 30 answers wrong, 9 of them human-correct. Confusion matrix (rows human, columns judge): wrong answers 10 judged wrong and 5 judged correct; correct answers 9 judged wrong and 6 judged correct.

**Reproducibility.** Two runs with the same settings gave identical outcomes for every case and an identical judge result. The raw outputs were not byte-identical: tool-call ids are random, and for one case the arguments came back with the keys in a different order (`{"to":"JPY","amount":250,"from":"GBP"}` against `{"amount":250,"from":"GBP","to":"JPY"}`). The scorer compares parsed arguments, so scores were not affected. Latency varied between runs (778 ms and 740 ms).

## How it was run

| | |
| --- | --- |
| Machine | arm64, Apple M2 Pro, 16 GB RAM |
| Server | ollama version is 0.40.14 |
| Endpoint | `http://localhost:11434/v1` (OpenAI-compatible) |
| Sampling | temperature 0, seed 42, max_tokens 2048 |
| Execution | one case at a time; judge cache off |
| Python | 3.12.13 |

```bash
ollama pull qwen3:0.6b
uv run python benchmarks/run_benchmark.py --model qwen3:0.6b --out docs/benchmarks/results/qwen3-0.6b.json
```

The script is [`benchmarks/run_benchmark.py`](../../benchmarks/run_benchmark.py), the data is in [`benchmarks/data/`](../../benchmarks/data/), and the raw per-case results, including every tool call the model made, are in [`results/qwen3-0.6b.json`](results/qwen3-0.6b.json). The design is recorded in [ADR 0013](../adr/0013-tool-use-benchmark.md).

## Limits

- One decision per prompt: this is not a multi-step agent loop, so it says nothing about planning or recovering from errors.
- Twelve tool cases and thirty judge cases are small, and the judge set is easy general knowledge.
- Results hold for this machine, this Ollama version and this model build. Change any of them and re-run.
