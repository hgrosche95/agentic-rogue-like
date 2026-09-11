"""Static placeholder enemy pool for Phase 1.

Phase 2 replaces this fixed pool with the encounter agent generating
enemies via a constrained tool call, validated against a per-floor budget.
The `Enemy` shape here is exactly the schema that tool call will have to
produce. This module stays agent-unaware on purpose - agent/encounter_agent.py
imports pick_enemy() as its fallback, so the dependency can only go one way.
"""

from __future__ import annotations

import random

from .models import Enemy

ENEMY_POOL: dict[str, list[Enemy]] = {
    # Kept inside agent/budgets.py's ranges (see its own comment for why
    # these read high compared to the old dice-combat numbers) - a test
    # pins that invariant down so this pool can't quietly drift out of it.
    "early": [
        Enemy(id="rat-swarm", name="Rat Swarm", hp=30, attack=7, attack_name="Swarm Bite"),
        Enemy(id="cave-slime", name="Cave Slime", hp=35, attack=6, attack_name="Acid Splash"),
    ],
    "mid": [
        Enemy(id="bandit", name="Bandit", hp=45, attack=12, attack_name="Dagger Strike"),
        Enemy(id="wild-boar", name="Wild Boar", hp=50, attack=13, attack_name="Tusk Charge"),
    ],
    "elite": [
        Enemy(id="ogre", name="Ogre", hp=85, attack=19, attack_name="Club Smash"),
    ],
    "boss": [
        Enemy(id="the-warden", name="The Warden", hp=160, attack=24, attack_name="Iron Verdict"),
    ],
}


def pick_enemy(floor: int, num_floors: int, elite: bool, boss: bool, rng: random.Random) -> Enemy:
    if boss:
        pool = ENEMY_POOL["boss"]
    elif elite:
        pool = ENEMY_POOL["elite"]
    elif floor < num_floors // 2:
        pool = ENEMY_POOL["early"]
    else:
        pool = ENEMY_POOL["mid"]
    return rng.choice(pool).model_copy(deep=True)
