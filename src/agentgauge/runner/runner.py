"""Execute a suite against a provider and score the outputs."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

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
    params: GenerationParams | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> RunResult:
    """Run every case in ``suite`` through ``provider`` and score the outputs.

    Scorers are created from ``suite.scorers`` before anything runs, so a bad
    scorer name or params raises ``ScorerConfigError`` immediately. Results are
    returned in suite order.
    """
    scorers = [create_scorer(spec) for spec in suite.scorers]
    started_at = datetime.now(UTC)
    results = [await _run_case(case, provider, scorers, params, clock) for case in suite.cases]
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
