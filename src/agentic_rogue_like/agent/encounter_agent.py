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
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

from ..enemies import pick_enemy
from ..models import DEFAULT_SETTING, Enemy
from .budgets import budget_for
from .encounter_schema import BudgetViolation, EnemyBudget, EnemyProposal, validate_proposal

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 20.0


class EncounterState(TypedDict):
    budget: EnemyBudget
    setting: str
    attempt: int
    last_error: str | None
    proposal: EnemyProposal | None


def _model() -> Any:
    # Return type is Any on purpose: ChatGroq and OllamaChatModel share no
    # common base class, only the duck-typed with_structured_output(schema,
    # include_raw=...).invoke(prompt) interface that generate_enemy() and the
    # eval harness actually call.
    #
    # ENCOUNTER_AGENT_MODEL_SOURCE picks the source - "groq" (default) or
    # "ollama", the fine-tuned model served locally (see training/RESULTS.md
    # for how it compares). ENCOUNTER_AGENT_OLLAMA_MODEL overrides which
    # imported Ollama model tag to use, since training produced more than one
    # candidate (see OllamaChatModel's DEFAULT_MODEL_NAME for the current pick).
    if os.environ.get("ENCOUNTER_AGENT_MODEL_SOURCE") == "ollama":
        # Lazy for the same reason as the langchain_groq import below: this
        # module pulls in httpx, and the agent is off in the common case.
        from .ollama_model import DEFAULT_MODEL_NAME, OllamaChatModel

        # constrain_output=True on purpose: the default model needs it to be
        # schema-valid at all, and for models that don't it costs nothing
        # measurable (same latency in eval) while ruling out a whole failure
        # mode. So it stays on whichever model is configured.
        model_name = os.environ.get("ENCOUNTER_AGENT_OLLAMA_MODEL") or DEFAULT_MODEL_NAME
        return OllamaChatModel(model_name, constrain_output=True)

    # Imported lazily: langchain_groq is only needed once the encounter
    # agent actually runs (see enemy_for_node's ENCOUNTER_AGENT_ENABLED
    # check) - importing it at module scope would pull it into every
    # process that imports this module, agent disabled or not.
    from langchain_groq import ChatGroq

    # max_retries=0: the graph's own retry loop already caps attempts, and
    # stacking the client's retries on top would multiply the wait before
    # enemy_for_node() can fall back to the static pool.
    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.9,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _build_prompt(state: EncounterState) -> str:
    setting = state.get("setting") or DEFAULT_SETTING
    prompt = (
        f"Invent an enemy for a {setting}-themed roguelike encounter. "
        f"Its name, description and attack_name must fit the {setting} setting "
        f"instead of generic dungeon fantasy. attack_name is what the enemy's "
        f"attack is called (e.g. 'Tusk Charge', not just 'Attack') and shows up "
        f"in the combat log as '<name> uses <attack_name> for N damage'. "
        f"It must have hp between {state['budget'].min_hp} and {state['budget'].max_hp}, "
        f"and attack between {state['budget'].min_attack} and {state['budget'].max_attack}. "
        f"Keep the description under 150 characters and attack_name under 40 characters."
    )
    if state["last_error"]:
        prompt += f" Your previous attempt was rejected: {state['last_error']}. Fix it."
    return prompt


def generate_enemy(state: EncounterState) -> EncounterState:
    model = _model().with_structured_output(EnemyProposal)
    proposal = model.invoke(_build_prompt(state))
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
    # Same lazy-import reasoning as _model() above, for langgraph.
    from langgraph.graph import END, StateGraph

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
    enemy_id: str,
    floor: int,
    num_floors: int,
    elite: bool,
    boss: bool,
    setting: str = DEFAULT_SETTING,
) -> Enemy:
    budget = budget_for(floor=floor, num_floors=num_floors, elite=elite, boss=boss)
    app = build_graph()
    result: EncounterState = app.invoke(
        {"budget": budget, "setting": setting, "attempt": 0, "last_error": None, "proposal": None}
    )

    if result["last_error"] is not None:
        raise BudgetViolation(f"agent failed after {MAX_ATTEMPTS} attempts: {result['last_error']}")

    proposal = result["proposal"]
    return Enemy(
        id=enemy_id,
        name=proposal.name,
        hp=proposal.hp,
        attack=proposal.attack,
        attack_name=proposal.attack_name,
    )


def enemy_for_node(
    enemy_id: str,
    floor: int,
    num_floors: int,
    elite: bool,
    boss: bool,
    rng: random.Random,
    setting: str = DEFAULT_SETTING,
    prefetched: Callable[[], Enemy] | None = None,
) -> Enemy:
    """Agent-generated enemy, degrading to the static pool if the agent can't deliver.

    This is the boundary the game loop calls: a dead API key, a rate limit or a
    model that never lands inside its budget must cost the player an interesting
    enemy, never the run. The catch is deliberately broad - anything escaping the
    LLM path lands here rather than on the player's terminal - and logged with a
    traceback, so a run that quietly plays on the static pool is still traceable.

    The static pool ignores `setting` - it's a fixed, pre-balanced fallback,
    not something worth theming - so a disabled or failed agent still means
    generic dungeon enemies regardless of what the player picked.

    `prefetched`, if given, stands in for the live agent call: the web API
    starts generation in the background while the player is still on the map
    (see prefetch.py) and hands the result in here, so its errors land in the
    same fallback as a live call's. Its placeholder id is swapped for
    `enemy_id` so ids still come from `rng` exactly as before.
    """
    if os.environ.get("ENCOUNTER_AGENT_ENABLED") != "1":
        return pick_enemy(floor=floor, num_floors=num_floors, elite=elite, boss=boss, rng=rng)

    try:
        if prefetched is not None:
            return prefetched().model_copy(update={"id": enemy_id})
        return generate_balanced_enemy(
            enemy_id=enemy_id,
            floor=floor,
            num_floors=num_floors,
            elite=elite,
            boss=boss,
            setting=setting,
        )
    except Exception:
        logger.warning("encounter agent failed, using static pool", exc_info=True)
        return pick_enemy(floor=floor, num_floors=num_floors, elite=elite, boss=boss, rng=rng)
