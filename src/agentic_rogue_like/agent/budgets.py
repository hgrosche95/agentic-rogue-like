"""Per-floor-tier balance envelopes the encounter agent must generate inside of.

Mirrors the early/mid/elite/boss tiering enemies.py already uses for its
static pool - budget_for() has the same signature as pick_enemy() so it can
slot into engine.py the same way once Phase 2 wires the agent in.
"""

from __future__ import annotations

from .encounter_schema import EnemyBudget

# Calibrated for the card-based combat system (combat.py), not the original
# one-hit-per-turn dice fights: a hand can throw several ~11-damage Strikes
# in a single turn, so an enemy sized for "roughly one player attack per
# turn" reads as trivial. Scaled up accordingly - roughly 2x HP, 2-2.5x
# attack versus the original dice-era numbers.
_BUDGETS: dict[str, EnemyBudget] = {
    "early": EnemyBudget(min_hp=25, max_hp=40, min_attack=6, max_attack=10),
    "mid": EnemyBudget(min_hp=40, max_hp=60, min_attack=10, max_attack=15),
    "elite": EnemyBudget(min_hp=70, max_hp=95, min_attack=15, max_attack=22),
    "boss": EnemyBudget(min_hp=140, max_hp=180, min_attack=20, max_attack=28),
}


def budget_for(floor: int, num_floors: int, elite: bool, boss: bool) -> EnemyBudget:
    if boss:
        return _BUDGETS["boss"]
    if elite:
        return _BUDGETS["elite"]
    if floor < num_floors // 2:
        return _BUDGETS["early"]
    return _BUDGETS["mid"]
