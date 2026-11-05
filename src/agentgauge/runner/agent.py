"""The multi-step tool loop: call the model, run its tool calls against mocks, repeat."""

from __future__ import annotations

from collections.abc import Sequence

from agentgauge.core.models import (
    AgentConfig,
    CompletionRequest,
    GenerationParams,
    Message,
    ModelOutput,
    TestCase,
    ToolCall,
    ToolMock,
    ToolSpec,
    Trajectory,
)
from agentgauge.providers.base import Provider
from agentgauge.scorers.arguments import parse_arguments, same_arguments


def resolve_tool_call(call: ToolCall, mocks: Sequence[ToolMock]) -> str:
    """The result the model sees for ``call``.

    A call the mocks cannot answer, or whose arguments are not a JSON object, gets an
    ``error:`` result, which the model can react to, instead of aborting the run.
    """
    arguments = parse_arguments(call.arguments)
    if arguments is None:
        return "error: the arguments are not a valid JSON object"
    for mock in mocks:
        if mock.tool != call.name:
            continue
        if mock.arguments is None or same_arguments(mock.arguments, arguments):
            return mock.result
    return f"error: no result is available for tool {call.name!r} with these arguments"


def _sum(values: list[float | int | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


async def run_agent(
    provider: Provider,
    case: TestCase,
    config: AgentConfig,
    *,
    tools: tuple[ToolSpec, ...] = (),
    mocks: Sequence[ToolMock] = (),
    params: GenerationParams | None = None,
) -> ModelOutput:
    """Run ``case`` as an agent for at most ``config.max_steps`` model calls.

    Each step asks the model; tool calls it makes are answered from ``mocks`` and fed back.
    The loop ends when the model replies without a tool call. The returned output carries the
    final text, latency, token counts and cost summed over every step, and the trajectory.
    """
    conversation = list(case.input)
    produced: list[Message] = []
    outputs: list[ModelOutput] = []
    stop_reason: str = "max_steps"
    for _ in range(config.max_steps):
        output = await provider.complete(
            CompletionRequest(messages=tuple(conversation), tools=tools, params=params)
        )
        outputs.append(output)
        assistant = Message(role="assistant", content=output.text, tool_calls=output.tool_calls)
        conversation.append(assistant)
        produced.append(assistant)
        if not output.tool_calls:
            stop_reason = "final"
            break
        for call in output.tool_calls:
            result = Message(
                role="tool", content=resolve_tool_call(call, mocks), tool_call_id=call.id
            )
            conversation.append(result)
            produced.append(result)
    last = outputs[-1]
    prompt_tokens = _sum([o.prompt_tokens for o in outputs])
    completion_tokens = _sum([o.completion_tokens for o in outputs])
    return ModelOutput(
        text=last.text,
        latency_ms=sum(o.latency_ms for o in outputs),
        prompt_tokens=None if prompt_tokens is None else int(prompt_tokens),
        completion_tokens=None if completion_tokens is None else int(completion_tokens),
        cost_usd=_sum([o.cost_usd for o in outputs]),
        trajectory=Trajectory(
            messages=tuple(produced),
            stop_reason="final" if stop_reason == "final" else "max_steps",
        ),
    )
