"""Scorers. Importing this package registers the built-in scorers."""

from agentgauge.scorers.base import Scorer
from agentgauge.scorers.deterministic import (
    Contains,
    ExactMatch,
    JsonSchema,
    NumericTolerance,
    Regex,
)
from agentgauge.scorers.llm_judge import JudgeError, LLMJudge
from agentgauge.scorers.registry import (
    ScorerConfigError,
    available_scorers,
    create_scorer,
    register_scorer,
    unregister_scorer,
)
from agentgauge.scorers.tool_call import ToolCallScorer

__all__ = [
    "Contains",
    "ExactMatch",
    "JsonSchema",
    "JudgeError",
    "LLMJudge",
    "NumericTolerance",
    "Regex",
    "Scorer",
    "ScorerConfigError",
    "ToolCallScorer",
    "available_scorers",
    "create_scorer",
    "register_scorer",
    "unregister_scorer",
]
