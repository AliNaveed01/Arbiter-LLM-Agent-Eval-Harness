"""Frozen domain models shared across the runner, scorers and storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TestCase(_Model):
    """A single input to run against a model, with optional expectations."""

    __test__ = False  # not a pytest test class

    id: str
    input: str
    expected: str | None = None
    metadata: dict[str, Any] = Field(default_factory=lambda: {})


class Suite(_Model):
    """A named collection of test cases and the scorers applied to them."""

    name: str
    cases: tuple[TestCase, ...]
    scorers: tuple[str, ...] = ()
    description: str | None = None


class ModelOutput(_Model):
    """What a provider returned for one case."""

    text: str
    latency_ms: float = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    raw: dict[str, Any] | None = None


class Score(_Model):
    """One scorer's verdict on one output."""

    scorer: str
    value: float
    passed: bool
    reason: str | None = None


class CaseResult(_Model):
    """The outcome of running one case: output, scores and any error."""

    case_id: str
    output: ModelOutput | None = None
    scores: tuple[Score, ...] = ()
    error: str | None = None


class RunResult(_Model):
    """The outcome of running a whole suite against one model."""

    run_id: str
    suite_name: str
    model: str
    started_at: datetime
    finished_at: datetime | None = None
    results: tuple[CaseResult, ...] = ()
