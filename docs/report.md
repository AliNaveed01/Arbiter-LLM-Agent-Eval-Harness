# HTML report

`agentgauge report` turns a stored run into one HTML file you can open, print, attach to a CI job or send to someone who does not have the tool.

```bash
uv run agentgauge run examples/regression/baseline.yaml
uv run agentgauge run examples/regression/candidate.yaml
uv run agentgauge report latest --baseline previous --output report.html
```

A finished example is in [`docs/examples/regression-report.html`](examples/regression-report.html).

## What is in it

- **Summary:** suite, model, run id, start time and duration; counts of passed, failed and errored cases; pass rate, mean latency and cost when there is one.
- **Comparison (with `--baseline`):** the verdict, the change in words, a chart of the pass-rate change with its 95% interval against zero, the metrics table, and the cases that regressed or improved, each linking to its detail. These are the numbers `agentgauge compare` prints; see [regression comparison](regression.md).
- **Cases:** a table with status, scores, latency and the reason for a failure.
- **Case detail:** each case expands to show the output, tool calls, every score with its reason, any error, and for an agent run each step: the model's text, its tool calls, the tool results, and how it ended.

## Options

| Option | Meaning |
| --- | --- |
| `RUN` | A run id, a unique prefix, `latest` or `previous` |
| `--suite NAME` | Resolve `latest` and `previous` among this suite's runs |
| `--output FILE` | Where to write. Default `agentgauge-report-<run id>.html` in the current directory |
| `--baseline RUN` | Also compare `RUN` with this run |
| `--alpha`, `--max-drop`, `--resamples`, `--seed` | The same as for `compare` |
| `--theme auto\|light\|dark` | `auto` follows the reader's system setting |
| `--expand` | Open every case, which suits printing |

`report` exits 0 when it writes the file, even if the comparison shows a regression: the report is for reading and `compare` is the gate. It exits 2 for an unknown or ambiguous run, runs that cannot be compared, or an unusable database.

## Safe to open

Model output is untrusted, so the report never puts it into the page as markup: every value is escaped in one place, and the page carries a Content-Security-Policy that forbids scripts and network requests. The file contains no JavaScript, fonts or images, so it works offline.

## Limits

- The prompt of each case is not stored with a run, so the report shows what the model answered but not what it was asked.
- There is no sorting or filtering in the page, because there is no script. A suite of several hundred cases is a long page.
- Closed case sections do not print; use `--expand` for a printable file.

The design is recorded in [ADR 0018](adr/0018-html-report.md).
