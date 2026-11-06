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


class FakeToolCall(_Model):
    """A tool call a fake provider makes; ``arguments`` may be a mapping or a JSON string."""

    name: str
    arguments: dict[str, Any] | str = Field(default_factory=lambda: {})


class FakeReply(_Model):
    """A scripted fake-provider reply: text, tool calls, or both."""

    text: str = ""
    tool_calls: tuple[FakeToolCall, ...] = ()


class ProviderConfig(_Model):
    """Which model a suite runs against, so ``agentgauge run suite.yaml`` is self-contained.

    ``type`` is ``openai_compat`` (any OpenAI-compatible endpoint) or ``fake``
    (canned ``responses``, for examples and tests; ``match`` says whether a
    response key must equal the last user message or merely appear in it). A fake
    response is a string, a ``{text, tool_calls}`` reply, or a list of those: in an agent
    run the list's n-th item answers the n-th step. ``api_key_env`` names the
    environment variable holding the API key; keys are never stored in suites.
    ``extra_body`` adds server-specific fields to every ``openai_compat`` request, such as
    ``{"reasoning_effort": "none"}`` to switch thinking off on Ollama.
    """

    type: Literal["openai_compat", "fake"]
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    params: GenerationParams | None = None
    extra_body: dict[str, Any] = Field(default_factory=lambda: {})
    responses: dict[str, str | FakeReply | list[str | FakeReply]] = Field(
        default_factory=lambda: {}
    )
    match: Literal["exact", "contains"] = "exact"


class AgentConfig(_Model):
    """Run cases as an agent: call the model, execute its tool calls, repeat.

    The loop stops when the model answers without calling a tool, or after
    ``max_steps`` model calls.
    """

    max_steps: int = Field(default=8, ge=1, le=100)


class ToolMock(_Model):
    """A scripted tool result, so agent runs need no real tools.

    A call matches when the tool name is equal and ``arguments`` is either unset (any
    arguments) or equal to the call's arguments (strings compared ignoring case and edge
    whitespace). The first matching mock wins.
    """

    tool: str
    arguments: dict[str, Any] | None = None
    result: str


class Suite(_Model):
    """A named collection of test cases and the scorers applied to them.

    Each entry in ``scorers`` may be a bare registry name or a mapping with
    ``name`` and ``params``. ``tools`` are offered to the model on every case. With
    ``agent`` set the runner runs each case as a multi-step tool loop, answering tool
    calls from ``tool_mocks``.
    """

    name: str
    cases: tuple[TestCase, ...]
    scorers: tuple[ScorerSpec, ...] = ()
    description: str | None = None
    provider: ProviderConfig | None = None
    tools: tuple[ToolSpec, ...] = ()
    agent: AgentConfig | None = None
    tool_mocks: tuple[ToolMock, ...] = ()

    if TYPE_CHECKING:

        def __init__(
            self,
            *,
            name: str,
            cases: Sequence[TestCase],
            scorers: Sequence[str | ScorerSpec] = (),
            description: str | None = None,
            provider: ProviderConfig | None = None,
            tools: Sequence[ToolSpec] = (),
            agent: AgentConfig | None = None,
            tool_mocks: Sequence[ToolMock] = (),
        ) -> None: ...

    @field_validator("scorers", mode="before")
    @classmethod
    def _expand_bare_names(cls, value: Any) -> Any:
        if isinstance(value, list | tuple):
            items = cast("Sequence[Any]", value)
            return tuple({"name": v} if isinstance(v, str) else v for v in items)
        return value


class Trajectory(_Model):
    """What an agent did: the assistant and tool messages produced while it ran, in order.

    ``stop_reason`` is ``final`` when the agent ended by answering and
    ``max_steps`` when it was cut off while still calling tools.
    """

    messages: tuple[Message, ...] = ()
    stop_reason: Literal["final", "max_steps"] = "final"

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        """Every tool call the agent made, in order."""
        calls: list[ToolCall] = []
        for message in self.messages:
            if message.role == "assistant":
                calls.extend(message.tool_calls)
        return tuple(calls)

    @property
    def steps(self) -> int:
        """How many times the model was asked (one assistant message per step)."""
        return sum(1 for m in self.messages if m.role == "assistant")


class ModelOutput(_Model):
    """What a provider returned for one case.

    For an agent run ``text`` is the final answer, ``latency_ms`` and token counts are summed
    over every step, and ``trajectory`` holds the steps.
    """

    text: str
    latency_ms: float = Field(ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    tool_calls: tuple[ToolCall, ...] = ()
    trajectory: Trajectory | None = None
    raw: dict[str, Any] | None = None


class Score(_Model):
    """One scorer's verdict on one output.

    ``details`` is scorer-specific provenance (for the LLM judge: the judge
    model, prompt version and raw output). It is stored with the run but never
    used to decide pass or fail.
    """

    scorer: str
    value: float
    passed: bool
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=lambda: {})


class CaseResult(_Model):
    """The outcome of running one case: output, scores and any error.

    ``latency_ms`` is the wall-clock time the runner spent getting the output
    (including provider retries), also recorded when the case failed;
    ``cost_usd`` comes from the provider's output when it reports one.
    """

    case_id: str
    output: ModelOutput | None = None
    scores: tuple[Score, ...] = ()
    error: str | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)

    @property
    def passed(self) -> bool:
        """True when the case ran without error and every score passed."""
        return self.error is None and all(score.passed for score in self.scores)


class RunResult(_Model):
    """The outcome of running a whole suite against one model."""

    run_id: str
    suite_name: str
    model: str
    started_at: datetime
    finished_at: datetime | None = None
    results: tuple[CaseResult, ...] = ()
