# agentgauge

agentgauge is an open-source regression-testing harness for LLM agents. It answers one question: did this change make my agent better or worse, and is that difference real? It calibrates its LLM judge against human labels, gates CI on bootstrap confidence intervals rather than raw score diffs, and scores tool-call trajectories as well as final answers.

**Status: pre-alpha**

**What works today:** define a suite of test cases in YAML or JSONL, run it against any OpenAI-compatible model, score it with deterministic scorers, an LLM judge calibrated against human labels, and tool-call trajectory scorers, store and inspect the runs, import OpenTelemetry traces, compare two runs with a significance test, locally or as a GitHub Action, and write a run as an HTML report. **Not built yet:** the docs site, the demo GIF and a worked example on a real agent (v1.0).

## Quickstart

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/). Install it from PyPI (the package is `agentgauge-eval`, the command is `agentgauge`):

```bash
uv tool install agentgauge-eval
agentgauge --help
```

To run the bundled example, work from a clone:

```bash
git clone https://github.com/AliNaveed01/agentgauge.git
cd agentgauge
uv sync
uv run agentgauge run examples/basic/suite.yaml
```

The example runs against a scripted fake model, so it works offline with no API key. You should see something like this (the run id and time will differ):

```text
Run 99d30193  suite basic  model scripted-demo  started 2026-11-03 12:48:02 UTC
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Case              ┃ Result ┃ Scores           ┃ Latency ┃ Detail                           ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ arithmetic        │ PASS   │ exact_match=pass │    0 ms │                                  │
│ capital-france    │ PASS   │ exact_match=pass │    0 ms │                                  │
│ capital-australia │ FAIL   │ exact_match=fail │    0 ms │ exact_match: expected 'Canberra' │
│ gold-symbol       │ PASS   │ exact_match=pass │    0 ms │                                  │
└───────────────────┴────────┴──────────────────┴─────────┴──────────────────────────────────┘
3/4 passed, 1 failed, 0 errors, cost $0.0000, took 0.00s
Stored as run 99d30193 in .agentgauge/runs.db
```

One case fails on purpose: the scripted model says Sydney, the suite expects Canberra. Look at what was stored:

```bash
uv run agentgauge runs list              # newest first
uv run agentgauge runs show 99d30193     # one run in detail, with each case's output
```

`runs show` accepts any unique prefix of a run id. Runs are stored in `.agentgauge/runs.db` in the current directory; use `--db PATH` or the `AGENTGAUGE_DB` environment variable to put them elsewhere.

## Writing a suite

A suite is a YAML file with a name, the model to run against, the scorers to apply and the cases:

```yaml
name: my-suite
provider:
  type: openai_compat            # any OpenAI-compatible endpoint
  model: my-model
  base_url: http://localhost:8000/v1   # omit for api.openai.com
  api_key_env: MY_API_KEY        # name of the environment variable; never put keys in the file
  params: {temperature: 0}
scorers:
  - exact_match
  - name: numeric_tolerance      # scorers with settings use the long form
    params: {abs_tol: 0.01}
cases:
  - id: add
    input: "What is 2 + 2?"      # a string, or a list of {role, content} messages
    expected: "4"
```

Every scorer runs on every case. Suites can also be JSONL, one case per line (`{"id": "add", "input": "What is 2 + 2?", "expected": "4"}`); since there is nowhere to put a `provider` or scorers there, pass them on the command line.

| Scorer | Passes when |
| --- | --- |
| `exact_match` | the output equals `expected` (params: `case_sensitive`, `strip`) |
| `contains` | the output contains `expected` (param: `case_sensitive`) |
| `regex` | the output matches `pattern`, or `expected` if no pattern is given (params: `pattern`, `ignore_case`, `full`) |
| `numeric_tolerance` | the first number in the output is within `abs_tol` or `rel_tol` of the number in `expected` |
| `json_schema` | the output is JSON that satisfies `schema` (a documented subset of JSON Schema) |
| `llm_judge` | a judge model scores the output against a rubric (params: `rubric`, `judge`, `cache`); see below |
| `tool_call` | the model made exactly the expected tool call (arguments compared case-insensitively), or none when none is expected |
| `trajectory_match` | an agent's tool-call sequence matches `expected_trajectory` (`exact`, `in_order` or `any_order`); see [docs/trajectories.md](docs/trajectories.md) |
| `trajectory_budget` | an agent finished within `max_calls` tool calls |

## Judging with a model, and checking the judge

`llm_judge` asks a model to grade each output against a rubric. A judge is only worth trusting once it has been checked against human labels, so agentgauge ships the check:

```bash
uv run agentgauge calibrate examples/judge/suite.yaml --labels examples/judge/labels.yaml
```

It reports accuracy, Cohen's kappa with a bootstrap interval, a confusion matrix and per-class precision and recall, and warns when kappa is below 0.6. The example uses a scripted judge, so it runs offline. [docs/calibration.md](docs/calibration.md) explains how to read the report.

## Agents and traces

With an `agent` block a suite runs each case as a multi-step tool loop against scripted tools, and the trajectory scorers judge the route, not just the answer. `agentgauge import-otel` scores traces recorded elsewhere, from OpenTelemetry GenAI spans:

```bash
uv run agentgauge run examples/agent/suite.yaml
uv run agentgauge runs show <run id> --trajectory
uv run agentgauge import-otel examples/otel/traces.json --suite examples/otel/suite.yaml
```

See [docs/trajectories.md](docs/trajectories.md).

## Comparing runs

`agentgauge compare` pairs two runs by case, tests whether the pass rate really dropped (exact McNemar test), and exits 1 only on a significant regression, so it can gate a pull request:

```bash
uv run agentgauge run examples/regression/baseline.yaml
uv run agentgauge run examples/regression/candidate.yaml
uv run agentgauge compare previous latest
```

See [docs/regression.md](docs/regression.md) for how to read it, how many cases you need, and the GitHub Action ([`action.yml`](action.yml), [example workflow](examples/github-action/regression.yml)).

## HTML report

`agentgauge report` writes a stored run as one self-contained HTML file, with the comparison against a baseline if you ask for it. It needs no network, contains no scripts, and escapes everything the model said:

```bash
uv run agentgauge report latest --baseline previous --output report.html
```

See [docs/report.md](docs/report.md) and the [example report](docs/examples/regression-report.html).

## Running against a real model

Command-line options override the suite's `provider` block, so you can point the example at a real model:

```bash
export OPENAI_API_KEY=...
uv run agentgauge run examples/basic/suite.yaml --provider openai_compat --model <model-name>
```

For a local server, add `--base-url http://localhost:8000/v1`; no key is needed. Use `--concurrency N` to limit how many cases run at once (default 8).

## Exit codes

`run` exits 0 whenever the run completes, even if cases fail or error: those are shown in the table. It exits 2 for configuration problems (unreadable or invalid suite, unknown scorer, bad provider options, a missing API key variable, an unusable database). `runs show` exits 1 for an unknown or ambiguous run id. `calibrate --fail-under` exits 1 when kappa is below the threshold. `compare` exits 0 when there is no significant regression, 1 on a significant regression, and 2 when the comparison cannot be made (unknown or ambiguous run, no shared cases, bad options, unusable database).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Design decisions are recorded in [docs/adr](docs/adr).

## License

Apache-2.0. See [LICENSE](LICENSE).
