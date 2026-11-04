"""The ``llm_judge`` scorer: a model scores the output against a rubric."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agentgauge.core.models import (
    CompletionRequest,
    GenerationParams,
    Message,
    ModelOutput,
    ProviderConfig,
    Score,
    TestCase,
)
from agentgauge.judge import (
    JudgeCache,
    Rubric,
    RubricLoadError,
    cache_key,
    load_rubric,
    render_prompt,
)
from agentgauge.judge.verdict import Verdict, VerdictError, parse_verdict
from agentgauge.providers import Provider, build_provider
from agentgauge.scorers.registry import ScorerConfigError, register_scorer
from agentgauge.storage import StorageError

NAME = "llm_judge"

_RETRY_PROMPT = (
    "Your previous reply was not a valid verdict: {problem}. "
    'Reply again with only a JSON object of the form {{"score": <integer>, "reasoning": '
    '"<one or two sentences>"}}.'
)

_DEFAULT_PARAMS = GenerationParams(temperature=0.0)
DEFAULT_CACHE_PATH = Path(".agentgauge/judge-cache.db")


class JudgeError(Exception):
    """The judge did not return a usable verdict."""


@register_scorer(NAME)
class LLMJudge:
    """Scores an output with a judge model.

    ``rubric`` is a :class:`Rubric`, a mapping, or the path of a rubric YAML file
    (relative to the working directory). ``judge`` configures the judge model
    like a suite ``provider`` block; alternatively pass a ready ``provider``.
    The judge runs at temperature 0 unless its params say otherwise.

    Accepted replies are cached in SQLite, keyed by the judge model, params,
    prompt version and rendered prompt, so rerunning a suite makes no judge
    calls and gives identical scores. ``cache`` is ``True`` (the default file,
    ``.agentgauge/judge-cache.db``), a path, a :class:`JudgeCache`, or ``False``
    to always call the judge.

    A reply that is not a valid verdict is retried once, with the problem
    pointed out; a second bad reply raises :class:`JudgeError`, which the runner
    records as an error on the case.
    """

    name = NAME

    def __init__(
        self,
        rubric: Rubric | Mapping[str, Any] | str,
        judge: ProviderConfig | Mapping[str, Any] | None = None,
        *,
        provider: Provider | None = None,
        params: GenerationParams | None = None,
        cache: bool | str | Path | JudgeCache = True,
    ) -> None:
        self._rubric = _build_rubric(rubric)
        if (judge is None) == (provider is None):
            raise ScorerConfigError(f"{NAME} needs exactly one of 'judge' or 'provider'")
        config = _build_config(judge) if judge is not None else None
        if provider is None:
            assert config is not None
            provider = build_provider(config)
            params = params or config.params
        self._provider = provider
        self._params = (params or GenerationParams()).merged_over(_DEFAULT_PARAMS)
        self._owns_cache = not isinstance(cache, JudgeCache)
        self._cache = _open_cache(cache)

    async def aclose(self) -> None:
        if self._cache is not None and self._owns_cache:
            self._cache.close()
        close = getattr(self._provider, "aclose", None)
        if close is not None:
            await close()

    async def score(self, case: TestCase, output: ModelOutput) -> Score:
        messages = render_prompt(self._rubric, case, output.text)
        verdict, raw, attempts = await self._judge(messages)
        cached = attempts == 0
        rubric = self._rubric
        return Score(
            scorer=self.name,
            value=float(verdict.score),
            passed=verdict.score >= rubric.threshold,
            reason=verdict.reasoning,
            details={
                "judge_model": self._provider.name,
                "rubric": rubric.name,
                "prompt_version": rubric.prompt_version,
                "scale": {"kind": rubric.scale.kind, "levels": rubric.scale.levels},
                "raw_output": raw,
                "attempts": attempts,
                "cached": cached,
            },
        )

    async def _judge(self, messages: tuple[Message, ...]) -> tuple[Verdict, str, int]:
        scale = self._rubric.scale
        key = cache_key(self._provider.name, self._params, self._rubric.prompt_version, messages)
        hit = self._cache.get(key) if self._cache is not None else None
        if hit is not None:
            try:
                return parse_verdict(hit, scale), hit, 0
            except VerdictError:
                pass  # an unusable entry (e.g. from an older scale) is treated as a miss
        verdict, reply, attempts = await self._ask(messages)
        if self._cache is not None:
            self._cache.put(key, reply)
        return verdict, reply, attempts

    async def _ask(self, messages: tuple[Message, ...]) -> tuple[Verdict, str, int]:
        scale = self._rubric.scale
        reply = (await self._provider.complete(self._request(messages))).text
        try:
            return parse_verdict(reply, scale), reply, 1
        except VerdictError as first:
            retry = (
                *messages,
                Message(role="assistant", content=reply),
                Message(role="user", content=_RETRY_PROMPT.format(problem=first)),
            )
            reply = (await self._provider.complete(self._request(retry))).text
            try:
                return parse_verdict(reply, scale), reply, 2
            except VerdictError as second:
                raise JudgeError(
                    f"judge reply was invalid after one retry: {second}; raw reply: {reply!r}"
                ) from second

    def _request(self, messages: tuple[Message, ...]) -> CompletionRequest:
        return CompletionRequest(messages=messages, params=self._params)


def _open_cache(cache: bool | str | Path | JudgeCache) -> JudgeCache | None:
    if isinstance(cache, JudgeCache):
        return cache
    if cache is False:
        return None
    path = DEFAULT_CACHE_PATH if cache is True else Path(cache)
    try:
        return JudgeCache(path)
    except StorageError as exc:
        raise ScorerConfigError(f"{NAME} cache: {exc}") from exc


def _build_rubric(value: Rubric | Mapping[str, Any] | str) -> Rubric:
    if isinstance(value, Rubric):
        return value
    if isinstance(value, str):
        try:
            return load_rubric(value)
        except RubricLoadError as exc:
            raise ScorerConfigError(f"{NAME} rubric: {exc}") from exc
    try:
        return Rubric.model_validate(dict(value))
    except ValidationError as exc:
        raise ScorerConfigError(f"{NAME} rubric is invalid: {exc.errors()[0]['msg']}") from exc


def _build_config(value: ProviderConfig | Mapping[str, Any]) -> ProviderConfig:
    if isinstance(value, ProviderConfig):
        return value
    try:
        return ProviderConfig.model_validate(dict(value))
    except ValidationError as exc:
        raise ScorerConfigError(f"{NAME} judge is invalid: {exc.errors()[0]['msg']}") from exc
