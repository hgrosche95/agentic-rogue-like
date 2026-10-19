"""LangGraph agent that invents an event room inside the rules of a real choice.

Same shape as encounter_agent.py: generate_event asks the model for a
GameEvent (events.py - the schema is the game's own event model), and
validate_rules checks it with events.validate_event; a violation loops back
with the reason (capped at MAX_ATTEMPTS). The model only picks building
blocks and amounts - what they do and what they are worth stays game logic.

event_for_room() is what the game calls: off unless ENCOUNTER_AGENT_ENABLED
is set, Groq only (the fine-tuned Ollama model was never trained on events),
and any failure falls back to the static EVENT_POOL - an agent problem costs
the player a fresh event, never the run.
"""

from __future__ import annotations

import logging
import os
import random
from collections.abc import Callable
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

from ..events import (
    AMOUNT_BOUNDS,
    CARD_VALUE,
    EVENT_MAX_VALUE,
    EVENT_MIN_VALUE,
    GOLD_PER_HP,
    GOLD_PER_MAX_HP,
    LOSE_CARD_VALUE,
    UPGRADE_VALUE,
    EventViolation,
    GameEvent,
    random_event,
    validate_event,
)
from ..models import DEFAULT_SETTING
from . import encounter_agent

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class EventState(TypedDict):
    setting: str
    attempt: int
    last_error: str | None
    event: GameEvent | None


def _build_prompt(state: EventState) -> str:
    setting = state.get("setting") or DEFAULT_SETTING
    gold, hp, max_hp = (AMOUNT_BOUNDS[k] for k in AMOUNT_BOUNDS)
    prompt = (
        f"Invent a short event for a {setting}-themed roguelike: a situation the player "
        f"stumbles into and 2 or 3 options to react, each with a short label that fits "
        f"the setting. Options are built only from these effects: gold (amount {gold[0]} to "
        f"{gold[1]}), hp (amount {hp[0]} to {hp[1]}), max_hp (amount {max_hp[0]} to "
        f"{max_hp[1]}), add_card (rarity common, uncommon or rare), lose_card (a random card "
        f"leaves the deck) and upgrade_card (a random card is upgraded). An option can also "
        f"be a gamble: its effects happen with `chance`, its fail_effects otherwise. "
        f"Make every option a real trade-off: each one, except at most one option that "
        f"does nothing, must have a price - a negative amount or lose_card, or a gamble "
        f"whose fail_effects cost something. Options are weighed in gold: 1 gold = 1, "
        f"1 hp = {GOLD_PER_HP}, 1 max_hp = {GOLD_PER_MAX_HP}, a card = "
        f"{', '.join(f'{r.value} {v}' for r, v in CARD_VALUE.items())}, lose_card = "
        f"{LOSE_CARD_VALUE}, upgrade_card = {UPGRADE_VALUE}; a gamble counts by its chance. "
        f"Every option with effects must be worth between {EVENT_MIN_VALUE} and "
        f"{EVENT_MAX_VALUE}. Keep the description under 150 characters."
    )
    if state["last_error"]:
        prompt += f" Your previous attempt was rejected: {state['last_error']}. Fix it."
    return prompt


def generate_event(state: EventState) -> EventState:
    model = encounter_agent._model().with_structured_output(GameEvent)
    event = model.invoke(_build_prompt(state))
    return {**state, "event": event, "attempt": state["attempt"] + 1}


def validate_rules(state: EventState) -> EventState:
    try:
        validate_event(state["event"])
        return {**state, "last_error": None}
    except EventViolation as exc:
        return {**state, "last_error": str(exc)}


def _route(state: EventState) -> str:
    if state["last_error"] is None:
        return "done"
    return "give_up" if state["attempt"] >= MAX_ATTEMPTS else "retry"


def build_graph() -> CompiledStateGraph:
    from langgraph.graph import END, StateGraph

    graph = StateGraph(EventState)
    graph.add_node("generate_event", generate_event)
    graph.add_node("validate_rules", validate_rules)
    graph.set_entry_point("generate_event")
    graph.add_edge("generate_event", "validate_rules")
    graph.add_conditional_edges(
        "validate_rules", _route, {"done": END, "retry": "generate_event", "give_up": END}
    )
    return graph.compile()


def generate_valid_event(setting: str = DEFAULT_SETTING) -> GameEvent:
    """Strict: raises EventViolation when the agent never gets it right."""
    result: EventState = build_graph().invoke(
        {"setting": setting, "attempt": 0, "last_error": None, "event": None}
    )
    if result["last_error"] is not None:
        raise EventViolation(f"agent failed after {MAX_ATTEMPTS} attempts: {result['last_error']}")
    return result["event"]


def agent_enabled() -> bool:
    return (
        os.environ.get("ENCOUNTER_AGENT_ENABLED") == "1"
        and os.environ.get("ENCOUNTER_AGENT_MODEL_SOURCE") != "ollama"
    )


def event_for_room(
    rng: random.Random,
    setting: str = DEFAULT_SETTING,
    prefetched: Callable[[], GameEvent] | None = None,
) -> tuple[GameEvent, bool]:
    """The room's event and whether the agent wrote it (else: the static
    pool, which the caller still has the narrator theme)."""
    if not agent_enabled():
        return random_event(rng), False
    try:
        event = prefetched() if prefetched is not None else generate_valid_event(setting)
        validate_event(event)  # a prefetched one went through the same graph, but cheap
        return event, True
    except Exception:
        logger.warning("event agent failed, using the static pool", exc_info=True)
        return random_event(rng), False
