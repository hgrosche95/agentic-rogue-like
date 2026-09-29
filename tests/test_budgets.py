import pytest

from agentic_rogue_like.agent.budgets import _BUDGETS, budget_for
from agentic_rogue_like.enemies import ENEMY_POOL, escalate
from agentic_rogue_like.models import Enemy


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
    balance cliff rather than an invisible degradation."""
    budget = _BUDGETS[tier]

    for enemy in ENEMY_POOL[tier]:
        assert budget.min_hp <= enemy.hp <= budget.max_hp, f"{enemy.id} hp out of {tier} budget"
        assert budget.min_attack <= enemy.attack <= budget.max_attack, (
            f"{enemy.id} attack out of {tier} budget"
        )


def test_escalate_strengthens_only_second_half_enemies() -> None:
    enemy = Enemy(id="foe", name="Foe", hp=50, attack=10, attack_name="Slam")
    assert escalate(enemy, floor=3, num_floors=8) == enemy
    late = escalate(enemy, floor=4, num_floors=8)
    assert (late.hp, late.attack) == (55, 11)
    assert (enemy.hp, enemy.attack) == (50, 10)  # the original is left alone
