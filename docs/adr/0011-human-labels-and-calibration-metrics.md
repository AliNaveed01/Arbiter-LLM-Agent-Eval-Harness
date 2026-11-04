# 11. Human labels and calibration metrics

Date: 2026-11-04

## Status

Accepted

## Context

A judge is only useful if its scores track a human's. Calibration measures that on a labelled sample. The metrics are small enough to implement directly, and the project avoids dependencies it does not need.

## Decision

Labels
- A label is `case_id`, an integer `label` on the rubric's scale, and an optional `annotator`. Files are YAML (a list, or a mapping with a `labels` list) or JSONL. `true`/`false` and `pass`/`fail` are accepted for binary labels. Floats and strings such as `"3"` are rejected: a label is a score, not a measurement.
- Errors carry `file:line`, sharing the YAML helpers with the suite and rubric loaders.
- A `case_id` may appear once. `annotator` is recorded but not used: comparing several annotators, or adjudicating between them, is out of scope. Teams with several annotators merge them first.

Metrics (pure Python, no new dependencies)
- Functions take two integer score sequences and the scale's full list of classes, so confusion matrices keep their shape even when a small sample misses a class.
- The confusion matrix has a row per human score and a column per judge score. Precision and recall treat the human as truth, and are `None` rather than 0 when the ratio is undefined.
- Cohen's kappa is computed as one minus observed over expected weighted disagreement. Ordinal scales use quadratic weights, binary scales plain ones; the two coincide for two classes. Kappa is `None` when expected disagreement is zero, which means both raters used a single score throughout and agreement carries no information. Reporting 1.0 or 0.0 there would be a guess.
- The kappa interval is a percentile bootstrap: 1000 resamples of cases with replacement from `random.Random(seed)`, seed 0 by default, 95% by default. Resamples where kappa is undefined are skipped. The result is reproducible, and a golden-value test pins the algorithm so any change to it is deliberate.
- `calibrate()` bundles all of this into a frozen `CalibrationReport`.

## Consequences

- Kappa on a handful of cases is unstable; the interval makes that visible rather than hiding it.
- Percentile bootstrap is simple but can be too narrow on very small samples; it is a guide, not a guarantee.
- The 0.6 trust threshold used by the CLI is a convention from the agreement literature, not a law; the report shows the numbers so a reader can judge.
