import pytest

from agentic_rogue_like.agent.budgets import _BUDGETS, budget_for
from agentic_rogue_like.enemies import ENEMY_POOL, escalate, tier_floor
from agentic_rogue_like.models import Enemy, MoveKind, default_moves
from agentic_rogue_like.threat import threat


def test_early_floor_gets_early_budget() -> None:
    budget = budget_for(floor=0, num_floors=8, elite=False, boss=False)
    assert budget == _BUDGETS["early"]


def test_late_floor_gets_mid_budget() -> None:
    budget = budget_for(floor=6, num_floors=8, elite=False, boss=False)
    assert budget == _BUDGETS["mid"]


def test_elite_flag_overrides_floor_tier() -> None:
    budget = budget_for(floor=3, num_floors=8, elite=True, boss=False)
    assert budget == _BUDGETS["elite"]


def test_boss_flag_takes_priority_over_elite() -> None:
    budget = budget_for(floor=7, num_floors=8, elite=True, boss=True)
    assert budget == _BUDGETS["boss"]


@pytest.mark.parametrize("tier", sorted(ENEMY_POOL))
def test_static_pool_stays_inside_its_own_tier_budget(tier: str) -> None:
    """The static pool doubles as the agent's fallback, so drifting out of the
    budgets it is meant to stand in for would make a failed agent call a
    balance cliff rather than an invisible degradation. Same rules as for an
    agent-generated enemy (encounter_schema.validate_proposal)."""
    budget = _BUDGETS["boss" if tier == "boss2" else tier]

    for enemy in ENEMY_POOL[tier]:
        assert budget.min_attack <= enemy.attack <= budget.max_attack, (
            f"{enemy.id} attack out of {tier} budget"
        )
        if budget.boss:
            assert budget.min_hp <= enemy.hp <= budget.max_hp, f"{enemy.id} hp out of budget"
            continue
        low_hp, high_hp = budget.hp_bounds()
        assert low_hp <= enemy.hp <= high_hp, f"{enemy.id} hp out of {tier} bounds"
        low, high = budget.threat_range()
        assert low <= threat(enemy) <= high, f"{enemy.id} threat out of {tier} range"


def test_every_regular_pool_enemy_has_its_own_named_move_set() -> None:
    regular = [e for tier in ("early", "mid", "elite") for e in ENEMY_POOL[tier]]
    for enemy in regular:
        assert enemy.moves != default_moves(), f"{enemy.id} still has the default move set"
        assert all(m.name for m in enemy.moves), f"{enemy.id} has an unnamed move"
        assert enemy.description, f"{enemy.id} has no description"
    # Between them, the pool shows off every kind of move.
    assert {m.kind for e in regular for m in e.moves} == set(MoveKind)


def test_escalate_strengthens_only_second_half_enemies() -> None:
    enemy = Enemy(id="foe", name="Foe", hp=50, attack=10, attack_name="Slam")
    assert escalate(enemy, floor=3, num_floors=8) == enemy
    late = escalate(enemy, floor=4, num_floors=8)
    assert (late.hp, late.attack) == (55, 11)
    assert (enemy.hp, enemy.attack) == (50, 10)  # the original is left alone


def test_escalate_adds_ten_percent_per_half_of_the_timeline() -> None:
    enemy = Enemy(id="foe", name="Foe", hp=100, attack=10, attack_name="Slam")
    assert escalate(enemy, floor=0, num_floors=8, act=2).hp == 121
    late = escalate(enemy, floor=4, num_floors=8, act=2)
    assert (late.hp, late.attack) == (133, 13)


def test_act_two_has_no_early_tier() -> None:
    assert tier_floor(0, 8, act=1) == 0
    assert tier_floor(0, 8, act=2) == 4
    assert tier_floor(6, 8, act=2) == 6
