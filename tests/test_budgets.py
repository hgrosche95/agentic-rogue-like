from agentic_rogue_like.agent.budgets import _BUDGETS, budget_for


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
