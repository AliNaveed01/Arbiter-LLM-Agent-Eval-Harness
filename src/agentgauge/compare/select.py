"""Pick stored runs by id, id prefix, or position in time."""

from __future__ import annotations

from agentgauge.compare.pairing import CompareError
from agentgauge.core.models import RunResult
from agentgauge.storage import RunStore

POSITIONS = {"latest": 0, "previous": 1}


def select_run(store: RunStore, token: str, *, suite: str | None = None) -> RunResult:
    """Load the run ``token`` names.

    ``latest`` is the newest stored run and ``previous`` the one before it, optionally
    among the runs of ``suite``. Anything else is a run id or unique id prefix. Storage
    errors for unknown or ambiguous ids propagate unchanged.
    """
    if token not in POSITIONS:
        return store.get_run(token)
    runs = [s for s in store.list_runs() if suite is None or s.suite_name == suite]
    position = POSITIONS[token]
    if len(runs) <= position:
        scope = f" of suite {suite!r}" if suite else ""
        raise CompareError(
            f"cannot resolve {token!r}: only {len(runs)} stored run(s){scope}, "
            f"and {token!r} needs {position + 1}"
        )
    return store.get_run(runs[position].run_id)
