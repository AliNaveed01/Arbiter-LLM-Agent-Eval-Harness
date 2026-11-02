"""Core domain models."""

from agentgauge.core.loader import SuiteLoadError, load_suite
from agentgauge.core.models import (
    CaseResult,
    ModelOutput,
    RunResult,
    Score,
    Suite,
    TestCase,
)

__all__ = [
    "CaseResult",
    "ModelOutput",
    "RunResult",
    "Score",
    "Suite",
    "SuiteLoadError",
    "TestCase",
    "load_suite",
]
