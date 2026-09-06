"""LangGraph agent that generates a balanced Enemy via constrained tool-calling.

Wires together the schema and budgets built earlier: generate_enemy asks Groq
for an EnemyProposal, validate_budget checks it with the already-tested
validate_proposal(); a budget violation loops back to generate_enemy (capped)
instead of ever handing engine.py an out-of-budget Enemy.

Two layers, on purpose: generate_balanced_enemy() is strict and raises when the
agent can't deliver, which is what the tests pin down; enemy_for_node() wraps it
with the fallback to the static pool and is what the game loop should call.
"""

from __future__ import annotations

import logging
import os
import random
from typing import TypedDict

from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ..enemies import pick_enemy
from ..models import Enemy
from .budgets import budget_for
from .encounter_schema import BudgetViolation, EnemyBudget, EnemyProposal, validate_proposal

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 20.0


class EncounterState(TypedDict):
    budget: EnemyBudget
    attempt: int
    last_error: str | None
    proposal: EnemyProposal | None


def _model() -> ChatGroq:
    # max_retries=0: the graph's own retry loop already caps attempts, and
    # stacking the client's retries on top would multiply the wait before
    # enemy_for_node() can fall back to the static pool.
    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.9,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def generate_enemy(state: EncounterState) -> EncounterState:
    model = _model().with_structured_output(EnemyProposal)
    prompt = (
        f"Invent an enemy for a roguelike encounter. "
        f"It must have hp between {state['budget'].min_hp} and {state['budget'].max_hp}, "
        f"and attack between {state['budget'].min_attack} and {state['budget'].max_attack}. "
        f"Keep the description under 150 characters."
    )
    if state["last_error"]:
        prompt += f" Your previous attempt was rejected: {state['last_error']}. Fix it."

    proposal = model.invoke(prompt)
    return {**state, "proposal": proposal, "attempt": state["attempt"] + 1}


def validate_budget(state: EncounterState) -> EncounterState:
    try:
        validate_proposal(state["proposal"], state["budget"])
        return {**state, "last_error": None}
    except BudgetViolation as exc:
        return {**state, "last_error": str(exc)}


def _route_after_validation(state: EncounterState) -> str:
    if state["last_error"] is None:
        return "done"
    if state["attempt"] >= MAX_ATTEMPTS:
        return "give_up"
    return "retry"


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(EncounterState)
    graph.add_node("generate_enemy", generate_enemy)
    graph.add_node("validate_budget", validate_budget)
    graph.set_entry_point("generate_enemy")
    graph.add_edge("generate_enemy", "validate_budget")
    graph.add_conditional_edges(
        "validate_budget",
        _route_after_validation,
        {"done": END, "retry": "generate_enemy", "give_up": END},
    )
    return graph.compile()


def generate_balanced_enemy(
    enemy_id: str, floor: int, num_floors: int, elite: bool, boss: bool
) -> Enemy:
    budget = budget_for(floor=floor, num_floors=num_floors, elite=elite, boss=boss)
    app = build_graph()
    result: EncounterState = app.invoke(
        {"budget": budget, "attempt": 0, "last_error": None, "proposal": None}
    )

    if result["last_error"] is not None:
        raise BudgetViolation(f"agent failed after {MAX_ATTEMPTS} attempts: {result['last_error']}")

    proposal = result["proposal"]
    return Enemy(id=enemy_id, name=proposal.name, hp=proposal.hp, attack=proposal.attack)


def enemy_for_node(
    enemy_id: str, floor: int, num_floors: int, elite: bool, boss: bool, rng: random.Random
) -> Enemy:
    """Agent-generated enemy, degrading to the static pool if the agent can't deliver.

    This is the boundary the game loop calls: a dead API key, a rate limit or a
    model that never lands inside its budget must cost the player an interesting
    enemy, never the run. The catch is deliberately broad - anything escaping the
    LLM path lands here rather than on the player's terminal - and logged with a
    traceback, so a run that quietly plays on the static pool is still traceable.
    """
    if os.environ.get("ENCOUNTER_AGENT_ENABLED") != "1":
        return pick_enemy(floor=floor, num_floors=num_floors, elite=elite, boss=boss, rng=rng)

    try:
        return generate_balanced_enemy(
            enemy_id=enemy_id, floor=floor, num_floors=num_floors, elite=elite, boss=boss
        )
    except Exception:
        logger.warning("encounter agent failed, using static pool", exc_info=True)
        return pick_enemy(floor=floor, num_floors=num_floors, elite=elite, boss=boss, rng=rng)
