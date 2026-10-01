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
        Enemy(id="rat-swarm", name="Rat Swarm", hp=34, attack=8, attack_name="Swarm Bite"),
        Enemy(id="cave-slime", name="Cave Slime", hp=38, attack=7, attack_name="Acid Splash"),
    ],
    "mid": [
        Enemy(id="bandit", name="Bandit", hp=50, attack=10, attack_name="Dagger Strike"),
        Enemy(id="wild-boar", name="Wild Boar", hp=56, attack=11, attack_name="Tusk Charge"),
    ],
    "elite": [
        Enemy(id="ogre", name="Ogre", hp=70, attack=12, attack_name="Club Smash"),
    ],
    "boss": [
        Enemy(id="the-warden", name="The Warden", hp=98, attack=13, attack_name="Iron Verdict"),
    ],
    # Waits at the end of act 2 - same budget as the Warden, escalate() makes
    # it the stronger of the two.
    "boss2": [
        Enemy(
            id="the-architect", name="The Architect", hp=102, attack=13, attack_name="Null Decree"
        ),
    ],
}


def tier_floor(floor: int, num_floors: int, act: int = 1) -> int:
    """The floor whose enemy tier (early/mid) an act-`act` room draws from.

    Act 2 has no early tier: its fights pick up where act 1's second half
    left off, and escalate() stacks its extra strength on top of that.
    """
    return floor if act <= 1 else max(floor, num_floors // 2)


def pick_enemy(
    floor: int, num_floors: int, elite: bool, boss: bool, rng: random.Random, act: int = 1
) -> Enemy:
    floor = tier_floor(floor, num_floors, act)
    if boss:
        pool = ENEMY_POOL["boss2" if act >= 2 else "boss"]
    elif elite:
        pool = ENEMY_POOL["elite"]
    elif floor < num_floors // 2:
        pool = ENEMY_POOL["early"]
    else:
        pool = ENEMY_POOL["mid"]
    return rng.choice(pool).model_copy(deep=True)


# Enemies get +10% HP and attack (and with it block - a defending enemy
# blocks its attack stat, see combat.py) for every half of the timeline
# behind them: act 1's second half x1.1, act 2's first half x1.21 and its
# second half x1.331. Applied after an enemy is picked or generated, on top
# of agent/budgets.py, so the encounter agent's envelopes - and the evals
# that check the agent against them - stay exactly as they are.
LATE_SCALING = 1.10


def scaling_steps(floor: int, num_floors: int, act: int = 1) -> int:
    """How many times LATE_SCALING applies to an enemy on `floor` of `act`."""
    return 2 * (act - 1) + (0 if floor < num_floors // 2 else 1)


def escalate(enemy: Enemy, floor: int, num_floors: int, act: int = 1) -> Enemy:
    steps = scaling_steps(floor, num_floors, act)
    if steps == 0:
        return enemy
    factor = LATE_SCALING**steps
    return enemy.model_copy(
        update={"hp": round(enemy.hp * factor), "attack": round(enemy.attack * factor)}
    )
