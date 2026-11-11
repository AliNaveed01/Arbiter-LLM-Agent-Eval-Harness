"""Compare two runs of a suite and decide whether the candidate is a real regression."""

from agentgauge.compare.pairing import CasePair, CompareError, Pairing, pair_runs

__all__ = ["CasePair", "CompareError", "Pairing", "pair_runs"]
