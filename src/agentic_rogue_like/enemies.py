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
    "early": [
        Enemy(id="rat-swarm", name="Rat Swarm", hp=18, attack=3),
        Enemy(id="cave-slime", name="Cave Slime", hp=22, attack=2),
    ],
    "mid": [
        Enemy(id="bandit", name="Bandit", hp=32, attack=5),
        Enemy(id="wild-boar", name="Wild Boar", hp=28, attack=6),
    ],
    "elite": [
        Enemy(id="ogre", name="Ogre", hp=55, attack=8),
    ],
    "boss": [
        Enemy(id="the-warden", name="The Warden", hp=90, attack=10),
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
