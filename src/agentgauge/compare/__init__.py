"""Compare two runs of a suite and decide whether the candidate is a real regression."""

from agentgauge.compare.format import to_json, to_markdown
from agentgauge.compare.pairing import CasePair, CompareError, Pairing, pair_runs
from agentgauge.compare.report import Comparison, ScorerDelta, Verdict, compare_runs
from agentgauge.compare.stats import mcnemar_exact, paired_bootstrap_ci

__all__ = [
    "CasePair",
    "CompareError",
    "Comparison",
    "Pairing",
    "ScorerDelta",
    "Verdict",
    "compare_runs",
    "mcnemar_exact",
    "pair_runs",
    "paired_bootstrap_ci",
    "to_json",
    "to_markdown",
]
