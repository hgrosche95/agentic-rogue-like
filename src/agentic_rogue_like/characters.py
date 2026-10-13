"""Playable characters - who a run is played as.

Dr. Chronos is the baseline every number in combat.py was tuned for. The
Vibe-Coder bends the card flow instead: he draws a card after every card he
plays but one fewer at the end of the turn, so his hand never runs dry -
what stops him is his context window. Every card costs tokens
(Card.token_cost) and only part of the window frees up again at the end of
each turn, so a big turn has to be saved up for. A card that would push him
past the window may hallucinate (see combat.HALLUCINATION_CHANCE) and
backfire instead.

The window's numbers come from `balance-sim --character vibe_coder`: a
whole fight's worth of tokens up front let him kill most enemies on turn 1
or run dry against bosses - a small window refilled every turn plays like
Dr. Chronos's curve (both ~9% run win rate with the smart bot).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .artifacts import ARTIFACT_POOL, VIBE_CODER_ARTIFACT_POOL
from .cards import REWARD_POOL, VIBE_CODER_REWARD_POOL, starter_deck, vibe_coder_starter_deck
from .models import Artifact, Card, Character


@dataclass(frozen=True)
class CharacterProfile:
    id: Character
    name: str
    title: str
    description: str
    hp: int
    attack: int
    deck: Callable[[], list[Card]]
    # What card rewards, the starting pick and shops offer him.
    reward_pool: list[Card]
    # What artifact offers and shops offer him.
    artifact_pool: list[Artifact]
    # Tokens per fight - None: no context window, token costs are ignored.
    token_limit: int | None = None
    token_regen: int = 0  # used tokens freed at the end of every turn
    draw_on_play: int = 0  # cards drawn after every card played
    turn_draw_modifier: int = 0  # added to the cards drawn at the end of the turn


CHARACTERS: dict[Character, CharacterProfile] = {
    Character.CHRONOS: CharacterProfile(
        id=Character.CHRONOS,
        name="Dr. Chronos",
        title="Human · Time traveller",
        description="Plays steady: draws 3 cards at the end of every turn.",
        hp=45,
        attack=2,
        deck=starter_deck,
        reward_pool=REWARD_POOL,
        artifact_pool=ARTIFACT_POOL,
    ),
    Character.VIBE_CODER: CharacterProfile(
        id=Character.VIBE_CODER,
        name="Vibe-Coder",
        title="Human · Prompts, doesn't type",
        description=(
            "Draws a card for every card he plays, but only 2 at the end of the "
            "turn. Every card costs tokens from a 4-token context window, 3 of "
            "which free up every turn - past it, cards may hallucinate and backfire."
        ),
        hp=45,
        attack=2,
        deck=vibe_coder_starter_deck,
        reward_pool=REWARD_POOL + VIBE_CODER_REWARD_POOL,
        artifact_pool=ARTIFACT_POOL + VIBE_CODER_ARTIFACT_POOL,
        token_limit=4,
        token_regen=3,
        draw_on_play=1,
        turn_draw_modifier=-1,
    ),
}


def profile(character: Character) -> CharacterProfile:
    return CHARACTERS[character]
