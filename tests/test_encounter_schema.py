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
    proposal = EnemyProposal(
        name="Cave Slime", description="A slow ooze.", hp=15, attack=3, attack_name="Acid Splash"
    )

    validate_proposal(proposal, budget)


def test_proposal_outside_hp_budget_raises() -> None:
    budget = EnemyBudget(min_hp=10, max_hp=20, min_attack=2, max_attack=5)
    proposal = EnemyProposal(
        name="Ogre",
        description="Too strong for this floor.",
        hp=999,
        attack=3,
        attack_name="Club Smash",
    )

    with pytest.raises(BudgetViolation):
        validate_proposal(proposal, budget)


def test_budget_with_max_below_min_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EnemyBudget(min_hp=20, max_hp=10, min_attack=2, max_attack=5)


# --------------------------------------------------------------- move set proposals

from agentic_rogue_like.agent.budgets import _BUDGETS  # noqa: E402
from agentic_rogue_like.agent.encounter_schema import (  # noqa: E402
    MoveProposal,
    MovesetProposal,
    proposal_moves,
)
from agentic_rogue_like.models import MoveKind  # noqa: E402

MID = _BUDGETS["mid"]  # hp 48-60, attack 9-12


def _moveset(hp: int, attack: int = 10, moves: list[MoveProposal] | None = None):
    return MovesetProposal(
        name="Wild Boar",
        description="Bristling with rage.",
        hp=hp,
        attack=attack,
        attack_name="Tusk Charge",
        moves=moves
        or [
            MoveProposal(kind=MoveKind.ATTACK, name="Gore", weight=3, power=100),
            MoveProposal(kind=MoveKind.BARRAGE, name="Bristle Volley", weight=2, power=35, hits=4),
        ],
    )


def test_a_move_set_inside_the_threat_range_passes() -> None:
    validate_proposal(_moveset(hp=40), MID)


def test_a_harder_hitting_move_set_may_not_have_the_plain_hp() -> None:
    # 60 HP is fine with plain moves but too much with a 4-hit barrage.
    with pytest.raises(BudgetViolation, match=r"threat .* too dangerous.*hp to about (\d+)"):
        validate_proposal(_moveset(hp=60), MID)


@pytest.mark.parametrize("tier", ["early", "mid", "elite"])
@pytest.mark.parametrize("too", ["dangerous", "weak"])
def test_the_suggested_hp_fixes_the_violation(tier: str, too: str) -> None:
    budget = _BUDGETS[tier]
    low_hp, high_hp = budget.hp_bounds()
    feeble = [
        MoveProposal(kind=MoveKind.ATTACK, name="Nibble", weight=1, power=60),
        MoveProposal(kind=MoveKind.DEFEND, name="Cower", weight=1, power=60),
    ]
    # Every HP that misses the range must get a suggestion that hits it -
    # including the ones where plain rounding would land a hair outside.
    for hp in range(low_hp, high_hp + 1):
        proposal = (
            _moveset(hp=hp, attack=budget.max_attack)
            if too == "dangerous"
            else _moveset(hp=hp, attack=budget.min_attack, moves=feeble)
        )
        try:
            validate_proposal(proposal, budget)
            continue
        except BudgetViolation as exc:
            if "hp to about" not in str(exc) or f"too {too}" not in str(exc):
                continue
            suggested = int(str(exc).split("hp to about ")[1].split(",")[0])
        if low_hp <= suggested <= high_hp and suggested not in (low_hp, high_hp):
            validate_proposal(proposal.model_copy(update={"hp": suggested}), budget)


def test_a_defensive_move_set_may_have_more_hp_than_the_plain_range() -> None:
    tank = [
        MoveProposal(kind=MoveKind.ATTACK, name="Shove", weight=2, power=100),
        MoveProposal(kind=MoveKind.DEFEND, name="Bulwark", weight=3, power=150),
    ]
    validate_proposal(_moveset(hp=MID.max_hp + 4, moves=tank), MID)


def test_too_weak_says_so() -> None:
    feeble = [
        MoveProposal(kind=MoveKind.ATTACK, name="Nibble", weight=1, power=50),
        MoveProposal(kind=MoveKind.DEFEND, name="Cower", weight=3, power=50),
    ]
    with pytest.raises(BudgetViolation, match="too weak"):
        validate_proposal(_moveset(hp=MID.min_hp, attack=MID.min_attack, moves=feeble), MID)


def test_attack_stays_a_hard_bound() -> None:
    with pytest.raises(BudgetViolation, match="attack"):
        validate_proposal(_moveset(hp=40, attack=MID.max_attack + 1), MID)


def test_hp_far_outside_the_budget_is_rejected_even_if_threat_fits() -> None:
    with pytest.raises(BudgetViolation, match="allowed range"):
        validate_proposal(_moveset(hp=MID.max_hp * 2), MID)


def test_an_unplayable_move_set_comes_back_as_a_violation() -> None:
    no_hit = [
        MoveProposal(kind=MoveKind.DEFEND, name="Hide", weight=1, power=100),
        MoveProposal(kind=MoveKind.CHARGE, name="Wind Up", weight=1, power=140),
    ]
    with pytest.raises(BudgetViolation, match="invalid move set"):
        validate_proposal(_moveset(hp=40, moves=no_hit), MID)


def test_hits_on_a_non_barrage_is_a_violation_not_a_crash() -> None:
    bad = [
        MoveProposal(kind=MoveKind.ATTACK, name="Gore", weight=1, power=100, hits=3),
        MoveProposal(kind=MoveKind.DEFEND, name="Hide", weight=1, power=100),
    ]
    with pytest.raises(BudgetViolation, match="barrage"):
        proposal_moves(_moveset(hp=40, moves=bad))


def test_bosses_are_held_to_the_plain_ranges_and_their_moves_ignored() -> None:
    boss = _BUDGETS["boss"]
    validate_proposal(_moveset(hp=boss.max_hp, attack=boss.max_attack), boss)
    with pytest.raises(BudgetViolation, match="hp"):
        validate_proposal(_moveset(hp=boss.max_hp + 1, attack=boss.max_attack), boss)


def test_a_plain_proposal_inside_the_old_ranges_is_inside_the_threat_range() -> None:
    low, high = MID.threat_range()
    assert low < high
    validate_proposal(
        EnemyProposal(
            name="B", description="d", hp=MID.max_hp, attack=MID.max_attack, attack_name="a"
        ),
        MID,
    )


def test_an_interrupt_is_not_the_agents_to_give() -> None:
    moves = [
        MoveProposal(kind=MoveKind.ATTACK, name="Gore", weight=3, power=100),
        MoveProposal(kind=MoveKind.INTERRUPT, name="Jam", weight=1, power=50),
    ]
    with pytest.raises(BudgetViolation, match="interrupt is added by the game"):
        validate_proposal(_moveset(hp=40, moves=moves), MID)
