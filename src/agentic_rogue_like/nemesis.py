"""The nemesis: the enemy that killed the player last run, back for revenge.

The client keeps the killer (name, description, attack name, moves) and sends
it with the next new run (api.NewRunRequest.nemesis). It returns once, as the
first elite room the player enters in act 1 (engine._room_enemy), as
"Returned <name>": its own look and moves, but its strength set fresh from the
elite budget - the attack at the budget's top, the HP chosen so that its
threat (threat.py) sits in the middle of the elite threat range - and without
an elite affix. The AGI opens the fight saying it brought it back.
"""

from __future__ import annotations

from pydantic import ValidationError

from .agent.budgets import tier_budget
from .models import (
    MAX_NEMESIS_DESCRIPTION_LENGTH,
    MAX_NEMESIS_NAME_LENGTH,
    PROGRAM_ONLY_MOVES,
    Enemy,
    NemesisSpec,
)
from .threat import threat

RETURNED_PREFIX = "Returned "

# Threat is proportional to HP except where Malware prices the fight's
# length (threat._malware): a few rescaling rounds settle that too.
_FIT_ROUNDS = 6
_START_HP = 70


def nemesis_line(name: str) -> str:
    """The AGI's line as the nemesis' fight opens - in the log's AGI form."""
    return f'AGI: "I brought {name} back. It remembers you."'


def nemesis_enemy(spec: NemesisSpec, enemy_id: str = "nemesis") -> Enemy | None:
    """The nemesis as an elite, its threat in the middle of the elite range -
    None if no HP lands it inside that range."""
    budget = tier_budget("elite")
    low, high = budget.threat_range()
    target = (low + high) / 2
    enemy = Enemy(
        id=enemy_id,
        name=f"{RETURNED_PREFIX}{spec.name}",
        hp=_START_HP,
        attack=budget.max_attack,
        attack_name=spec.attack_name,
        description=spec.description,
        moves=[m.model_copy() for m in spec.moves],
        body_shape=spec.body_shape,
        feature=spec.feature,
        taunt=nemesis_line(spec.name),
        nemesis=True,
    )
    for _ in range(_FIT_ROUNDS):
        value = threat(enemy)
        if value <= 0:
            return None
        hp = max(1, round(enemy.hp * target / value))
        if hp == enemy.hp:
            break
        enemy = enemy.model_copy(update={"hp": hp})
    return enemy if low <= threat(enemy) <= high else None


def valid_nemesis(spec: NemesisSpec | None) -> NemesisSpec | None:
    """`spec` if it makes a fightable elite, else None."""
    if spec is None or nemesis_enemy(spec) is None:
        return None
    return spec


def spec_from_enemy(enemy: Enemy, final_boss: bool = False) -> NemesisSpec | None:
    """What the client keeps of the enemy that just killed the player, to send
    back with its next run - its own name (a returned nemesis loses the
    prefix again, so it never piles up), its look and its move set without
    the moves the game adds in program mode. None for the final boss, which
    is the AGI itself, and for anything that makes no fightable elite."""
    if final_boss:
        return None
    name = enemy.name
    while name.startswith(RETURNED_PREFIX):
        name = name[len(RETURNED_PREFIX) :]
    try:
        spec = NemesisSpec(
            name=name[:MAX_NEMESIS_NAME_LENGTH],
            description=enemy.description[:MAX_NEMESIS_DESCRIPTION_LENGTH],
            attack_name=enemy.attack_name[:MAX_NEMESIS_NAME_LENGTH],
            moves=[m.model_copy() for m in enemy.moves if m.kind not in PROGRAM_ONLY_MOVES],
            body_shape=enemy.body_shape,
            feature=enemy.feature,
        )
    except ValidationError:
        return None
    return valid_nemesis(spec)
