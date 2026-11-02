# 2. Provider interface

Date: 2026-11-02

## Status

Accepted

## Context

agentgauge evaluates agents, not just single prompts. A provider has to carry multi-turn chat history, tool definitions and tool calls, and sampling parameters, and the same shape must work for hosted APIs, local servers and test fakes. A bare `complete(prompt: str)` cannot express any of that, and widening it later would break every implementation.

## Decision

A provider implements:

```python
class Provider(Protocol):
    @property
    def name(self) -> str: ...
    async def complete(self, request: CompletionRequest) -> ModelOutput: ...
```

- `CompletionRequest` is a frozen Pydantic model in `agentgauge.core.models` holding `messages` (role `system|user|assistant|tool`, content, optional `tool_call_id`), `tools` (name, description, JSON Schema parameters) and optional `params`.
- `GenerationParams` (temperature, max_tokens, seed, stop) uses `None` for "not set". A provider instance holds default params; params on a request override them field by field via `GenerationParams.merged_over`.
- `ModelOutput` gains `tool_calls`, each with an id, a name and arguments as a JSON string. Arguments stay a string, exactly as the model produced them, so malformed JSON can be scored rather than hidden by parsing at the boundary.
- `TestCase.input` accepts a string, which becomes one user message, or a list of messages.
- `FakeProvider` matches canned responses on the last user message and can return canned tool calls.

## Consequences

- One request type serves single-turn prompts and agent trajectories, so trajectory scoring (M3) needs no interface change.
- New request fields can be added with defaults without breaking implementers.
- Callers always build a `CompletionRequest`, which is slightly more verbose for the simple case. `TestCase` input normalisation keeps suite files short.
- Per-call parameter overrides are resolved by the provider, so each adapter must call `merged_over` once.
