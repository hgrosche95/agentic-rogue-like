# agentic-rogue-like

A roguelike (think Slay the Spire / FTL) where the run content isn't pulled
from a fixed drop table, but generated live by an LLM agent — constrained to
tool calls with a game-balance budget, so it can be creative without being
able to break the run.

## Goal

A personal project to build real, hands-on experience with agentic AI in
Python — LangGraph, tool-calling, structured-output validation — as a
complement to prior TypeScript/NestJS agent work
([ai-trip-planer](https://github.com/hgrosche95/ai-trip-planer)). Code is
written to be understood and explained, not just to work: the deterministic
game and the agent layer are kept strictly separate on purpose, so the seam
between "what the LLM is allowed to decide" and "what stays fixed game
logic" stays visible instead of blurring together.

## Status

- [x] **Skeleton** — project setup, core state models (`RunState`,
      `PlayerState`, `MapNode`, `Enemy`)
- [x] **Deterministic core loop** — procedurally generated node-map,
      dice-based combat, event/rest/shop resolution, win/lose conditions.
      Fully playable in the terminal, no LLM involved yet.
- [ ] **Encounter agent** — a LangGraph agent that generates enemies, relics
      and events via constrained tool calls, validated against a per-floor
      budget, replacing the static content pools above.
- [ ] **Narrator agent** — wraps generated/mechanical results in flavor text.
- [ ] **Difficulty agent** — adapts future encounter budgets to how the run
      is going.
- [ ] **Polish** — nicer terminal UI, a recorded run, tests that assert
      agent-generated content always stays within its balance budget.

## Why built this way

Most roguelikes get their variety from large, hand-authored content tables.
This flips that: the content generator is an agent making state-aware
decisions (what to spawn, how hard, what it does) through a strict schema,
instead of either a static table or unconstrained free text. The
deterministic core loop was built and tested first, entirely without an LLM,
so the game is playable and its balance is understood on its own terms before
an agent starts generating content into it.

## Stack

Python, Pydantic (state + tool schemas), LangGraph + Claude (agent), pytest.

## Development

```bash
uv sync
uv run pytest
uv run agentic-rogue-like
```
