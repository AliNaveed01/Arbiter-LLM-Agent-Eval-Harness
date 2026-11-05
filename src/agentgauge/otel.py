"""Import OpenTelemetry GenAI traces as agent trajectories.

Reads OTLP/JSON trace files (one export document, or one per line in ``.jsonl``) and turns
each trace into a :class:`ModelOutput` whose trajectory is rebuilt from its spans. Only the
parts of the GenAI semantic conventions listed below are read; the conventions are still in
development, so anything else is ignored rather than guessed at.

Per span (``gen_ai.*`` attributes):

* ``gen_ai.operation.name`` = ``execute_tool``: one tool call. ``gen_ai.tool.name`` is
  required; ``gen_ai.tool.call.id``, ``gen_ai.tool.call.arguments`` and
  ``gen_ai.tool.call.result`` are used when present (a string, or a structured value that is
  stored as JSON).
* ``gen_ai.operation.name`` = ``chat``: ``gen_ai.output.messages`` (a JSON string or array of
  messages with ``parts``) supplies the final answer, taken from the last chat span;
  ``gen_ai.usage.input_tokens`` and ``gen_ai.usage.output_tokens`` are summed;
  ``gen_ai.response.model`` (or ``gen_ai.request.model``) names the model.

Per trace: ``agentgauge.case_id``, set on any span, says which suite case the trace is for.
Spans are ordered by start time. Latency is the time from the first span's start to the last
span's end.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from agentgauge.core.models import (
    CaseResult,
    Message,
    ModelOutput,
    RunResult,
    Suite,
    ToolCall,
    Trajectory,
)
from agentgauge.core.yamlio import FileLoadError
from agentgauge.runner.runner import close_scorers, score_output
from agentgauge.scorers.registry import create_scorer

CASE_ID_ATTRIBUTE = "agentgauge.case_id"
DEFAULT_MODEL = "otel-import"


class OtelImportError(FileLoadError):
    """Raised when a trace file cannot be read, is not OTLP/JSON, or cannot be matched."""


class ImportedTrace(BaseModel):
    """One trace, converted."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    case_id: str | None
    model: str | None
    output: ModelOutput


class _Span(BaseModel):
    model_config = ConfigDict(frozen=True)

    trace_id: str
    span_id: str
    name: str
    start_ns: int
    end_ns: int
    attributes: dict[str, Any]


def load_traces(path: str | Path) -> tuple[list[ImportedTrace], int]:
    """Parse ``path`` into traces. Returns the traces and how many had no GenAI spans."""
    p = Path(path)
    if p.suffix.lower() not in {".json", ".jsonl"}:
        raise OtelImportError(p, f"unsupported file type {p.suffix!r}; use .json or .jsonl")
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise OtelImportError(p, f"cannot read file: {exc.strerror or exc}") from exc
    documents: list[Any] = []
    if p.suffix.lower() == ".jsonl":
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if raw.strip():
                documents.append(_decode(p, raw, lineno))
    else:
        documents.append(_decode(p, text, None))
    spans: list[_Span] = []
    for document in documents:
        spans.extend(_spans(p, document))
    if not spans:
        raise OtelImportError(p, "no spans found; expected an OTLP/JSON 'resourceSpans' export")
    by_trace: dict[str, list[_Span]] = {}
    for span in spans:
        by_trace.setdefault(span.trace_id, []).append(span)
    traces: list[ImportedTrace] = []
    skipped = 0
    for trace_id, members in by_trace.items():
        trace = _convert(p, trace_id, sorted(members, key=lambda s: (s.start_ns, s.span_id)))
        if trace is None:
            skipped += 1
        else:
            traces.append(trace)
    return traces, skipped


def _decode(path: Path, text: str, lineno: int | None) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        line = lineno if lineno is not None else exc.lineno
        raise OtelImportError(path, f"invalid JSON: {exc.msg}", line) from exc


def _dict(value: Any) -> dict[str, Any]:
    """``value`` if it is a JSON object, else an empty one."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    """``value`` if it is a JSON array, else an empty one."""
    return cast("list[Any]", value) if isinstance(value, list) else []


def _value(raw: Any) -> Any:
    """Decode an OTLP ``AnyValue``."""
    value = _dict(raw)
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return float(value["doubleValue"])
    if "boolValue" in value:
        return bool(value["boolValue"])
    if "arrayValue" in value:
        return [_value(item) for item in _list(_dict(value["arrayValue"]).get("values"))]
    if "kvlistValue" in value:
        return _attributes(_dict(value["kvlistValue"]).get("values"))
    return None


def _attributes(raw: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in _list(raw):
        entry = _dict(item)
        if "key" in entry:
            result[str(entry["key"])] = _value(entry.get("value"))
    return result


def _spans(path: Path, document: Any) -> list[_Span]:
    root = _dict(document)
    if "resourceSpans" not in root:
        raise OtelImportError(path, "not an OTLP/JSON export: no 'resourceSpans'")
    found: list[_Span] = []
    for resource in _list(root["resourceSpans"]):
        for scope in _list(_dict(resource).get("scopeSpans")):
            for item in _list(_dict(scope).get("spans")):
                raw = _dict(item)
                trace_id, span_id = raw.get("traceId"), raw.get("spanId")
                if not trace_id or not span_id:
                    raise OtelImportError(path, "a span has no traceId or spanId")
                try:
                    start = int(raw.get("startTimeUnixNano", 0))
                    end = int(raw.get("endTimeUnixNano", start))
                except (TypeError, ValueError) as exc:
                    raise OtelImportError(path, f"span {span_id}: bad timestamp") from exc
                found.append(
                    _Span(
                        trace_id=str(trace_id),
                        span_id=str(span_id),
                        name=str(raw.get("name", "")),
                        start_ns=start,
                        end_ns=end,
                        attributes=_attributes(raw.get("attributes")),
                    )
                )
    return found


def _text(value: Any) -> str:
    """A string attribute as is, anything structured as JSON."""
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _final_text(path: Path, span: _Span) -> str:
    raw = span.attributes.get("gen_ai.output.messages")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OtelImportError(
                path, f"span {span.span_id}: gen_ai.output.messages is not valid JSON"
            ) from exc
    messages = _list(raw)
    if not messages:
        return ""
    texts: list[str] = []
    for part in _list(_dict(messages[-1]).get("parts")):
        fields = _dict(part)
        if fields.get("type") == "text":
            texts.append(str(fields.get("content", "")))
    return "".join(texts)


def _convert(path: Path, trace_id: str, spans: list[_Span]) -> ImportedTrace | None:
    operations = {s.span_id: s.attributes.get("gen_ai.operation.name") for s in spans}
    tools = [s for s in spans if operations[s.span_id] == "execute_tool"]
    chats = [s for s in spans if operations[s.span_id] == "chat"]
    if not tools and not chats:
        return None
    messages: list[Message] = []
    for span in tools:
        name = span.attributes.get("gen_ai.tool.name")
        if not isinstance(name, str) or not name:
            raise OtelImportError(
                path, f"trace {trace_id}: execute_tool span {span.span_id} has no gen_ai.tool.name"
            )
        call_id = span.attributes.get("gen_ai.tool.call.id") or f"span_{span.span_id}"
        arguments = _text(span.attributes.get("gen_ai.tool.call.arguments")) or "{}"
        call = ToolCall(id=str(call_id), name=name, arguments=arguments)
        messages.append(Message(role="assistant", content="", tool_calls=(call,)))
        result = _text(span.attributes.get("gen_ai.tool.call.result"))
        messages.append(Message(role="tool", content=result, tool_call_id=call.id))
    final = _final_text(path, max(chats, key=lambda s: s.end_ns)) if chats else ""
    if final:
        messages.append(Message(role="assistant", content=final))
    case_ids = [s.attributes[CASE_ID_ATTRIBUTE] for s in spans if CASE_ID_ATTRIBUTE in s.attributes]
    model = next(
        (
            str(s.attributes[key])
            for s in spans
            for key in ("gen_ai.response.model", "gen_ai.request.model")
            if s.attributes.get(key)
        ),
        None,
    )

    def total(key: str) -> int | None:
        values = [
            s.attributes[key]
            for s in chats
            if isinstance(s.attributes.get(key), int) and not isinstance(s.attributes[key], bool)
        ]
        return sum(values) if values else None

    elapsed_ms = (max(s.end_ns for s in spans) - min(s.start_ns for s in spans)) / 1e6
    output = ModelOutput(
        text=final,
        latency_ms=max(elapsed_ms, 0.0),
        prompt_tokens=total("gen_ai.usage.input_tokens"),
        completion_tokens=total("gen_ai.usage.output_tokens"),
        trajectory=Trajectory(messages=tuple(messages), stop_reason="final"),
    )
    return ImportedTrace(
        trace_id=trace_id,
        case_id=str(case_ids[0]) if case_ids else None,
        model=model,
        output=output,
    )


async def score_imported(suite: Suite, traces: list[ImportedTrace], path: Path) -> RunResult:
    """Score imported traces with ``suite``'s scorers and return them as a run.

    Each trace must name a case with ``agentgauge.case_id``, each case may be named once, and
    the case must exist in the suite. Cases with no trace are simply absent from the run.
    """
    cases = {case.id: case for case in suite.cases}
    seen: dict[str, str] = {}
    for trace in traces:
        if trace.case_id is None:
            raise OtelImportError(
                path, f"trace {trace.trace_id} has no {CASE_ID_ATTRIBUTE} attribute on any span"
            )
        if trace.case_id not in cases:
            raise OtelImportError(
                path, f"trace {trace.trace_id} is for case {trace.case_id!r}, not in the suite"
            )
        if trace.case_id in seen:
            raise OtelImportError(
                path,
                f"case {trace.case_id!r} has two traces "
                f"({seen[trace.case_id]} and {trace.trace_id})",
            )
        seen[trace.case_id] = trace.trace_id
    scorers = [create_scorer(spec) for spec in suite.scorers]
    started = datetime.now(UTC)
    results: list[CaseResult] = []
    try:
        for trace in traces:
            assert trace.case_id is not None
            scores, error = await score_output(cases[trace.case_id], trace.output, scorers)
            results.append(
                CaseResult(
                    case_id=trace.case_id,
                    output=trace.output,
                    scores=scores,
                    error=error,
                    latency_ms=trace.output.latency_ms,
                )
            )
    finally:
        await close_scorers(scorers)
    models = [t.model for t in traces if t.model]
    return RunResult(
        run_id=uuid.uuid4().hex,
        suite_name=suite.name,
        model=models[0] if models else DEFAULT_MODEL,
        started_at=started,
        finished_at=datetime.now(UTC),
        results=tuple(results),
    )
