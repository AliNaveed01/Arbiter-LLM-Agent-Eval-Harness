"""Core domain models."""

from agentgauge.core.loader import SuiteLoadError, load_suite
from agentgauge.core.models import (
    CaseResult,
    CompletionRequest,
    GenerationParams,
    Message,
    ModelOutput,
    RunResult,
    Score,
    ScorerSpec,
    Suite,
    TestCase,
    ToolCall,
    ToolSpec,
)

__all__ = [
    "CaseResult",
    "CompletionRequest",
    "GenerationParams",
    "Message",
    "ModelOutput",
    "RunResult",
    "Score",
    "ScorerSpec",
    "Suite",
    "SuiteLoadError",
    "TestCase",
    "ToolCall",
    "ToolSpec",
    "load_suite",
]
