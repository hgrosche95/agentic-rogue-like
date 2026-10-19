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

import math

from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator

from ..models import Enemy, EnemyMove, MoveKind
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
    hits: int | None = Field(
        default=None, ge=2, le=4, description="barrage only: how many hits (2-4)."
    )
    stacks: int | None = Field(
        default=None,
        ge=1,
        le=6,
        description="infect: Malware stacks it leaves (1-6). corrupt: Glitch cards (1-3).",
    )


class MovesetProposal(EnemyProposal):
    """An EnemyProposal with its own move set."""

    moves: list[MoveProposal] = Field(min_length=2, max_length=4)


class BudgetViolation(Exception):
    """Raised when a proposal falls outside its budget."""


def proposal_moves(proposal: EnemyProposal) -> list[EnemyMove] | None:
    """The proposal's moves as EnemyMoves, None if it has none (default move set).

    Raises BudgetViolation for a move set the game can't play - e.g. no move
    that can always be rolled - so the agent gets it back as feedback like
    any other violation.
    """
    if not isinstance(proposal, MovesetProposal):
        return None
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
    """
    if not (budget.min_attack <= proposal.attack <= budget.max_attack):
        raise BudgetViolation(
            f"attack {proposal.attack} outside budget [{budget.min_attack}, {budget.max_attack}]"
        )

    moves = None if budget.boss else proposal_moves(proposal)
    if moves is None:
        if not (budget.min_hp <= proposal.hp <= budget.max_hp):
            raise BudgetViolation(
                f"hp {proposal.hp} outside budget [{budget.min_hp}, {budget.max_hp}]"
            )
        return

    low_hp, high_hp = budget.hp_bounds()
    if not (low_hp <= proposal.hp <= high_hp):
        raise BudgetViolation(f"hp {proposal.hp} outside the allowed range [{low_hp}, {high_hp}]")

    enemy = Enemy(
        id="", name="", hp=proposal.hp, attack=proposal.attack, attack_name="", moves=moves
    )
    value = threat(enemy)
    low, high = budget.threat_range()
    if low <= value <= high:
        return
    # Threat is proportional to HP, so the HP that lands on the nearest bound
    # is one division away - rounded towards the inside of the range, or the
    # suggestion itself could miss it by a fraction.
    if value > high:
        fitting_hp = math.floor(proposal.hp * high / value)
    else:
        fitting_hp = math.ceil(proposal.hp * low / value)
    fitting_hp = max(low_hp, min(high_hp, fitting_hp))
    direction = "too dangerous" if value > high else "too weak"
    raise BudgetViolation(
        f"threat {value:.1f} outside budget [{low:.1f}, {high:.1f}] - the enemy is "
        f"{direction} for this floor. Change hp to about {fitting_hp}, or make the moves "
        f"{'weaker' if value > high else 'stronger'}"
    )
