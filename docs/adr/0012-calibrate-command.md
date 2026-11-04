# 12. The calibrate command

Date: 2026-11-04

## Status

Accepted

## Context

Calibration ties the judge scorer, the human labels and the metrics together. The command should be cheap to repeat while someone tunes a rubric, and it should be hard to read a flattering number off a broken setup.

## Decision

- `agentgauge calibrate SUITE --labels FILE` runs the suite's judge scorer, selected by `--scorer` (default `llm_judge`), on the labelled cases only, then compares the judge's scores with the labels. The model under test and the judge are configured exactly as for `run`, including the provider override options.
- Only labelled cases are run, which saves model and judge calls. Unlabelled cases are counted in the report rather than silently dropped.
- Exactly one scorer of that name must exist in the suite. Several judges in one suite are calibrated one at a time by giving them different suites or by naming them; running two in one report would hide which is which.
- Labels naming cases that are not in the suite, or lying off the judge's scale, are configuration errors (exit 2): a typo should not shrink the sample unnoticed. Cases where the judge errored are skipped and listed by id. If none could be judged the command exits 1.
- The scale is taken from the `details` the scorer recorded, so calibration needs no second copy of the rubric and works with any scorer that reports a `scale`. A scorer that does not is rejected with a clear message.
- Nothing is written to the run database; judge replies are cached, so repeated calibration is free until the judge or prompt changes.
- Kappa below 0.6, or undefined, prints a warning that the judge is not trustworthy against these labels. The command still exits 0: calibration reports a measurement, and a gate on it belongs in CI configuration, not in the command.
- The report prints accuracy, kappa with its weighting and 95% interval, the confusion matrix, and per-class precision and recall.

## Consequences

- Exit code 0 with a warning can be missed in a script; reading the output, or a later `--fail-under` option, is the remedy.
- The bootstrap seed is fixed in the CLI (0), so the same inputs always print the same interval.
- Calibration measures agreement with the supplied labels only. A judge that agrees with careless labels is still wrong.
