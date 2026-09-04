"""Per-floor-tier balance envelopes the encounter agent must generate inside of.

Mirrors the early/mid/elite/boss tiering enemies.py already uses for its
static pool - budget_for() has the same signature as pick_enemy() so it can
slot into engine.py the same way once Phase 2 wires the agent in.
"""

from __future__ import annotations

from .encounter_schema import EnemyBudget

_BUDGETS: dict[str, EnemyBudget] = {
    "early": EnemyBudget(min_hp=15, max_hp=25, min_attack=2, max_attack=4),
    "mid": EnemyBudget(min_hp=25, max_hp=38, min_attack=4, max_attack=7),
    "elite": EnemyBudget(min_hp=45, max_hp=60, min_attack=7, max_attack=10),
    "boss": EnemyBudget(min_hp=80, max_hp=100, min_attack=9, max_attack=12),
}


def budget_for(floor: int, num_floors: int, elite: bool, boss: bool) -> EnemyBudget:
    if boss:
        return _BUDGETS["boss"]
    if elite:
        return _BUDGETS["elite"]
    if floor < num_floors // 2:
        return _BUDGETS["early"]
    return _BUDGETS["mid"]