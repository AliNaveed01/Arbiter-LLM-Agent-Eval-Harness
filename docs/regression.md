# Regression comparison

`agentgauge compare` answers: did this change make my agent worse, and is that difference real?

```bash
uv run agentgauge run examples/regression/baseline.yaml
uv run agentgauge run examples/regression/candidate.yaml
uv run agentgauge compare previous latest
```

```text
agentgauge compare: REGRESSION  suite capitals
Pass rate fell from 100.0% to 41.7% (-58.3 points, 95% interval -83.3 to -33.3 points) over 12
paired case(s); exact McNemar p = 0.0156.
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Metric           ┃ Baseline ┃ Candidate ┃ Change (95% interval)         ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ pass rate        │ 100.0%   │ 41.7%     │ -58.3 points (-83.3 to -33.3) │
│ exact_match mean │ 1.000    │ 0.417     │ -0.583 (-0.833 to -0.333)     │
└──────────────────┴──────────┴───────────┴───────────────────────────────┘
Regressed (7): japan, canada, egypt, norway, kenya, chile, greece
A regression needs p < 0.05 and a drop of more than 0 points in pass rate.
```

## Choosing the runs

Each argument is a run id, a unique prefix of one, `latest` (the newest stored run) or `previous` (the one before it). `--suite NAME` restricts `latest` and `previous` to that suite's runs. `--db` picks the database, as for every command.

## How to read it

- **The runs are paired by case id.** The same case in both runs is one observation, so an easy case that always passes does not dilute the result. Cases in only one run are left out and listed as a note; runs with no case in common are an error.
- **The verdict comes from the exact McNemar test** on pass/fail. It looks only at the cases whose outcome changed: passed then failed ("Regressed") and failed then passed ("Improved"). If the changes are about evenly split, nothing is flagged; if nearly all go one way, the p-value is small.
- **The interval shows how big the change could be.** It is a seeded bootstrap interval (95%) over the per-case differences. It does not decide the verdict. A wide interval means the suite is too small to say much.
- **A regression** is p below `--alpha` (default 0.05) and a pass-rate drop larger than `--max-drop` (default 0). Set `--max-drop 0.02` to accept a real but small drop of 2 points. **An improvement** is the same test in the other direction. Everything else is "No significant change".
- **Scorer rows** give each scorer's mean score and an interval over the cases both runs scored. They are informational: only the pass rate decides.

## How many cases you need

Significance needs enough cases that changed. With no improvements at all, six regressions are enough at alpha 0.05 and five are not (p = 0.0625); with one improvement you need eight. A suite of ten cases can only catch a collapse, and a suite of a hundred can catch a few points. If you see "No significant change" on a small suite, that is not evidence the agent is unchanged.

## Output and exit codes

`--format markdown` prints a GitHub-flavoured report, `--format json` the whole comparison including the verdict, and `--output FILE` writes either to a file instead.

| Exit code | Meaning |
| --- | --- |
| 0 | No significant regression (including an improvement) |
| 1 | A significant regression |
| 2 | The comparison could not be made: unknown or ambiguous run, no shared cases, bad options, unusable database |

## In CI

The [`action.yml`](../action.yml) at the root of this repository wraps `compare` as a GitHub Action: it installs `agentgauge-eval`, writes the markdown report to the job summary, and fails the job only on exit code 1; a setup problem (exit code 2) fails with a different message. [`examples/github-action/regression.yml`](../examples/github-action/regression.yml) shows the whole workflow: run the suite on the base branch and on the pull request into one database, then compare `previous` with `latest`. Pin the action to a release tag that contains `action.yml`; `@main` is for trying it out.

## Limits

- The test assumes the cases are an independent sample and each run is a single draw. A model that is not deterministic changes some cases between two identical runs, and that looks like a difference. Use temperature 0 and a seed, and expect an occasional false alarm otherwise: about one comparison in twenty between identical models at alpha 0.05.
- Comparing many suites, or many pairs of runs, multiplies the chance of a false alarm. There is no correction for it.
- The decision uses pass rate. A drop in a scorer's mean that does not change which cases pass shows in the scorer rows and does not fail the job.

The design is recorded in [ADR 0017](adr/0017-regression-comparison.md).
