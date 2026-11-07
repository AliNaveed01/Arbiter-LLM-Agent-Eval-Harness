"""Benchmark one model served by an OpenAI-compatible endpoint (such as Ollama).

Two measurements per model, both at temperature 0 with a fixed seed:

* tool use: ``data/agent_suite.yaml``, scored by the ``tool_call`` scorer. Reports the agent
  pass rate (every case, including the ones where the right move is to not call a tool), the
  tool-call accuracy (only the cases that expect a call) and the mean latency per case.
* tool loop: ``data/agent_loop_suite.yaml``, eight tasks run through the multi-step agent loop
  (tool results are scripted mocks), scored on the exact sequence of calls. Reports the loop pass
  rate, mean steps and mean latency per task.
* judging: ``data/judge_set.yaml``, thirty answers with a human verdict. The model is the judge;
  reports Cohen's kappa against the human labels with a seeded bootstrap 95% interval.

Failures are recorded as they happen. A malformed tool call, an empty reply or an invalid verdict
counts against the model and is listed in the results; nothing is repaired or retried beyond the
library's own single retry of an invalid judge verdict.

``--thinking off`` sends ``reasoning_effort: "none"`` with every request, which is how Ollama's
OpenAI-compatible endpoint turns thinking off (the equivalent of ``think: false`` on its native
API, which that endpoint ignores).

    uv run python benchmarks/run_benchmark.py --model qwen3:0.6b --out results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from agentgauge.calibration import calibrate
from agentgauge.core import (
    GenerationParams,
    ProviderConfig,
    ScorerSpec,
    Suite,
    TestCase,
    load_suite,
)
from agentgauge.core.models import CaseResult
from agentgauge.judge import Scale
from agentgauge.providers import Provider, build_provider
from agentgauge.runner import run_suite

HERE = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "http://localhost:11434/v1"
THINKING_OFF: dict[str, Any] = {"reasoning_effort": "none"}
RUBRIC: dict[str, Any] = {
    "name": "factual-accuracy",
    "criteria": ["The answer is factually correct.", "The answer addresses the question asked."],
    "scale": "binary",
}


def classify(result: CaseResult) -> str:
    """One word for what happened on a tool-use case."""
    if result.error is not None:
        if "malformed tool call" in result.error:
            return "malformed_response"
        return "error"
    for score in result.scores:
        outcome = score.details.get("outcome")
        if isinstance(outcome, str):
            return outcome
    return "unscored"


def agent_metrics(results: tuple[CaseResult, ...], suite: Suite) -> dict[str, Any]:
    """Pass rate, tool-call accuracy, latency and the outcome of every case."""
    wants_call = {c.id for c in suite.cases if c.metadata.get("expected_tool_call") is not None}
    passed = [r for r in results if r.passed]
    call_cases = [r for r in results if r.case_id in wants_call]
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    outcomes = {r.case_id: classify(r) for r in results}
    return {
        "cases": len(results),
        "passed": len(passed),
        "pass_rate": len(passed) / len(results),
        "tool_cases": len(call_cases),
        "tool_correct": sum(1 for r in call_cases if r.passed),
        "tool_call_accuracy": sum(1 for r in call_cases if r.passed) / len(call_cases),
        "mean_latency_ms": statistics.fmean(latencies) if latencies else None,
        "outcomes": dict(Counter(outcomes.values())),
        "per_case": outcomes,
    }


def loop_metrics(results: tuple[CaseResult, ...]) -> dict[str, Any]:
    """Pass rate, steps and latency for the multi-step tasks, plus the route each case took."""
    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    steps = [r.output.trajectory.steps for r in results if r.output and r.output.trajectory]
    routes: dict[str, Any] = {}
    for result in results:
        trajectory = result.output.trajectory if result.output else None
        routes[result.case_id] = {
            "passed": result.passed,
            "error": result.error,
            "calls": [f"{c.name} {c.arguments}" for c in trajectory.tool_calls]
            if trajectory
            else [],
            "stop_reason": trajectory.stop_reason if trajectory else None,
            "final_text": result.output.text if result.output else None,
        }
    passed = sum(1 for r in results if r.passed)
    return {
        "cases": len(results),
        "passed": passed,
        "pass_rate": passed / len(results),
        "mean_steps": statistics.fmean(steps) if steps else None,
        "mean_latency_ms": statistics.fmean(latencies) if latencies else None,
        "per_case": routes,
    }


def judge_suite(items: list[dict[str, Any]], judge: dict[str, Any] | Provider) -> Suite:
    """The judge set as a suite: fixed answers to judge, with the model as the judge."""
    answers = {i["question"]: i["answer"] for i in items}
    params: dict[str, Any] = {"rubric": RUBRIC, "cache": False}
    params["provider" if not isinstance(judge, dict) else "judge"] = judge
    return Suite(
        name="judge-set",
        cases=tuple(TestCase(id=i["id"], input=i["question"]) for i in items),
        scorers=(ScorerSpec(name="llm_judge", params=params),),
        provider=ProviderConfig(type="fake", model="fixed-answers", responses=answers),
    )


def judge_metrics(
    results: tuple[CaseResult, ...], items: list[dict[str, Any]], seed: int
) -> dict[str, Any]:
    labels = {i["id"]: int(i["label"]) for i in items}
    human: list[int] = []
    judged: list[int] = []
    problems: dict[str, str] = {}
    for result in results:
        score = next((s for s in result.scores if s.scorer == "llm_judge"), None)
        if result.error is not None or score is None:
            problems[result.case_id] = result.error or "no score"
            continue
        human.append(labels[result.case_id])
        judged.append(round(score.value))
    out: dict[str, Any] = {"cases": len(items), "judged": len(human), "problems": problems}
    if len(human) < 2:
        return {**out, "kappa": None, "kappa_ci": None, "accuracy": None}
    report = calibrate(human, judged, Scale.model_validate("binary"), seed=seed)
    return {
        **out,
        "kappa": report.kappa,
        "kappa_ci": report.kappa_ci,
        "accuracy": report.accuracy,
        "confusion": report.confusion,
    }


async def run_model(
    model: str,
    *,
    base_url: str,
    seed: int,
    max_tokens: int,
    thinking: str = "on",
    agent_provider: Provider | None = None,
    loop_provider: Provider | None = None,
    judge_provider: Provider | None = None,
) -> dict[str, Any]:
    """Run all three measurements for ``model``. Providers can be injected for tests."""
    params = GenerationParams(temperature=0.0, seed=seed, max_tokens=max_tokens)
    config = ProviderConfig(
        type="openai_compat",
        model=model,
        base_url=base_url,
        params=params,
        extra_body=THINKING_OFF if thinking == "off" else {},
    )
    agent = load_suite(HERE / "data" / "agent_suite.yaml")
    provider = agent_provider or build_provider(config)
    try:
        run = await run_suite(agent, provider, concurrency=1)  # one at a time: honest latency
    finally:
        if agent_provider is None:
            await provider.aclose()  # type: ignore[attr-defined]
    loop_suite = load_suite(HERE / "data" / "agent_loop_suite.yaml")
    loop_llm = loop_provider or build_provider(config)
    try:
        loop_run = await run_suite(loop_suite, loop_llm, concurrency=1)
    finally:
        if loop_provider is None:
            await loop_llm.aclose()  # type: ignore[attr-defined]
    items: list[dict[str, Any]] = yaml.safe_load((HERE / "data" / "judge_set.yaml").read_text())
    judge: dict[str, Any] | Provider = judge_provider or config.model_dump(mode="json")
    judging = judge_suite(items, judge)
    assert judging.provider is not None
    judged = await run_suite(judging, build_provider(judging.provider), concurrency=1)
    return {
        "model": model,
        "thinking": thinking,
        "agent": agent_metrics(run.results, agent),
        "loop": loop_metrics(loop_run.results),
        "judge": judge_metrics(judged.results, items, seed),
        "raw_agent_outputs": {
            r.case_id: {
                "text": r.output.text if r.output else None,
                "tool_calls": [c.model_dump() for c in r.output.tool_calls] if r.output else [],
                "error": r.error,
            }
            for r in run.results
        },
    }


def _shell(*command: str) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def environment(model: str) -> dict[str, Any]:
    """Hardware and server details worth recording next to the numbers."""
    memory = _shell("sysctl", "-n", "hw.memsize")
    ram_gib = (
        int(memory) / 2**30
        if memory.isdigit()
        else os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    )
    size = ""
    for line in _shell("ollama", "list").splitlines()[1:]:
        columns = re.split(r"\s{2,}", line.strip())
        if columns and columns[0] == model and len(columns) >= 3:
            size = columns[2]
    return {
        "machine": _shell("uname", "-m") or platform.machine(),
        "chip": _shell("sysctl", "-n", "machdep.cpu.brand_string"),
        "ram_gib": round(ram_gib),
        "ollama_version": _shell("ollama", "--version"),
        "model_size": size,
        "python": sys.version.split()[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--thinking", choices=("on", "off"), default="on")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(
        run_model(
            args.model,
            base_url=args.base_url,
            seed=args.seed,
            max_tokens=args.max_tokens,
            thinking=args.thinking,
        )
    )
    result["environment"] = environment(args.model)
    result["settings"] = {
        "temperature": 0.0,
        "seed": args.seed,
        "max_tokens": args.max_tokens,
        "extra_body": THINKING_OFF if args.thinking == "off" else {},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    agent, judge, loop = result["agent"], result["judge"], result["loop"]
    kappa = "n/a" if judge["kappa"] is None else f"{judge['kappa']:.2f}"
    print(
        f"{args.model} (thinking {args.thinking}): kappa {kappa}, "
        f"agent pass {agent['pass_rate']:.0%}, "
        f"tool-call accuracy {agent['tool_call_accuracy']:.0%}, "
        f"loop pass {loop['pass_rate']:.0%} ({loop['passed']}/{loop['cases']}), "
        f"latency {agent['mean_latency_ms']:.0f} ms; outcomes {agent['outcomes']}"
    )


if __name__ == "__main__":
    main()
