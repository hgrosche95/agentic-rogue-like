"""Contract the encounter agent's enemy tool-call must satisfy.

The schema the agent is constrained to, and a pure-Python check that a
proposal stays inside its floor's balance budget. Two schemas:

- `EnemyProposal`: name, description, HP, attack, attack name - every enemy
  then fights with the default move set. Checked against the budget's plain
  HP and attack ranges. What bosses (their move set is fixed, see
  combat._roll_boss_intent) and the fine-tuned Ollama model (trained on this
  schema, see training/) generate.
- `MovesetProposal`: the same plus 2-4 named moves. The HP range is no longer
  the rule here - a move set can make an enemy far more or less dangerous at
  the same HP - so it has to land in the budget's *threat* range instead
  (threat.py: the HP it takes off the player before it dies). A harder-hitting
  move set pays for it with HP, a defensive one may have more. The attack
  range stays a hard bound, and HP a loose sanity range around the budget's.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    ValidationInfo,
    WithJsonSchema,
    field_validator,
)

from ..models import PROGRAM_ONLY_MOVES, BodyShape, Enemy, EnemyMove, Feature, MoveKind
from ..threat import threat

# How far a move set's HP may stray from the budget's HP range, as fractions
# of its bounds - the threat range does the real balancing, this only keeps
# out a 3-HP glass cannon or a 400-HP wall that happens to price out right.
HP_SLACK_LOW = 0.5
HP_SLACK_HIGH = 1.5


class EnemyBudget(BaseModel):
    """The balance envelope the agent must generate an enemy inside of."""

    min_hp: int
    max_hp: int
    min_attack: int
    max_attack: int
    # Bosses fight with their own move set, so they are only ever held to
    # the plain HP/attack ranges.
    boss: bool = False

    @field_validator("max_hp")
    @classmethod
    def _hp_range_valid(cls, max_hp: int, info: ValidationInfo) -> int:
        min_hp = info.data.get("min_hp")
        if min_hp is not None and max_hp < min_hp:
            raise ValueError("max_hp must be >= min_hp")
        return max_hp

    @field_validator("max_attack")
    @classmethod
    def _attack_range_valid(cls, max_attack: int, info: ValidationInfo) -> int:
        min_attack = info.data.get("min_attack")
        if min_attack is not None and max_attack < min_attack:
            raise ValueError("max_attack must be >= min_attack")
        return max_attack

    def threat_range(self) -> tuple[float, float]:
        """The threat this budget spans with the default move set: from its
        weakest enemy (min HP, min attack) to its strongest (max, max).

        Derived from threat.DEFAULT_MODEL, so recalibrating that moves these
        bounds along with every enemy's threat.
        """
        return (
            threat(Enemy(id="", name="", hp=self.min_hp, attack=self.min_attack, attack_name="")),
            threat(Enemy(id="", name="", hp=self.max_hp, attack=self.max_attack, attack_name="")),
        )

    def hp_bounds(self) -> tuple[int, int]:
        """The HP a move set enemy may have (see HP_SLACK_LOW/HIGH)."""
        return round(self.min_hp * HP_SLACK_LOW), round(self.max_hp * HP_SLACK_HIGH)


class EnemyProposal(BaseModel):
    """What the LLM's tool call must produce - validated before it becomes an Enemy."""

    name: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    hp: int = Field(gt=0)
    attack: int = Field(gt=0)
    attack_name: str = Field(min_length=1, max_length=40)


class MoveProposal(BaseModel):
    """One move as the LLM proposes it - becomes a models.EnemyMove."""

    kind: MoveKind = Field(
        description=(
            "attack: one hit. defend: raises block. barrage: several smaller hits. "
            "charge: raises a little block, then next turn always a crushing overload. "
            "purge: destroys the player's rightmost permanent card, then hits. "
            "infect: a light hit that leaves Malware on the player, which costs them HP "
            "every turn as it fades. lock: a light hit that locks one of the player's empty "
            "field slots for their next turn. corrupt: a light hit that shuffles useless "
            "Glitch cards into the player's draw pile."
        )
    )
    name: str = Field(min_length=1, max_length=40, description="What the move is called.")
    weight: int = Field(ge=1, le=5, description="How often it is picked, relative to the others.")
    power: int = Field(
        ge=10,
        le=300,
        description=(
            "Strength in percent of the enemy's attack: damage per hit, block raised, or "
            "for charge the overload's damage. Typical: attack 100, defend 100, "
            "barrage 25 per hit, charge 140, purge 50, infect / lock / corrupt 50."
        ),
    )
    # ge=1, not EnemyMove's 2: gpt-oss sends hits=1 for a plain attack or
    # purge, and Groq rejects a tool call outside this schema before the
    # retry loop ever sees it. _single_hit_is_no_barrage turns it back into
    # "no hits" before it reaches EnemyMove.
    hits: int | None = Field(
        default=None,
        ge=1,
        le=4,
        description="barrage only: how many hits (2-4). Leave out for every other move.",
    )
    stacks: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="infect: Malware stacks it leaves (1-6). corrupt: Glitch cards (1-3).",
    )

    @field_validator("hits")
    @classmethod
    def _single_hit_is_no_barrage(cls, hits: int | None) -> int | None:
        # One hit is what every non-barrage move does anyway; a barrage left
        # without hits gets EnemyMove's default.
        return None if hits == 1 else hits


def _spellings(enum: type[StrEnum]) -> dict[str, str]:
    """Every way the model may spell a value -> the value: as it is, and
    with or without its plural "s" ("circuit" for circuits, "blobs" for blob)."""
    out: dict[str, str] = {}
    for member in enum:
        value = member.value
        out[value] = value
        out[value[:-1] if value.endswith("s") else value + "s"] = value
    return out


_BODY_SHAPES = _spellings(BodyShape)
_FEATURES = _spellings(Feature)


def _looks_schema(spellings: dict[str, str], description: str) -> WithJsonSchema:
    """The JSON schema the model is held to for a look: every spelling
    _spellings accepts. Groq checks a tool call against it before anything
    of ours runs and rejects the whole call for one near miss ("circuit"),
    so it lists the variants; the validator below maps them back."""
    return WithJsonSchema(
        {
            "anyOf": [{"type": "string", "enum": sorted(spellings)}, {"type": "null"}],
            "default": None,
            "description": description,
        }
    )


def _normalize_look(value: Any, spellings: dict[str, str]) -> Any:
    """A spelling variant (any case, singular or plural) -> its value; anything
    else is left for the enum to reject."""
    if isinstance(value, str):
        return spellings.get(value.strip().lower(), value)
    return value


class MovesetProposal(EnemyProposal):
    """An EnemyProposal with its own move set."""

    moves: list[MoveProposal] = Field(min_length=2, max_length=4)
    # What it looks like, from fixed lists - an unknown value fails the schema
    # (a spelling variant of a known one doesn't, see _spellings). Optional,
    # so a model that leaves them out still lands a valid enemy.
    body_shape: Annotated[
        BodyShape | None,
        _looks_schema(
            _BODY_SHAPES, "How it is built: blob, swarm, brute, machine, ghost or serpent."
        ),
    ] = None
    feature: Annotated[
        Feature | None,
        _looks_schema(
            _FEATURES, "What stands out on its body: horns, circuits, tentacles, fins or stripes."
        ),
    ] = None

    @field_validator("body_shape", mode="before")
    @classmethod
    def _known_body_shape(cls, value: Any) -> Any:
        return _normalize_look(value, _BODY_SHAPES)

    @field_validator("feature", mode="before")
    @classmethod
    def _known_feature(cls, value: Any) -> Any:
        return _normalize_look(value, _FEATURES)


class BudgetViolation(Exception):
    """Raised when a proposal falls outside its budget."""


class ThreatViolation(BudgetViolation):
    """A proposal that breaks only the threat rule - attack, HP sanity bound and
    move set are all fine.

    The only violation the budget can fix by itself: threat is proportional to
    HP, so `fitting_hp` - the HP centering the threat in the budget's range -
    is what validate_budget (encounter_agent) retunes hp to instead of asking
    the model for a whole new proposal. It applies it only when `fitting_hp`
    sits inside budget.hp_bounds(), and checks the result with
    validate_proposal: proportionality is an approximation, and where the ideal
    HP sits outside the allowed range even the nearest allowed one may not
    price the threat right - then this violation goes into the retry unchanged.
    """

    def __init__(self, message: str, fitting_hp: int) -> None:
        super().__init__(message)
        self.fitting_hp = fitting_hp


def proposal_moves(proposal: EnemyProposal) -> list[EnemyMove] | None:
    """The proposal's moves as EnemyMoves, None if it has none (default move set).

    Raises BudgetViolation for a move set the game can't play - e.g. no move
    that can always be rolled - so the agent gets it back as feedback like
    any other violation.
    """
    if not isinstance(proposal, MovesetProposal):
        return None
    if kinds := {m.kind for m in proposal.moves} & PROGRAM_ONLY_MOVES:
        raise BudgetViolation(
            f"invalid move set: {', '.join(sorted(k.value for k in kinds))} is added by the "
            "game, not part of a move set"
        )
    try:
        moves = [EnemyMove(**move.model_dump()) for move in proposal.moves]
        # Enemy owns the move-set-wide rules (see models.Enemy).
        Enemy(id="", name="", hp=1, attack=1, attack_name="", moves=moves)
    except ValidationError as exc:
        reasons = "; ".join(error["msg"] for error in exc.errors())
        raise BudgetViolation(f"invalid move set: {reasons}") from exc
    return moves


def validate_proposal(proposal: EnemyProposal, budget: EnemyBudget) -> None:
    """Raise BudgetViolation if the proposal breaks its budget.

    The message is written for the agent's retry: it says what is off and,
    for threat, which HP would fit.

    Checks run in the order that decides *which* violation a proposal that
    breaks several rules gets: the move set (the game has to be able to play
    it), then attack, then threat, then the loose HP sanity bound. Only a
    proposal that clears everything but the threat gets a ThreatViolation -
    the auto-correctable kind. So the HP sanity bound sits after the threat
    check: an enemy so overpowered that even its HP bound can't hold it is a
    threat problem first, and correcting its HP is what brings it back inside
    both.
    """
    # First whether the game can play the move set at all (proposal_moves
    # validates it by building an Enemy from it), then the hard attack bound -
    # a proposal that breaks a non-HP rule never gets the auto-correctable
    # ThreatViolation, whatever its threat does.
    moves = None if budget.boss else proposal_moves(proposal)

    if not (budget.min_attack <= proposal.attack <= budget.max_attack):
        raise BudgetViolation(
            f"attack {proposal.attack} outside budget [{budget.min_attack}, {budget.max_attack}]"
        )

    if moves is None:
        # Bosses (their own phased move set, which threat() does not model) and
        # the plain schema the fine-tuned Ollama model was trained on: held to
        # the HP/attack ranges alone, so never a ThreatViolation, never an
        # auto-correction.
        if not (budget.min_hp <= proposal.hp <= budget.max_hp):
            raise BudgetViolation(
                f"hp {proposal.hp} outside budget [{budget.min_hp}, {budget.max_hp}]"
            )
        return

    low_hp, high_hp = budget.hp_bounds()
    enemy = Enemy(
        id="", name="", hp=proposal.hp, attack=proposal.attack, attack_name="", moves=moves
    )
    value = threat(enemy)
    low, high = budget.threat_range()
    if not (low <= value <= high):
        # Threat is proportional to HP, so the HP that lands it on the middle of
        # the range - the most room for whatever threat model errors are left -
        # is one division away. Where it sits outside the HP this budget allows,
        # validate_budget does not retune to it: that violation goes into the
        # retry as-is, and "make the moves ..." is the part the model can act on.
        fitting_hp = round(proposal.hp * ((low + high) / 2) / value)
        direction = "too dangerous" if value > high else "too weak"
        raise ThreatViolation(
            f"threat {value:.1f} outside budget [{low:.1f}, {high:.1f}] - the enemy is "
            f"{direction} for this floor. Change hp to about {fitting_hp}, or make the moves "
            f"{'weaker' if value > high else 'stronger'}",
            fitting_hp,
        )

    if not (low_hp <= proposal.hp <= high_hp):
        raise BudgetViolation(f"hp {proposal.hp} outside the allowed range [{low_hp}, {high_hp}]")
