import pytest
from pydantic import ValidationError

from agentic_rogue_like.agent.encounter_schema import (
    BudgetViolation,
    EnemyBudget,
    EnemyProposal,
    validate_proposal,
)


def test_proposal_within_budget_passes() -> None:
    budget = EnemyBudget(min_hp=10, max_hp=20, min_attack=2, max_attack=5)
    proposal = EnemyProposal(name="Cave Slime", description="A slow ooze.", hp=15, attack=3)

    validate_proposal(proposal, budget)


def test_proposal_outside_hp_budget_raises() -> None:
    budget = EnemyBudget(min_hp=10, max_hp=20, min_attack=2, max_attack=5)
    proposal = EnemyProposal(
        name="Ogre", description="Too strong for this floor.", hp=999, attack=3
    )

    with pytest.raises(BudgetViolation):
        validate_proposal(proposal, budget)


def test_budget_with_max_below_min_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EnemyBudget(min_hp=20, max_hp=10, min_attack=2, max_attack=5)
