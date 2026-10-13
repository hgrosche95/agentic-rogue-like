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


class Artifact(BaseModel):
    """A passive bonus for the rest of the run - see artifacts.py.

    Every field is a bonus that defaults to "off", so an artifact only lists
    what it changes. attack and max_hp are applied to the player once, when
    the artifact is picked up; everything else is read by the engine and
    combat.py at their hook points.
    """

    id: str
    name: str
    description: str
    attack: int = 0
    max_hp: int = 0
    extra_draw: int = 0  # cards drawn at the end of the turn ...
    extra_draw_every: int = 1  # ... on every Nth turn only
    opening_hand: int = 0
    max_hand: int = 0
    start_block: int = 0
    opening_damage: int = 0  # dealt to the enemy when the fight starts
    enemy_hp_percent: int = 0  # enemies start the fight with this % more HP
    enemy_attack: int = 0  # added to every enemy attack
    armor: int = 0  # subtracted from every enemy attack
    thorns: int = 0  # damage back to the enemy whenever it attacks
    turn_block: int = 0  # block gained at the end of the turn ...
    turn_block_every: int = 1  # ... on every Nth turn only
    block_bonus: int = 0  # added to block cards
    heal_bonus: int = 0  # added to heal cards
    lifesteal: int = 0  # healed per attack card played
    heal_after_combat: int = 0
    rest_heal: int = 0
    # Only for a character with a context window (the Vibe-Coder):
    token_window: int = 0  # tokens the window holds
    token_regen: int = 0  # used tokens freed at the end of every turn
    opening_free_plays: int = 0  # the first N cards of every fight cost no tokens
    hallucination_percent: int = 0  # cards past the window hallucinate this % more often


class CardType(StrEnum):
    # Action cards: resolve once, then go to the discard pile - see combat.py.
    ATTACK = "attack"
    BLOCK = "block"
    HEAL = "heal"
    FINAL_STRIKE = "final_strike"
    DRAW = "draw"  # draw `value` cards
    RETRIEVE = "retrieve"  # graveyard -> hand, the `value` most recent cards
    RESTORE = "restore"  # banished pile -> hand, the `value` most recent cards
    # destroy every permanent on the field, then the cards that were already
    # banished go back to the hand
    REBOOT = "reboot"
    # Permanent cards: occupy a field slot for the rest of the fight instead
    # of being discarded, passively affecting play based on their position.
    AMPLIFIER = "amplifier"
    ARMOR = "armor"
    DRAW_BONUS = "draw_bonus"
    DAMAGE_BOOST = "damage_boost"  # attacks +value per permanent on the field
    TURRET = "turret"  # deals `value` damage at the end of every turn
    FORTIFY = "fortify"  # +value block per permanent at the end of every turn
    # The Vibe-Coder's cards (see characters.py) - COMPACT and TOKEN_REGEN
    # only do something for a character with a context window.
    COMPACT = "compact"  # action: frees `value` used tokens
    FREE_PLAY = "free_play"  # action: the next `value` cards this turn cost no tokens
    CHAIN = "chain"  # actions to its right +value per card already played this turn
    TOKEN_REGEN = "token_regen"  # frees `value` used tokens at the end of every turn
    SAFEGUARD = "safeguard"  # hallucinating cards fizzle instead of backfiring
    OPENER = "opener"  # the first `value` cards of every turn cost no tokens


PERMANENT_CARD_TYPES = frozenset(
    {
        CardType.AMPLIFIER,
        CardType.ARMOR,
        CardType.DRAW_BONUS,
        CardType.DAMAGE_BOOST,
        CardType.TURRET,
        CardType.FORTIFY,
        CardType.CHAIN,
        CardType.TOKEN_REGEN,
        CardType.SAFEGUARD,
        CardType.OPENER,
    }
)


class Scaling(StrEnum):
    """What an attack or block card's `scale_value` bonus is counted per."""

    PERMANENT = "permanent"  # permanent cards on the field
    GRAVEYARD = "graveyard"  # cards in the discard pile
    BANISHED = "banished"  # cards in the banished pile
    PLAYED = "played"  # cards already played this turn
    EMPTY_SLOT = "empty_slot"  # empty field slots


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
    scaling: Scaling | None = None  # attacks and blocks only: +scale_value per ...
    scale_value: int = 0
    # Tokens it takes from the context window - only characters with one
    # (the Vibe-Coder, see characters.py) pay it, everyone else ignores it.
    token_cost: int = 1


class Character(StrEnum):
    """Who the run is played as - see characters.py for what each one changes."""

    CHRONOS = "chronos"
    VIBE_CODER = "vibe_coder"


class PlayerState(BaseModel):
    character: Character = Character.CHRONOS
    hp: int
    max_hp: int
    attack: int = 5
    gold: int = 0
    artifacts: list[Artifact] = Field(default_factory=list)
    deck: list[Card] = Field(default_factory=list)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0


class ShopCard(BaseModel):
    card: Card
    price: int
    sold: bool = False


class ShopArtifact(BaseModel):
    artifact: Artifact
    price: int
    sold: bool = False


class Shop(BaseModel):
    """What a SHOP room has for sale - see shop.py."""

    cards: list[ShopCard] = Field(default_factory=list)
    artifacts: list[ShopArtifact] = Field(default_factory=list)
    # Removing one card from the deck, once per shop.
    removal_price: int = 0
    removal_used: bool = False


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
    # Which map of the run the player is on - beating an act's boss opens
    # the next one (see engine.advance_act), beating the last one wins.
    act: int = 1
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
    # Map steps taken so far - every ARTIFACT_EVERY_STEPS of them (and once
    # at the start) the player is offered artifacts, and has to pick one
    # before the room they arrived in can be entered.
    steps: int = 0
    artifact_offer: list[Artifact] | None = None
    # The shop the player is browsing - open from entering a SHOP room until
    # they leave it; the run can't move on while it is open.
    shop: Shop | None = None
    # Cards removed at black markets so far - each removal costs more.
    cards_removed: int = 0
