"""Deterministic dice-based combat resolution - no LLM involved.

Kept deliberately simple for Phase 1: a straight damage race with d6
variance. This is the seam Phase 2 targets next - the encounter agent
decides *which* Enemy shows up, not how a fight plays out.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .models import Enemy, PlayerState


@dataclass
class CombatResult:
    victory: bool
    log: list[str] = field(default_factory=list)


def resolve_combat(player: PlayerState, enemy: Enemy, rng: random.Random) -> CombatResult:
    log: list[str] = [f"A {enemy.name} appears! ({enemy.hp} HP)"]
    enemy_hp = enemy.hp

    while player.hp > 0 and enemy_hp > 0:
        player_damage = player.attack + rng.randint(1, 6)
        enemy_hp -= player_damage
        log.append(f"You deal {player_damage} damage. {enemy.name} at {max(enemy_hp, 0)} HP.")
        if enemy_hp <= 0:
            break

        enemy_damage = enemy.attack + rng.randint(1, 6)
        player.hp = max(player.hp - enemy_damage, 0)
        log.append(f"{enemy.name} deals {enemy_damage} damage. You are at {player.hp} HP.")

    victory = player.hp > 0
    log.append("Victory!" if victory else "You have fallen.")
    return CombatResult(victory=victory, log=log)
