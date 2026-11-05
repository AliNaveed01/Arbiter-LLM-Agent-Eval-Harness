"""The benchmark script, driven by scripted providers instead of a real model."""

import asyncio
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from agentgauge.core import ToolCall, load_suite
from agentgauge.providers import FakeProvider, FakeResponse

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "benchmarks" / "run_benchmark.py"
DATA = ROOT / "benchmarks" / "data"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_benchmark", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call(name: str, arguments: str) -> FakeResponse:
    return FakeResponse(tool_calls=(ToolCall(id="1", name=name, arguments=arguments),))


def scripted_agent() -> FakeProvider:
    """Right on weather, wrong tool on currency, malformed on timers, silent on the rest."""
    suite = load_suite(DATA / "agent_suite.yaml")
    responses: dict[str, str | FakeResponse] = {}
    for case in suite.cases:
        expected: Any = case.metadata["expected_tool_call"]
        prompt = case.input[0].content
        if expected is None:
            responses[prompt] = "Sure, no tool needed."
        elif expected["name"] == "get_weather":
            responses[prompt] = call("get_weather", json.dumps(expected["arguments"]))
        elif expected["name"] == "convert_currency":
            responses[prompt] = call("get_weather", '{"city": "x"}')
        else:
            responses[prompt] = call("set_timer", "{minutes: ten")
    return FakeProvider(responses, name="scripted-agent", latency_ms=10.0)


def scripted_judge(reply: str | None) -> FakeProvider:
    """Agrees with every human label, or answers ``reply`` to everything."""
    items = yaml.safe_load((DATA / "judge_set.yaml").read_text())
    if reply is not None:
        return FakeProvider(default=reply, name="scripted-judge")
    verdicts = {
        f"user: {i['question']}\n": json.dumps({"score": i["label"], "reasoning": "r"})
        for i in items
    }
    return FakeProvider(verdicts, match="contains", name="scripted-judge")


def run(judge: FakeProvider) -> dict[str, Any]:
    script = load_script()
    return asyncio.run(
        script.run_model(
            "scripted",
            base_url="http://unused",
            seed=42,
            max_tokens=256,
            agent_provider=scripted_agent(),
            judge_provider=judge,
        )
    )


def test_data_files_are_consistent() -> None:
    suite = load_suite(DATA / "agent_suite.yaml")
    assert len(suite.cases) == 12 and len(suite.tools) == 3
    assert [s.name for s in suite.scorers] == ["tool_call"]
    items = yaml.safe_load((DATA / "judge_set.yaml").read_text())
    assert len(items) == 30 and sum(i["label"] for i in items) == 15
    assert len({i["id"] for i in items}) == 30


def test_agent_metrics_separate_pass_rate_from_tool_call_accuracy() -> None:
    agent = run(scripted_judge(None))["agent"]
    # 3 weather calls and 3 restraint cases pass; currency and timer cases fail.
    assert (agent["cases"], agent["passed"]) == (12, 6)
    assert agent["pass_rate"] == 0.5
    assert (agent["tool_cases"], agent["tool_correct"]) == (9, 3)
    assert agent["tool_call_accuracy"] == 3 / 9
    assert agent["mean_latency_ms"] is not None
    assert agent["outcomes"] == {"ok": 6, "wrong_tool": 3, "malformed_arguments": 3}
    assert agent["per_case"]["timer-ten"] == "malformed_arguments"


def test_a_judge_that_agrees_with_the_humans_has_kappa_one() -> None:
    judge = run(scripted_judge(None))["judge"]
    assert (judge["cases"], judge["judged"], judge["problems"]) == (30, 30, {})
    assert judge["kappa"] == 1.0
    assert judge["accuracy"] == 1.0


def test_a_judge_that_cannot_produce_verdicts_is_recorded_not_repaired() -> None:
    result = run(scripted_judge("I am not sure."))
    judge = result["judge"]
    assert (judge["judged"], len(judge["problems"])) == (0, 30)
    assert judge["kappa"] is None and judge["kappa_ci"] is None
    assert "invalid after one retry" in next(iter(judge["problems"].values()))


def test_raw_agent_outputs_are_kept_for_the_record() -> None:
    raw = run(scripted_judge(None))["raw_agent_outputs"]
    assert raw["weather-paris"]["tool_calls"][0]["name"] == "get_weather"
    assert raw["no-tool-greeting"]["text"] == "Sure, no tool needed."
    assert raw["timer-ten"]["tool_calls"][0]["arguments"] == "{minutes: ten"


def test_environment_reports_machine_and_ram() -> None:
    info = load_script().environment("not-a-real-model")
    assert info["machine"] and info["ram_gib"] > 0
    assert info["model_size"] == ""
