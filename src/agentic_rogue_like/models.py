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
    DRAW = "draw"  # draw `value` cards
    RETRIEVE = "retrieve"  # graveyard -> hand, the `value` most recent cards
    RESTORE = "restore"  # banished pile -> hand, the `value` most recent cards
    # Permanent cards: occupy a field slot for the rest of the fight instead
    # of being discarded, passively affecting play based on their position.
    AMPLIFIER = "amplifier"
    ARMOR = "armor"
    RECYCLING = "recycling"
    DRAW_BONUS = "draw_bonus"
    DAMAGE_BOOST = "damage_boost"  # attacks +value per permanent on the field
    TURRET = "turret"  # deals `value` damage at the end of every turn
    FORTIFY = "fortify"  # +value block per permanent at the end of every turn


PERMANENT_CARD_TYPES = frozenset(
    {
        CardType.AMPLIFIER,
        CardType.ARMOR,
        CardType.RECYCLING,
        CardType.DRAW_BONUS,
        CardType.DAMAGE_BOOST,
        CardType.TURRET,
        CardType.FORTIFY,
    }
)


class Scaling(StrEnum):
    """What an attack card's `scale_value` bonus is counted per."""

    PERMANENT = "permanent"  # permanent cards on the field
    GRAVEYARD = "graveyard"  # cards in the discard pile
    BANISHED = "banished"  # cards in the banished pile


class Rarity(StrEnum):
    STARTER = "starter"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"


class Card(BaseModel):
    id: str
    name: str
    type: CardType
    value: int
    description: str
    rarity: Rarity = Rarity.STARTER
    # Optional mechanics on top of the type's base effect - all default to
    # "off", so a plain Card(...) still behaves exactly like before.
    exhaust: bool = False  # one-shot: banished after use instead of discarded
    discard_cost: int = 0  # discard this many random other hand cards first
    hits: int = 1  # attacks only: the damage is dealt this many times
    draw: int = 0  # draw this many cards after the effect
    scaling: Scaling | None = None  # attacks only: +scale_value per ...
    scale_value: int = 0


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
    # Cards offered after a won fight, waiting for the player to pick one
    # (or skip) - the run can't move on to the next room until then.
    card_reward: list[Card] | None = None
