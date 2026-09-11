"""Core state models for a run.

These are the contracts everything else builds on: the deterministic game
loop (Phase 1) reads and writes them directly, and later the encounter agent
(Phase 2) fills them in via constrained tool calls instead of free text -
so the shape defined here is also the schema the LLM is allowed to produce.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class NodeType(StrEnum):
    COMBAT = "combat"
    ELITE = "elite"
    EVENT = "event"
    SHOP = "shop"
    REST = "rest"
    BOSS = "boss"


class RunStatus(StrEnum):
    ONGOING = "ongoing"
    VICTORY = "victory"
    DEFEAT = "defeat"


class Relic(BaseModel):
    id: str
    name: str
    description: str


class CardType(StrEnum):
    # Action cards: resolve once, then go to the discard pile (or back to
    # the deck, if a Recycling permanent applies) - see combat.py.
    ATTACK = "attack"
    BLOCK = "block"
    HEAL = "heal"
    FINAL_STRIKE = "final_strike"
    # Permanent cards: occupy a field slot for the rest of the fight instead
    # of being discarded, passively affecting play based on their position.
    AMPLIFIER = "amplifier"
    ARMOR = "armor"
    RECYCLING = "recycling"
    DRAW_BONUS = "draw_bonus"


PERMANENT_CARD_TYPES = frozenset(
    {CardType.AMPLIFIER, CardType.ARMOR, CardType.RECYCLING, CardType.DRAW_BONUS}
)


class Card(BaseModel):
    id: str
    name: str
    type: CardType
    value: int
    description: str


class PlayerState(BaseModel):
    hp: int
    max_hp: int
    attack: int = 5
    gold: int = 0
    relics: list[Relic] = Field(default_factory=list)
    deck: list[Card] = Field(default_factory=list)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0


class Enemy(BaseModel):
    id: str
    name: str
    hp: int
    attack: int
    attack_name: str


class MapNode(BaseModel):
    id: str
    floor: int
    type: NodeType
    connections: list[str] = Field(default_factory=list)
    visited: bool = False


# Offered to the player at run start and folded into the encounter agent's
# prompt (see agent/encounter_agent.py) so generated enemies match a theme
# instead of always reading as generic dungeon fantasy.
SETTING_PRESETS: tuple[str, ...] = (
    "dungeon",
    "cyberpunk",
    "alien planet",
    "pirate seas",
    "haunted carnival",
)
DEFAULT_SETTING = SETTING_PRESETS[0]
# Players can also type their own setting instead of picking a preset - capped
# so a stray essay doesn't blow up the encounter agent's prompt.
MAX_CUSTOM_SETTING_LENGTH = 40


class RunState(BaseModel):
    seed: int
    floor: int = 0
    status: RunStatus = RunStatus.ONGOING
    player: PlayerState
    nodes: dict[str, MapNode] = Field(default_factory=dict)
    current_node_id: str | None = None
    history: list[str] = Field(default_factory=list)
    setting: str = DEFAULT_SETTING
