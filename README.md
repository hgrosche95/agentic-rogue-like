# agentic-rogue-like

A roguelike (think Slay the Spire / FTL) where the run content isn't pulled
from a fixed drop table, but generated live by an LLM agent — constrained to
tool calls with a game-balance budget, so it can be creative without being
able to break the run.

## Status

Early scaffold. Building in phases:

1. **Skeleton** — project setup, core state models *(this commit)*
2. **Deterministic core loop** — procedurally generated node-map, combat/event
   resolution, win/lose conditions. Playable in the terminal, no LLM yet.
3. **Encounter agent** — a LangGraph agent that generates enemies, relics and
   events via constrained tool calls, validated against a per-floor budget.
4. **Narrator agent** — wraps generated/mechanical results in flavor text.
5. **Difficulty agent** — adapts future encounter budgets to how the run is
   going.

## Why

Most roguelikes get their variety from large, hand-authored content tables.
This flips that: the content generator is an agent making state-aware
decisions (what to spawn, how hard, what it does) through a strict schema,
instead of either a static table or unconstrained free text. The interesting
part is the boundary between what the LLM is allowed to decide and what stays
deterministic game logic.

## Stack

Python, Pydantic (state + tool schemas), LangGraph + Claude (agent), pytest.

## Development

```bash
uv sync
uv run pytest
```
