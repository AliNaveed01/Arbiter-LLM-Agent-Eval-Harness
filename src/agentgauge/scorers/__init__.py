"""Scorers. Importing this package registers the built-in scorers."""

from agentgauge.scorers.base import Scorer
from agentgauge.scorers.deterministic import ExactMatch
from agentgauge.scorers.registry import (
    ScorerConfigError,
    available_scorers,
    create_scorer,
    register_scorer,
    unregister_scorer,
)

__all__ = [
    "ExactMatch",
    "Scorer",
    "ScorerConfigError",
    "available_scorers",
    "create_scorer",
    "register_scorer",
    "unregister_scorer",
]
