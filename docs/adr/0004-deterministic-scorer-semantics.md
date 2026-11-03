# 4. Deterministic scorer semantics

Date: 2026-11-03

## Status

Accepted

## Context

Issue #7 asks for five deterministic scorers without saying how reference values, parameters and edge cases work. `jsonschema` is not on the approved dependency list, and adding dependencies needs approval.

## Decision

- **Reference values** come from `TestCase.expected`. `exact_match`, `contains` and `numeric_tolerance` require it; a case without one fails with the reason `case has no expected value` rather than erroring, so one incomplete case does not abort a run.
- **`exact_match`** compares after stripping edge whitespace; params `strip` and `case_sensitive` adjust that.
- **`regex`** uses the `pattern` param, or `expected` as the pattern when no param is given (one pattern per case). It searches by default; `full=True` requires the whole output to match. An invalid `pattern` param is a configuration error; an invalid per-case pattern fails that case.
- **`numeric_tolerance`** compares the first number found in the output (tolerating thousands separators, currency symbols and a Unicode minus) with the number in `expected`. It passes when `|actual - expected| <= max(abs_tol, rel_tol * |expected|)`; both default to 0.
- **`json_schema`** parses the output as JSON, ignoring one surrounding Markdown code fence, and validates it against the `schema` param.
- **JSON Schema is a documented subset, implemented in-tree** (`agentgauge.scorers.schema`) instead of adding `jsonschema`: `type`, `enum`, `const`, `properties`, `required`, `additionalProperties`, `items`, `minItems`, `maxItems`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum` and `anyOf`. A schema using any other keyword (for example `$ref`, `allOf`, `format`) is rejected when the scorer is created, so a schema never silently validates less than it appears to.
- Every deterministic scorer returns a value of exactly 0.0 or 1.0.

## Consequences

- Suites cannot use `$ref` or `allOf`. If that becomes a real need, adding `jsonschema` as a dependency and deleting the in-tree validator is a contained change.
- First-number extraction is a heuristic: "7 apples and 42 pears" is read as 7. Suites that need more control should use `regex` or `json_schema`.
