"""Scorers. Importing this package registers the built-in scorers."""

from agentgauge.scorers.base import Scorer
from agentgauge.scorers.deterministic import Contains, ExactMatch
from agentgauge.scorers.registry import (
    ScorerConfigError,
    available_scorers,
    create_scorer,
    register_scorer,
    unregister_scorer,
)

__all__ = [
    "Contains",
    "ExactMatch",
    "Scorer",
    "ScorerConfigError",
    "available_scorers",
    "create_scorer",
    "register_scorer",
    "unregister_scorer",
]
