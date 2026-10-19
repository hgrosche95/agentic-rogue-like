"""Core state models for a run.

These are the contracts everything else builds on: the deterministic game
loop (Phase 1) reads and writes them directly, and later the encounter agent
(Phase 2) fills them in via constrained tool calls instead of free text -
so the shape defined here is also the schema the LLM is allowed to produce.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


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
    # Improved once at a rest site (cards.upgrade_card) - never twice.
    upgraded: bool = False
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


class MoveKind(StrEnum):
    """What an enemy can do on its turn - the building blocks of a move set.

    Values match combat.EnemyIntentType, which telegraphs the rolled move
    (plus OVERLOAD, which is never rolled but always follows a CHARGE).
    """

    ATTACK = "attack"  # one hit
    DEFEND = "defend"  # raises block
    BARRAGE = "barrage"  # several smaller hits, armor counts against each
    CHARGE = "charge"  # raises a little block; the next turn is a crushing overload
    PURGE = "purge"  # destroys the rightmost permanent card, then hits


# Default power (percent of the enemy's attack stat) per move kind - the
# numbers the boss move set has always used. For CHARGE it is the power of
# the overload that follows.
DEFAULT_MOVE_POWER: dict[MoveKind, int] = {
    MoveKind.ATTACK: 100,
    MoveKind.DEFEND: 100,
    MoveKind.BARRAGE: 25,
    MoveKind.CHARGE: 140,
    MoveKind.PURGE: 50,
}
DEFAULT_BARRAGE_HITS = 3


class EnemyMove(BaseModel):
    """One entry in an enemy's move set.

    Strength is relative on purpose: `power` is a percentage of the enemy's
    attack stat, so enemies.escalate() and a boss's phase strength - which
    both only touch the attack stat - scale every move along with it.
    """

    kind: MoveKind
    # Relative chance to be rolled among the moves available that turn.
    weight: int = Field(default=1, ge=1, le=10)
    # Shown in the combat log and the intent marker; None falls back to the
    # enemy's attack_name for hitting moves.
    name: str | None = Field(default=None, max_length=40)
    power: int | None = Field(default=None, ge=10, le=300)
    # BARRAGE only.
    hits: int | None = Field(default=None, ge=2, le=4)

    @model_validator(mode="after")
    def _fill_defaults(self) -> EnemyMove:
        if self.hits is not None and self.kind is not MoveKind.BARRAGE:
            raise ValueError("only a barrage has hits")
        if self.power is None:
            self.power = DEFAULT_MOVE_POWER[self.kind]
        if self.kind is MoveKind.BARRAGE and self.hits is None:
            self.hits = DEFAULT_BARRAGE_HITS
        return self


def default_moves() -> list[EnemyMove]:
    """The move set every enemy had before move sets existed: brace 30% of
    the time, attack otherwise. DEFEND comes first so the weighted roll
    draws the same random number the old `random() < 0.3` check did, which
    keeps seeded runs reproducible across the change."""
    return [EnemyMove(kind=MoveKind.DEFEND, weight=3), EnemyMove(kind=MoveKind.ATTACK, weight=7)]


# Moves that can be rolled on any turn - a move set needs one of them, since
# PURGE needs a permanent to destroy and a CHARGE is never rolled right
# after its own overload.
_ALWAYS_AVAILABLE = frozenset({MoveKind.ATTACK, MoveKind.BARRAGE})


class Affix(StrEnum):
    """An elite's extra trait (combat.py applies it, threat.py prices it)."""

    ARMORED = "armored"  # raises block after every one of its turns
    REGENERATING = "regenerating"  # heals after every one of its turns
    ENRAGED = "enraged"  # hits harder once below half HP
    THORNY = "thorny"  # every attack card played against it hurts the player


class Enemy(BaseModel):
    id: str
    name: str
    hp: int
    attack: int
    attack_name: str
    description: str = ""
    # Bosses ignore this and fight with their own phased move set (see
    # combat._roll_boss_intent).
    moves: list[EnemyMove] = Field(default_factory=default_moves, min_length=1, max_length=4)
    # Elites only, rolled per room - see enemies.with_affix.
    affix: Affix | None = None

    @field_validator("moves")
    @classmethod
    def _always_has_a_move(cls, moves: list[EnemyMove]) -> list[EnemyMove]:
        if not any(m.kind in _ALWAYS_AVAILABLE for m in moves):
            raise ValueError("a move set needs an attack or a barrage")
        return moves


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


class RestSite(BaseModel):
    """An open rest site: heal, upgrade a card, or remove a card - one of them."""

    heal_amount: int


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
    # The rest site the player is at, until they pick what to do there (see
    # engine.open_rest); the run can't move on while it is open.
    rest: RestSite | None = None
