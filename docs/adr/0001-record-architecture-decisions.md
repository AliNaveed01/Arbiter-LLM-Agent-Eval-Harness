# 1. Record architecture decisions

Date: 2026-11-02

## Status

Accepted

## Context

Non-obvious design choices are easy to forget and hard to reconstruct from code alone. Contributors need to know why the project is shaped the way it is.

## Decision

We record architecture decisions as short Markdown files in `docs/adr/`, named `NNNN-title.md` with a sequential number. Each has Status, Context, Decision and Consequences sections. Superseded decisions are kept and marked as such.

## Consequences

Decisions are reviewable in pull requests and discoverable later. Writing one adds a small cost to any change that makes a non-obvious design choice.
