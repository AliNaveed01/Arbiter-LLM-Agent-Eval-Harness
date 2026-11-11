# 17. Regression comparison

Date: 2026-11-11

## Status

Accepted

## Context

M4 has to answer "did this change make the agent worse, and is that difference real?" and to fail a pull request only when it did. Suites are small (often 10 to 100 cases), a case either passes or fails, and a model re-run on the same cases changes only a few of them. A raw score difference would fail pull requests on noise, and a rule that never fails would not be a gate.

## Decision

- **Pair the cases.** Two runs are matched by case id. The same case in both runs is one observation, so case difficulty cancels out. Cases only in one run are left out and reported; runs that share no case are refused; repeated case ids are refused. An errored case counts as failed, as everywhere else.
- **Decide with the exact McNemar test on pass/fail.** Only the discordant cases (passed before and failed now, or the reverse) carry information. Under "no difference" each goes either way with probability one half, so the p-value is the doubled lower tail of a binomial with p = 0.5, capped at 1. It is computed exactly with `math.comb`, needs no resampling, and so the decision is deterministic and has no seed. There is no new dependency: the whole test is a few lines, and scipy would be a heavy dependency for one function.
- **Show a bootstrap interval, do not decide with it.** The change in pass rate and in each scorer's mean score gets a seeded percentile bootstrap interval over the per-case differences. It tells the reader how large the change could be. Using both a test and an interval to decide could disagree on the same data, so only the test decides.
- **The verdict has three values.** `regression` when p < alpha (default 0.05) and the pass rate fell by more than `max_drop` (default 0); `improvement` when p < alpha and it rose; otherwise `unchanged`. `max_drop` lets a team accept a real but small drop, such as 2 points, for a cheaper model.
- **Scorer means are informational.** A per-scorer mean score has an interval but does not decide the verdict, because scores differ in scale and meaning and a gate on several of them would need a multiple-comparison correction. The pass rate already reflects every scorer, since a case passes only when all of its scorers pass.
- **Exit codes separate a regression from a broken setup.** `agentgauge compare` exits 0 for no significant regression or an improvement, 1 for a significant regression, and 2 for a configuration problem (unknown or ambiguous run, no shared cases, bad options, unusable database). A CI job can tell "the agent got worse" from "the check did not run".
- **Runs are picked by id, unique prefix, `latest` or `previous`**, optionally within one suite, so a workflow does not need to capture run ids.
- **The GitHub Action is a composite action** that installs `agentgauge-eval`, runs `compare` with markdown output, writes the job summary, and passes the exit code through. Its inputs reach the script as environment variables, never by interpolation into the shell text.

## Consequences

- Significance needs enough discordant cases. With no improvements, six regressions are needed at alpha 0.05 (p = 2/64); five are not enough (p = 0.0625). Each improvement raises the bar: eight regressions against one just pass. A 10-case suite can only catch a collapse.
- The test assumes the cases are an independent sample and that each model run is a single draw. Run-to-run noise of a non-deterministic model is not modelled: two runs of the same model can differ by chance, and McNemar will then see it as a difference. Use temperature 0 and a seed, and expect occasional false alarms otherwise (about one in twenty comparisons of identical models at alpha 0.05).
- Comparing many suites or many pairs of runs multiplies the chance of a false alarm; the tool does not correct for that.
- A gate on pass rate alone does not see a drop in a scorer that does not change which cases pass. The scorer rows are there to show it.
