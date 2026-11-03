"""Execute a suite against a provider and score the outputs."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import anyio

from agentgauge.core.models import (
    CaseResult,
    CompletionRequest,
    GenerationParams,
    RunResult,
    Suite,
    TestCase,
)
from agentgauge.providers.base import Provider
from agentgauge.scorers.base import Scorer
from agentgauge.scorers.registry import create_scorer


async def run_suite(
    suite: Suite,
    provider: Provider,
    *,
    concurrency: int = 8,
    params: GenerationParams | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> RunResult:
    """Run every case in ``suite`` through ``provider`` and score the outputs.

    At most ``concurrency`` cases are in flight at once. Scorers are created
    from ``suite.scorers`` before anything runs, so a bad scorer name or params
    raises ``ScorerConfigError`` immediately. Results are returned in suite
    order regardless of completion order.
    """
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    scorers = [create_scorer(spec) for spec in suite.scorers]
    started_at = datetime.now(UTC)
    slots: list[CaseResult | None] = [None] * len(suite.cases)
    limiter = anyio.CapacityLimiter(concurrency)

    async def worker(index: int, case: TestCase) -> None:
        async with limiter:
            slots[index] = await _run_case(case, provider, scorers, params, clock)

    async with anyio.create_task_group() as group:
        for index, case in enumerate(suite.cases):
            group.start_soon(worker, index, case)
    results = [result for result in slots if result is not None]
    return RunResult(
        run_id=uuid.uuid4().hex,
        suite_name=suite.name,
        model=provider.name,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        results=tuple(results),
    )


async def _run_case(
    case: TestCase,
    provider: Provider,
    scorers: Sequence[Scorer],
    params: GenerationParams | None,
    clock: Callable[[], float],
) -> CaseResult:
    request = CompletionRequest(messages=case.input, params=params)
    start = clock()
    output = await provider.complete(request)
    latency_ms = (clock() - start) * 1000
    scores = tuple([await scorer.score(case, output) for scorer in scorers])
    return CaseResult(
        case_id=case.id,
        output=output,
        scores=scores,
        latency_ms=latency_ms,
        cost_usd=output.cost_usd,
    )
