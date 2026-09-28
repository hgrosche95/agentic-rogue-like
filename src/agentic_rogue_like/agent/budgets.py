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
# worn down. Card rewards (one card per won fight) are part of the tuning:
# without them the same budgets leave the boss nearly out of reach. So is the
# draw rule (5-card opening hand, 3 cards per turn, hand limit 8): it feeds
# fewer cards per turn than the old top-up-to-5, and enemies were scaled
# down ~20% to keep the same curve.
_BUDGETS: dict[str, EnemyBudget] = {
    "early": EnemyBudget(min_hp=32, max_hp=40, min_attack=7, max_attack=10),
    "mid": EnemyBudget(min_hp=48, max_hp=60, min_attack=9, max_attack=12),
    "elite": EnemyBudget(min_hp=64, max_hp=76, min_attack=11, max_attack=13),
    "boss": EnemyBudget(min_hp=90, max_hp=105, min_attack=12, max_attack=14),
}


def budget_for(floor: int, num_floors: int, elite: bool, boss: bool) -> EnemyBudget:
    if boss:
        return _BUDGETS["boss"]
    if elite:
        return _BUDGETS["elite"]
    if floor < num_floors // 2:
        return _BUDGETS["early"]
    return _BUDGETS["mid"]
