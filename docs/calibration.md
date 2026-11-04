# Calibrating an LLM judge

An LLM judge is a model grading another model's output. It is convenient, and it is a measuring instrument that nobody has checked. Calibration is the check: score a sample of cases with the judge, have a person score the same cases, and measure how closely they agree. If they agree, you can use the judge on cases nobody has time to read. If they do not, its scores are noise with a confident tone.

agentgauge does not trust a judge until you have calibrated it. `agentgauge calibrate` runs the check and warns when the numbers say the judge is not trustworthy.

## The workflow

1. **Write a rubric.** Say what good means as one or more criteria, and pick a scale: binary (0 or 1) or ordinal (1 to N). A rubric is part of a suite's `llm_judge` scorer, inline or in its own YAML file.
2. **Label a sample by hand.** Pick cases that include the hard and borderline ones, not only the obvious ones. Write the verdicts in a labels file.
3. **Run `agentgauge calibrate`.** Read the report.
4. **Fix the judge until the numbers hold up.** Sharpen the criteria, bump the prompt version, or try a stronger judge model, and calibrate again.
5. **Only then** use the judge in regular runs.

Judge replies are cached (see below), so step 4 costs nothing for the cases whose prompt did not change.

## Labels

A labels file is YAML or JSONL, one label per case:

```text
- case_id: capital-france
  label: 1
  annotator: ana        # optional
```

`label` is an integer on the rubric's scale. For a binary rubric `true`/`false` and `pass`/`fail` also work. A case appears once. Mistakes are reported with the file and line, for example `labels.yaml:4: label: Input should be a valid integer`.

Cases without a label are ignored, and only labelled cases are run, so you can label a subset of a large suite. Labels for cases that are not in the suite, or outside the rubric's scale, are errors: a typo should not quietly shrink your sample.

## Reading the report

```bash
agentgauge calibrate examples/judge/suite.yaml --labels examples/judge/labels.yaml
```

```text
calibration of judge-demo  judge scripted-judge
cases compared          12
accuracy                0.83
kappa (none weighting)  0.62  (95% CI 0.00 to 1.00)
    Confusion matrix
┏━━━━━━━━━━━━━━━┳━━━┳━━━┓
┃ human \ judge ┃ 0 ┃ 1 ┃
┡━━━━━━━━━━━━━━━╇━━━╇━━━┩
│ 0             │ 3 │ 1 │
│ 1             │ 1 │ 7 │
└───────────────┴───┴───┘
    Per class (human label is truth)
┏━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━┓
┃ score ┃ support ┃ precision ┃ recall ┃
┡━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━┩
│     0 │       4 │      0.75 │   0.75 │
│     1 │       8 │      0.88 │   0.88 │
└───────┴─────────┴───────────┴────────┘
```

**Accuracy** is the share of cases where the judge gave the same score as the human. It is easy to read and easy to be fooled by: a judge that says "pass" to everything is 90% accurate on a suite where 90% of answers are good.

**Cohen's kappa** corrects for that. It measures agreement beyond what you would get if the judge and the human each used their scores at their usual rates but independently of each other. 1 is perfect agreement, 0 is no better than chance, negative is worse than chance. A common reading is:

| kappa | agreement |
| --- | --- |
| below 0.4 | poor |
| 0.4 to 0.6 | moderate |
| 0.6 to 0.8 | substantial |
| above 0.8 | almost perfect |

agentgauge warns when kappa is **below 0.6**: below that the judge is not trustworthy and you should not rely on its scores. The threshold is a convention, not a law; the numbers are printed so you can judge for yourself.

**Weighting.** For an ordinal rubric kappa is *quadratic-weighted*: a 4 against a 5 counts as a small disagreement and a 1 against a 5 as a large one, in proportion to the squared distance. Unweighted kappa would treat both as equally wrong. Binary rubrics use plain kappa; the two are identical for two classes. The report says which was used.

**The 95% interval** is a bootstrap: the report resamples your labelled cases with replacement a thousand times and recomputes kappa each time. The interval above, 0.00 to 1.00, is the honest answer to "how much does twelve cases tell you?": not much. A kappa of 0.62 from twelve cases could easily be 0.3 or 0.9 on another twelve. The resampling uses a fixed seed, so the same inputs always print the same interval. More labelled cases narrow it.

**Kappa can be undefined.** If the judge and the human each used a single score for every case, chance agreement is already total and kappa has no meaning. The report says "undefined" and still warns, because a sample like that cannot show the judge is trustworthy.

**The confusion matrix** shows where the disagreements are: rows are the human's score, columns the judge's. Off-diagonal cells are errors. Here the judge was too strict once (human 1, judge 0) and too lenient once (human 0, judge 1).

**Per-class precision and recall** treat the human as truth. For class 1, recall is the share of human "1"s the judge also called 1; precision is the share of the judge's "1"s the human agreed with. A lenient judge has low precision on "pass". A value is `n/a` when it is undefined, for example precision for a score the judge never gave.

## Using a judge

```bash
agentgauge run suite.yaml
```

A suite uses the judge as a scorer. In the example, the `llm_judge` scorer takes a `rubric` and a `judge` (a provider block like a suite's own `provider`):

- The judge is asked for `{"score": <int>, "reasoning": "..."}`. A reply that is not a valid verdict is retried once, with the problem pointed out. After a second bad reply the case is recorded as an error, not as a failing score.
- Every score records the judge model, the prompt version, the raw reply and whether it came from the cache, so a surprising score can be traced.
- `rubric` can be a path to a rubric file instead of an inline mapping. Paths are relative to the directory you run the command from.
- The judge runs at temperature 0 unless its params say otherwise.

### Caching

Accepted judge replies are stored in `.agentgauge/judge-cache.db`, keyed by the judge model, params, prompt version and the exact prompt. Running a suite or calibration again with nothing changed makes no judge calls and prints identical results. Changing the criteria, the template, the case or the output changes the prompt and so misses the cache. Set `cache: false` on the scorer to always call the judge, or delete the file to start over.

### Prompt versions

The rubric names a `prompt_version`. Built-in versions are never edited in place, so a score from `v1` always means the same prompt. If you write your own `template`, change its `prompt_version` label when you change its text so results from different wordings are not confused.

## Limits

- Calibration measures agreement with *your* labels. A judge that agrees with careless labels is still wrong.
- A small sample gives a wide interval. Treat a handful of cases as a smoke test, not evidence.
- Kappa is computed for one rubric at a time. Several dimensions mean several judge scorers, calibrated separately with `--scorer`.
- Calibration is specific to the judge model, rubric and prompt version you calibrated. Change any of them and calibrate again.
- Only one label per case. If several people label, agree on one verdict per case first.
