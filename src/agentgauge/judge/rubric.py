"""The rubric a judge scores against: criteria, a scale and a prompt version."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentgauge.judge.prompts import template_problem


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Scale(_Model):
    """Binary (0 or 1) or ordinal (1 to ``levels``).

    In YAML a scale may be written ``binary`` or as the number of ordinal
    levels, e.g. ``5``.
    """

    kind: Literal["binary", "ordinal"]
    levels: int = Field(default=2, ge=2, le=10)

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, value: Any) -> Any:
        if value == "binary":
            return {"kind": "binary"}
        if isinstance(value, int) and not isinstance(value, bool):
            return {"kind": "ordinal", "levels": value}
        return value

    @model_validator(mode="after")
    def _binary_has_two_levels(self) -> Scale:
        if self.kind == "binary" and self.levels != 2:
            raise ValueError("a binary scale has exactly two levels")
        return self

    @property
    def values(self) -> tuple[int, ...]:
        """Every score the scale allows, lowest first."""
        if self.kind == "binary":
            return (0, 1)
        return tuple(range(1, self.levels + 1))


class Rubric(_Model):
    """What to judge and how.

    ``pass_at`` is the lowest score that counts as passing. It defaults to 1 for
    a binary scale and to ``levels // 2 + 1`` for an ordinal one (3 of 5, 3 of 4).
    ``prompt_version`` names a built-in prompt template; ``template`` supplies
    your own, in which case ``prompt_version`` is the label you give it.
    """

    name: str
    criteria: tuple[str, ...] = Field(min_length=1)
    scale: Scale
    prompt_version: str = "v1"
    template: str | None = None
    pass_at: int | None = None

    @field_validator("criteria")
    @classmethod
    def _criteria_not_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("criteria must not be blank")
        return value

    @model_validator(mode="after")
    def _template_is_usable(self) -> Rubric:
        problem = template_problem(self.prompt_version, self.template)
        if problem is not None:
            raise ValueError(problem)
        return self

    @model_validator(mode="after")
    def _pass_at_on_scale(self) -> Rubric:
        if self.pass_at is not None and self.pass_at not in self.scale.values:
            raise ValueError(f"pass_at must be one of {list(self.scale.values)}")
        return self

    @property
    def threshold(self) -> int:
        """The lowest passing score."""
        if self.pass_at is not None:
            return self.pass_at
        return 1 if self.scale.kind == "binary" else self.scale.levels // 2 + 1
