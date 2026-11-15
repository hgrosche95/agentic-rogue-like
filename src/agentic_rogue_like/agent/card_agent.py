"""LangGraph agent that designs the AGI's custom card for the player's style.

Same shape as event_agent.py: design_card asks the model for a CardSpec
(forge.py - only building blocks: name, attack or block, numbers, a known
scaling, drawbacks), and check_budget runs forge.validate_spec on it; a
design the game won't take loops back with the reason (capped at
MAX_ATTEMPTS). The rules text and the strength check stay game logic.

card_for_style() is what the game calls: off unless ENCOUNTER_AGENT_ENABLED
is set, Groq only (like the event agent), and any failure falls back to
forge.fallback_card - an agent problem costs the player a fresh card design,
never the run.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

from ..forge import (
    DISCARD_COST,
    FORGE_MAX_POWER,
    FORGE_MIN_POWER,
    HALT_COST,
    MALWARE_VALUE,
    ONE_SHOT_FACTOR,
    PROGRAM_SCALINGS,
    STYLE_SCALINGS,
    TYPICAL_COUNT,
    CardSpec,
    ForgeViolation,
    fallback_card,
    validate_spec,
)
from ..models import DEFAULT_SETTING, Card
from ..style import LABELS, PlayStyle
from . import encounter_agent
from .event_agent import agent_enabled

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3


class CardState(TypedDict):
    style: PlayStyle
    key_cards: list[str]
    program_mode: bool
    setting: str
    attempt: int
    last_error: str | None
    spec: CardSpec | None
    card: Card | None


def _build_prompt(state: CardState) -> str:
    # only the scalings that fit the style (forge.STYLE_SCALINGS)
    scalings = [
        f"{s.value} (typically {TYPICAL_COUNT[s]:g})"
        for s in TYPICAL_COUNT
        if s in STYLE_SCALINGS[state["style"]]
        and (state["program_mode"] or s not in PROGRAM_SCALINGS)
    ]
    cards = ", ".join(state["key_cards"]) or "nothing in particular yet"
    prompt = (
        f"You are a hostile AGI in a {state['setting']}-themed card roguelike. You have "
        f"analysed the player: their deck leans on {LABELS[state['style']]} (key cards: "
        f"{cards}). Design one card that fits that style so well they are tempted to take "
        f"it as part of a deal with you. Give it a short, menacing name that fits the "
        f"setting (under 24 characters). It is an attack (attack: true) or a block card. "
        f"Pick numbers so its power lands between {FORGE_MIN_POWER:g} and "
        f"{FORGE_MAX_POWER:g}, where power = (value + scale_value x the scaling's typical "
        f"count) x hits, + {MALWARE_VALUE:g} per malware, - {DISCARD_COST:g} per "
        f"discard_cost{f', - {HALT_COST:g} if halts' if state['program_mode'] else ''}, "
        f"then x{ONE_SHOT_FACTOR:g} if one_shot. Scalings: {', '.join(scalings)} - or none. "
        f"Use the scaling that fits the style. Don't write rules text, the game does."
    )
    if not state["program_mode"]:
        prompt += " halts must be false."
    if state["last_error"]:
        prompt += f" Your last design was rejected: {state['last_error']}. Fix that."
    return prompt


def design_card(state: CardState) -> CardState:
    model = encounter_agent._model().with_structured_output(CardSpec)
    spec = model.invoke(_build_prompt(state))
    return {**state, "spec": spec, "attempt": state["attempt"] + 1}


def check_budget(state: CardState) -> CardState:
    try:
        card = validate_spec(state["spec"], state["program_mode"], state["style"])
        return {**state, "card": card, "last_error": None}
    except ForgeViolation as exc:
        return {**state, "card": None, "last_error": str(exc)}


def _route(state: CardState) -> str:
    if state["last_error"] is None:
        return "done"
    return "give_up" if state["attempt"] >= MAX_ATTEMPTS else "retry"


def build_graph() -> CompiledStateGraph:
    from langgraph.graph import END, StateGraph

    graph = StateGraph(CardState)
    graph.add_node("design_card", design_card)
    graph.add_node("check_budget", check_budget)
    graph.set_entry_point("design_card")
    graph.add_edge("design_card", "check_budget")
    graph.add_conditional_edges(
        "check_budget", _route, {"done": END, "retry": "design_card", "give_up": END}
    )
    return graph.compile()


def generate_valid_card(
    style: PlayStyle,
    key_cards: list[str],
    program_mode: bool,
    setting: str = DEFAULT_SETTING,
) -> Card:
    """Strict: raises ForgeViolation when the agent never gets it right."""
    result: CardState = build_graph().invoke(
        {
            "style": style,
            "key_cards": key_cards,
            "program_mode": program_mode,
            "setting": setting,
            "attempt": 0,
            "last_error": None,
            "spec": None,
            "card": None,
        }
    )
    if result["card"] is None:
        raise ForgeViolation(f"agent failed after {MAX_ATTEMPTS} attempts: {result['last_error']}")
    return result["card"]


def card_for_style(
    style: PlayStyle,
    key_cards: list[str],
    program_mode: bool,
    setting: str = DEFAULT_SETTING,
) -> tuple[Card, bool]:
    """The forged card and whether the agent designed it (else: the static
    design for the style)."""
    if not agent_enabled():
        return fallback_card(style, program_mode), False
    try:
        return generate_valid_card(style, key_cards, program_mode, setting), True
    except Exception:
        logger.warning("card agent failed, using the static design", exc_info=True)
        return fallback_card(style, program_mode), False
