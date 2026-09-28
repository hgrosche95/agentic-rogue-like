"""Per-floor-tier balance envelopes the encounter agent must generate inside of.

Mirrors the early/mid/elite/boss tiering enemies.py already uses for its
static pool - budget_for() has the same signature as pick_enemy() so it can
slot into engine.py the same way once Phase 2 wires the agent in.
"""

from __future__ import annotations

from .encounter_schema import EnemyBudget

# Tuned with `balance-sim` against a 60 HP / 3 attack player whose Exploit
# deals 8 (5 + attack) - see the README's Balancing section for the numbers.
# Goal is a rising curve instead of the old "trivial fights, then a wall":
# early fights last ~3 turns and cost a few HP, mid ~4 turns, elites are a
# real threat, and the boss is the run's climax but winnable. The boss is
# deliberately *not* the tankiest-per-tier jump: a run arrives there already
# worn down, and there is no card progression yet to scale the player up.
_BUDGETS: dict[str, EnemyBudget] = {
    "early": EnemyBudget(min_hp=38, max_hp=48, min_attack=9, max_attack=12),
    "mid": EnemyBudget(min_hp=55, max_hp=70, min_attack=11, max_attack=14),
    "elite": EnemyBudget(min_hp=80, max_hp=95, min_attack=13, max_attack=16),
    "boss": EnemyBudget(min_hp=95, max_hp=115, min_attack=14, max_attack=17),
}


def budget_for(floor: int, num_floors: int, elite: bool, boss: bool) -> EnemyBudget:
    if boss:
        return _BUDGETS["boss"]
    if elite:
        return _BUDGETS["elite"]
    if floor < num_floors // 2:
        return _BUDGETS["early"]
    return _BUDGETS["mid"]
