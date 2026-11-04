"""Parse and validate the judge's JSON reply."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentgauge.judge.rubric import Scale

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class VerdictError(ValueError):
    """The judge's reply is not a valid verdict for the rubric's scale."""


class Verdict(BaseModel):
    """A judge's score and its reasoning."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: int
    reasoning: str


def parse_verdict(text: str, scale: Scale) -> Verdict:
    """Parse ``text`` as ``{"score": <int>, "reasoning": <str>}`` within ``scale``.

    A reply wrapped in a Markdown code fence is accepted, since models add them
    habitually. Anything else around the JSON object is an error. Extra keys
    are ignored.
    """
    body = text.strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1)
    try:
        data: Any = json.loads(body)
    except json.JSONDecodeError as exc:
        raise VerdictError(f"reply is not valid JSON ({exc.msg})") from exc
    if not isinstance(data, dict):
        raise VerdictError("reply must be a JSON object")
    fields: dict[str, Any] = data  # pyright: ignore[reportUnknownVariableType]
    if "score" not in fields or "reasoning" not in fields:
        raise VerdictError("reply must have 'score' and 'reasoning'")
    score, reasoning = fields["score"], fields["reasoning"]
    if isinstance(score, float) and score.is_integer():
        score = int(score)
    if not isinstance(score, int) or isinstance(score, bool):
        raise VerdictError(f"score must be an integer, got {score!r}")
    if score not in scale.values:
        raise VerdictError(f"score {score} is outside the scale {list(scale.values)}")
    if not isinstance(reasoning, str):
        raise VerdictError("reasoning must be a string")
    return Verdict(score=score, reasoning=reasoning)
