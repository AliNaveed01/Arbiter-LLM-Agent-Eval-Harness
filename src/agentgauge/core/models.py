"""Frozen domain models shared across the runner, scorers and storage."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ToolCall(_Model):
    """A tool call requested by the model. ``arguments`` is a JSON string."""

    id: str
    name: str
    arguments: str


class Message(_Model):
    """One chat message.

    An assistant message may carry ``tool_calls``; a tool message must carry the
    ``tool_call_id`` of the call it answers.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    @model_validator(mode="after")
    def _check_tool_fields(self) -> Message:
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages may carry tool_calls")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("tool messages must have a tool_call_id")
        return self


class ToolSpec(_Model):
    """A tool the model may call, described with a JSON Schema for its arguments."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=lambda: {})


class GenerationParams(_Model):
    """Sampling parameters. ``None`` means "not set"."""

    temperature: float | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, gt=0)
    seed: int | None = None
    stop: tuple[str, ...] | None = None

    def merged_over(self, defaults: GenerationParams | None) -> GenerationParams:
        """Return these params layered over ``defaults``, field by field.

        A field set here wins; an unset (``None``) field falls back to ``defaults``.
        """
        if defaults is None:
            return self
        overrides = {k: v for k, v in self.model_dump().items() if v is not None}
        return defaults.model_copy(update=overrides)


class CompletionRequest(_Model):
    """Everything a provider needs to produce one completion."""

    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    params: GenerationParams | None = None


class TestCase(_Model):
    """A single input to run against a model, with optional expectations.

    ``input`` may be given as a plain string, which becomes a single user
    message, or as a list of messages.
    """

    __test__ = False  # not a pytest test class

    id: str
    input: tuple[Message, ...]
    expected: str | None = None
    metadata: dict[str, Any] = Field(default_factory=lambda: {})

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            id: str,
            input: str | Sequence[Message],
            expected: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None: ...

    @field_validator("input", mode="before")
    @classmethod
    def _wrap_string_input(cls, value: Any) -> Any:
        if isinstance(value, str):
            return ({"role": "user", "content": value},)
        return value


class ScorerSpec(_Model):
    """A scorer referenced by registry name, with optional constructor params."""

    name: str
    params: dict[str, Any] = Field(default_factory=lambda: {})


class Suite(_Model):
    """A named collection of test cases and the scorers applied to them.

    Each entry in ``scorers`` may be a bare registry name or a mapping with
    ``name`` and ``params``.
    """

    name: str
    cases: tuple[TestCase, ...]
    scorers: tuple[ScorerSpec, ...] = ()
    description: str | None = None

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            name: str,
            cases: Sequence[TestCase],
            scorers: Sequence[str | ScorerSpec] = (),
            description: str | None = None,
        ) -> None: ...

    @field_validator("scorers", mode="before")
    @classmethod
    def _expand_bare_names(cls, value: Any) -> Any:
        if isinstance(value, list | tuple):
            items = cast("Sequence[Any]", value)
            return tuple({"name": v} if isinstance(v, str) else v for v in items)
        return value


class ModelOutput(_Model):
    """What a provider returned for one case."""

    text: str
    latency_ms: float = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    tool_calls: tuple[ToolCall, ...] = ()
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
