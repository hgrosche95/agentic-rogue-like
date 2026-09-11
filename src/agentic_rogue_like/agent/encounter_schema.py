"""Contract the encounter agent's enemy tool-call must satisfy.

This is Phase 2's starting point: no LLM, no LangGraph yet - just the schema
the agent will be constrained to, and a pure-Python check that a proposal
stays inside its floor's balance budget. engine.py doesn't call any of this
yet; enemies.py still serves the static pool.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class EnemyBudget(BaseModel):
    """The balance envelope the agent must generate an enemy inside of."""

    min_hp: int
    max_hp: int
    min_attack: int
    max_attack: int

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


class EnemyProposal(BaseModel):
    """What the LLM's tool call must produce - validated before it becomes an Enemy."""

    name: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    hp: int = Field(gt=0)
    attack: int = Field(gt=0)
    attack_name: str = Field(min_length=1, max_length=40)


class BudgetViolation(Exception):
    """Raised when a proposal falls outside its budget."""


def validate_proposal(proposal: EnemyProposal, budget: EnemyBudget) -> None:
    """Raise BudgetViolation if the proposal breaks its budget."""
    if not (budget.min_hp <= proposal.hp <= budget.max_hp):
        raise BudgetViolation(f"hp {proposal.hp} outside budget [{budget.min_hp}, {budget.max_hp}]")
    if not (budget.min_attack <= proposal.attack <= budget.max_attack):
        raise BudgetViolation(
            f"attack {proposal.attack} outside budget [{budget.min_attack}, {budget.max_attack}]"
        )
