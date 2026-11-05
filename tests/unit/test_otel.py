import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from agentgauge.core import Suite, TestCase
from agentgauge.otel import ImportedTrace, OtelImportError, load_traces, score_imported


def attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        wrapped: dict[str, Any] = {"boolValue": value}
    elif isinstance(value, int):
        wrapped = {"intValue": str(value)}
    elif isinstance(value, float):
        wrapped = {"doubleValue": value}
    elif isinstance(value, dict):
        wrapped = {"kvlistValue": {"values": [attr(k, v) for k, v in value.items()]}}
    elif isinstance(value, list):
        wrapped = {"arrayValue": {"values": [attr("", v)["value"] for v in value]}}
    else:
        wrapped = {"stringValue": value}
    return {"key": key, "value": wrapped}


def span(
    trace: str,
    span_id: str,
    start: int,
    end: int,
    operation: str | None = None,
    **attributes: Any,
) -> dict[str, Any]:
    items = [attr(k.replace("__", "."), v) for k, v in attributes.items()]
    if operation:
        items.append(attr("gen_ai.operation.name", operation))
    return {
        "traceId": trace,
        "spanId": span_id,
        "name": operation or "other",
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "attributes": items,
    }


def export(*spans: dict[str, Any]) -> dict[str, Any]:
    return {"resourceSpans": [{"scopeSpans": [{"spans": list(spans)}]}]}


def tool(trace: str, sid: str, start: int, name: str, **extra: Any) -> dict[str, Any]:
    return span(
        trace, sid, start, start + 1_000_000, "execute_tool", gen_ai__tool__name=name, **extra
    )


def write(tmp_path: Path, document: Any, name: str = "traces.json") -> Path:
    path = tmp_path / name
    path.write_text(document if isinstance(document, str) else json.dumps(document))
    return path


FINAL = json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": "It is sunny."}]}])


def agent_trace(trace: str = "t1", case_id: str | None = "weather") -> list[dict[str, Any]]:
    spans = [
        span(
            trace,
            "s1",
            1_000_000_000,
            1_900_000_000,
            "chat",
            gen_ai__response__model="m-1",
            gen_ai__usage__input_tokens=10,
            gen_ai__usage__output_tokens=4,
        ),
        tool(
            trace,
            "s2",
            1_100_000_000,
            "get_weather",
            gen_ai__tool__call__id="call_9",
            gen_ai__tool__call__arguments='{"city": "Paris"}',
            gen_ai__tool__call__result="sunny",
        ),
        tool(
            trace,
            "s3",
            1_200_000_000,
            "get_time",
            gen_ai__tool__call__arguments={"tz": "CET"},
            gen_ai__tool__call__result={"time": "12:00"},
        ),
        span(
            trace,
            "s4",
            1_500_000_000,
            2_000_000_000,
            "chat",
            gen_ai__output__messages=FINAL,
            gen_ai__usage__input_tokens=20,
            gen_ai__usage__output_tokens=6,
        ),
    ]
    if case_id:
        spans[0]["attributes"].append(attr("agentgauge.case_id", case_id))
    return spans


def load(tmp_path: Path, document: Any, name: str = "traces.json") -> list[ImportedTrace]:
    return load_traces(write(tmp_path, document, name))[0]


def test_a_trace_becomes_an_ordered_trajectory(tmp_path: Path) -> None:
    (trace,) = load(tmp_path, export(*reversed(agent_trace())))
    assert (trace.trace_id, trace.case_id, trace.model) == ("t1", "weather", "m-1")
    output = trace.output
    assert output.text == "It is sunny."
    assert (output.prompt_tokens, output.completion_tokens) == (30, 10)
    assert output.latency_ms == pytest.approx(1000.0)
    assert output.trajectory is not None
    calls = output.trajectory.tool_calls
    assert [(c.id, c.name, c.arguments) for c in calls] == [
        ("call_9", "get_weather", '{"city": "Paris"}'),
        ("span_s3", "get_time", '{"tz": "CET"}'),
    ]
    results = [m.content for m in output.trajectory.messages if m.role == "tool"]
    assert results == ["sunny", '{"time": "12:00"}']
    assert output.trajectory.messages[-1].content == "It is sunny."
    assert output.trajectory.stop_reason == "final"


def test_output_messages_may_be_a_structured_array_and_text_parts_are_joined(
    tmp_path: Path,
) -> None:
    messages = [
        {
            "role": "assistant",
            "parts": [
                {"type": "text", "content": "a"},
                {"type": "x"},
                {"type": "text", "content": "b"},
            ],
        }
    ]
    chat = span("t", "c", 1, 2, "chat", gen_ai__output__messages=messages)
    (trace,) = load(tmp_path, export(chat))
    assert trace.output.text == "ab"


def test_traces_without_text_tokens_model_or_case_id_still_import(tmp_path: Path) -> None:
    (trace,) = load(tmp_path, export(tool("t", "s", 5, "ping")))
    assert (trace.case_id, trace.model, trace.output.text) == (None, None, "")
    assert (trace.output.prompt_tokens, trace.output.completion_tokens) == (None, None)
    assert trace.output.trajectory is not None
    assert trace.output.trajectory.tool_calls[0].arguments == "{}"
    assert trace.output.trajectory.messages[1].content == ""


def test_request_model_is_the_fallback_and_non_genai_traces_are_skipped(tmp_path: Path) -> None:
    document = export(
        span("a", "1", 1, 2, "chat", gen_ai__request__model="req-model"),
        span("b", "2", 1, 2),  # an HTTP span, say
    )
    traces, skipped = load_traces(write(tmp_path, document))
    assert [t.model for t in traces] == ["req-model"] and skipped == 1


def test_several_exports_in_jsonl_and_several_traces(tmp_path: Path) -> None:
    lines = "\n".join(
        [
            json.dumps(export(*agent_trace("t1", "a"))),
            "",
            json.dumps(export(*agent_trace("t2", "b"))),
        ]
    )
    traces = load(tmp_path, lines, "traces.jsonl")
    assert sorted(t.case_id or "" for t in traces) == ["a", "b"]


@pytest.mark.parametrize(
    ("document", "name", "message", "line"),
    [
        ("{not json", "t.json", "invalid JSON", 1),
        ('{"resourceSpans": []}\n{oops\n', "t.jsonl", "invalid JSON", 2),
        ({"hello": 1}, "t.json", "no 'resourceSpans'", None),
        ({"resourceSpans": []}, "t.json", "no spans found", None),
        ([1, 2], "t.json", "no 'resourceSpans'", None),
        ("x", "t.txt", "unsupported file type", None),
    ],
)
def test_unreadable_input_has_specific_errors(
    tmp_path: Path, document: Any, name: str, message: str, line: int | None
) -> None:
    with pytest.raises(OtelImportError, match=message) as info:
        load_traces(write(tmp_path, document, name))
    assert info.value.line == line


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(OtelImportError, match="cannot read file"):
        load_traces(tmp_path / "missing.json")


def test_malformed_spans_are_rejected_with_the_span_named(tmp_path: Path) -> None:
    broken_time = span("t", "s1", 1, 2, "chat")
    broken_time["startTimeUnixNano"] = "soon"
    no_id = span("t", "s2", 1, 2, "chat")
    del no_id["spanId"]
    nameless = span("t", "s3", 1, 2, "execute_tool")
    bad_messages = span("t", "s4", 1, 2, "chat", gen_ai__output__messages="{nope")
    for broken, message in [
        (broken_time, "s1: bad timestamp"),
        (no_id, "no traceId or spanId"),
        (nameless, "execute_tool span s3 has no gen_ai.tool.name"),
        (bad_messages, "s4: gen_ai.output.messages is not valid JSON"),
    ]:
        with pytest.raises(OtelImportError, match=message):
            load(tmp_path, export(broken))


def run_score(suite: Suite, traces: list[ImportedTrace], path: Path) -> Any:
    return asyncio.run(score_imported(suite, traces, path))


SUITE = Suite(
    name="agent",
    cases=(
        TestCase(
            id="weather",
            input="q",
            metadata={
                "expected_trajectory": [{"name": "get_weather", "arguments": {"city": "Paris"}}]
            },
        ),
        TestCase(id="other", input="q", metadata={"expected_trajectory": []}),
    ),
    scorers=("trajectory_match",),
)


def test_imported_traces_are_scored_into_a_run(tmp_path: Path) -> None:
    traces = load(tmp_path, export(*agent_trace()))
    run = run_score(SUITE, traces, tmp_path / "traces.json")
    assert (run.suite_name, run.model) == ("agent", "m-1")
    (result,) = run.results
    assert (result.case_id, result.passed, result.error) == ("weather", True, None)
    assert result.latency_ms == pytest.approx(1000.0)
    assert result.output is not None and result.output.trajectory is not None
    assert run.finished_at is not None


def test_a_run_without_any_model_attribute_is_named_after_the_import(tmp_path: Path) -> None:
    spans = export(
        tool("t", "s", 1, "get_weather", gen_ai__tool__call__arguments={"city": "Paris"})
    )
    trace = load(tmp_path, spans)[0]
    trace = trace.model_copy(update={"case_id": "weather"})
    assert run_score(SUITE, [trace], tmp_path / "x.json").model == "otel-import"


def test_scorer_failures_become_case_errors(tmp_path: Path) -> None:
    bad = Suite(
        name="s",
        cases=(TestCase(id="weather", input="q", metadata={"expected_trajectory": "nope"}),),
        scorers=("trajectory_match",),
    )
    run = run_score(bad, load(tmp_path, export(*agent_trace())), tmp_path / "x.json")
    assert run.results[0].error is not None and "trajectory_match" in run.results[0].error


def test_matching_traces_to_cases_is_strict(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    cases = {
        "no case id": (agent_trace("t1", None), "has no agentgauge.case_id"),
        "unknown": (agent_trace("t1", "ghost"), "is for case 'ghost', not in the suite"),
        "two traces": (agent_trace("t1", "weather") + agent_trace("t2", "weather"), "two traces"),
    }
    for spans, message in cases.values():
        with pytest.raises(OtelImportError, match=message):
            run_score(SUITE, load(tmp_path, export(*spans)), path)
