"""The static enemy pool - what the game fights whenever the encounter agent
is off or fails (see agent/encounter_agent.enemy_for_node).

Each regular enemy has a hand-made move set, held to the same budget rules
as an agent-generated one, so falling back to the pool is a change of
authorship, not of difficulty.

This module stays agent-unaware on purpose - agent/encounter_agent.py imports
pick_enemy() as its fallback, so the dependency can only go one way.
"""

from __future__ import annotations

import random

from .models import Affix, Enemy, EnemyMove, MoveKind
from .style import COUNTER_AFFIX, COUNTER_WEIGHT, PlayStyle, answers
from .threat import threat

# Shorthands for the move sets below.
_ATTACK, _DEFEND, _BARRAGE, _CHARGE, _PURGE, _INFECT, _LOCK, _CORRUPT = (
    MoveKind.ATTACK,
    MoveKind.DEFEND,
    MoveKind.BARRAGE,
    MoveKind.CHARGE,
    MoveKind.PURGE,
    MoveKind.INFECT,
    MoveKind.LOCK,
    MoveKind.CORRUPT,
)


def _move(kind: MoveKind, name: str, weight: int, **extra: int) -> EnemyMove:
    return EnemyMove(kind=kind, name=name, weight=weight, **extra)


ENEMY_POOL: dict[str, list[Enemy]] = {
    # Every regular enemy has its own move set and is held to the same rules
    # as one the encounter agent generates (agent/encounter_schema.py): attack
    # inside its tier's range, threat (threat.py) inside its tier's threat
    # range, HP within the loose bounds around it - a test pins that down. HP
    # was solved for each move set so the tiers stay as hard as they were:
    # a barrage or charge costs HP, a strong guard buys some. Mid enemies sit
    # ~12% above the threat they replace: threat.py is calibrated against the
    # starter deck, and by mid-run decks kill faster, so low-HP move sets
    # played easier than their threat says (`balance-sim --pool`: mid win
    # rate 92% before the bump, 90% after, 88% with the old pool).
    "early": [
        Enemy(
            id="rat-swarm",
            name="Rat Swarm",
            hp=31,
            attack=8,
            attack_name="Swarm Bite",
            description="A squeaking carpet of teeth and tails, pouring out of every crack.",
            moves=[
                _move(_ATTACK, "Swarm Bite", 3),
                _move(_BARRAGE, "Gnawing Frenzy", 2, hits=3, power=30),
            ],
        ),
        Enemy(
            id="cave-slime",
            name="Cave Slime",
            hp=44,
            attack=7,
            attack_name="Acid Splash",
            description="A quivering green blob that dissolves all it touches, bones included.",
            moves=[
                _move(_ATTACK, "Acid Splash", 3),
                _move(_DEFEND, "Gelatinous Wall", 2, power=130),
            ],
        ),
        Enemy(
            id="goblin-lookout",
            name="Goblin Lookout",
            hp=31,
            attack=8,
            attack_name="Rusty Shiv",
            description="A twitchy goblin with a bag of rocks and a very good throwing arm.",
            moves=[
                _move(_ATTACK, "Rusty Shiv", 4),
                _move(_CHARGE, "Wind-Up Throw", 1, power=130),
            ],
        ),
        Enemy(
            id="skeleton",
            name="Skeleton",
            hp=32,
            attack=9,
            attack_name="Bone Club",
            description="Rattling bones held together by spite and a dented round shield.",
            moves=[
                _move(_ATTACK, "Bone Club", 3),
                _move(_DEFEND, "Shield Up", 1),
            ],
        ),
        Enemy(
            id="gremlin",
            name="Gremlin",
            hp=33,
            attack=8,
            attack_name="Wrench Whack",
            description="A grinning little saboteur with a wrench and a love of moving parts.",
            moves=[
                _move(_ATTACK, "Wrench Whack", 3),
                _move(_LOCK, "Jam the Gears", 2),
            ],
        ),
    ],
    "mid": [
        Enemy(
            id="bandit",
            name="Bandit",
            hp=50,
            attack=10,
            attack_name="Dagger Strike",
            description="A scarred cutthroat who robs anyone fool enough to walk here alone.",
            moves=[
                _move(_ATTACK, "Dagger Strike", 3),
                _move(_BARRAGE, "Knife Flurry", 1, hits=3, power=35),
                _move(_DEFEND, "Parry", 1, power=90),
            ],
        ),
        Enemy(
            id="wild-boar",
            name="Wild Boar",
            hp=49,
            attack=11,
            attack_name="Gore",
            description="A tusked brute with a hide like bark, maddened by your torchlight.",
            moves=[
                _move(_ATTACK, "Gore", 2),
                _move(_CHARGE, "Tusk Charge", 2, power=160),
            ],
        ),
        Enemy(
            id="rust-monster",
            name="Rust Monster",
            hp=46,
            attack=10,
            attack_name="Corroding Bite",
            description="An armored insect whose feelers turn steel to flaking rust - and eat it.",
            moves=[
                _move(_ATTACK, "Corroding Bite", 3),
                _move(_PURGE, "Devour Metal", 2, power=60),
            ],
        ),
        Enemy(
            id="cultist",
            name="Cultist",
            hp=65,
            attack=9,
            attack_name="Dark Bolt",
            description="A hooded zealot chanting to something that is, unfortunately, listening.",
            moves=[
                _move(_ATTACK, "Dark Bolt", 2),
                _move(_DEFEND, "Unholy Ward", 2, power=120),
                _move(_CHARGE, "Ritual Chant", 1, power=180),
            ],
        ),
        Enemy(
            id="plague-doctor",
            name="Plague Doctor",
            hp=51,
            attack=10,
            attack_name="Bone Saw",
            description="A beaked mask, a bone saw and a cure that is worse than the disease.",
            moves=[
                _move(_ATTACK, "Bone Saw", 3),
                _move(_INFECT, "Miasma", 2, stacks=3),
                _move(_DEFEND, "Beak Mask", 1),
            ],
        ),
        Enemy(
            id="corrupted-scribe",
            name="Corrupted Scribe",
            hp=56,
            attack=10,
            attack_name="Quill Stab",
            description="Its ink writes back. Whatever it touches starts to read wrong.",
            moves=[
                _move(_ATTACK, "Quill Stab", 3),
                _move(_CORRUPT, "Ink Blot", 2, stacks=2),
                _move(_DEFEND, "Tome Shield", 1),
            ],
        ),
    ],
    "elite": [
        Enemy(
            id="ogre",
            name="Ogre",
            hp=62,
            attack=12,
            attack_name="Club Smash",
            description="A hulking ogre dragging a club carved from a whole tree trunk.",
            moves=[
                _move(_ATTACK, "Club Smash", 3),
                _move(_CHARGE, "Ground Pound", 2, power=170),
                _move(_DEFEND, "Thick Hide", 1),
            ],
        ),
        Enemy(
            id="gargoyle",
            name="Gargoyle",
            hp=65,
            attack=12,
            attack_name="Stone Claw",
            description="A winged statue that was never quite as still as it looked.",
            moves=[
                _move(_ATTACK, "Stone Claw", 2),
                _move(_BARRAGE, "Rending Dive", 2, hits=3, power=35),
                _move(_DEFEND, "Petrify", 2, power=150),
            ],
        ),
        Enemy(
            id="mimic",
            name="Mimic",
            hp=56,
            attack=13,
            attack_name="Gnash",
            description="The treasure chest has teeth. And a tongue. And it is very hungry.",
            moves=[
                _move(_ATTACK, "Gnash", 3),
                _move(_PURGE, "Swallow Whole", 1, power=70),
                _move(_DEFEND, "Play Dead", 1, power=120),
            ],
        ),
    ],
    # Bosses fight with their own phased move set (combat._roll_boss_intent),
    # so they keep the plain HP/attack budget and no move set of their own.
    "boss": [
        Enemy(
            id="the-warden",
            name="The Warden",
            hp=98,
            attack=13,
            attack_name="Iron Verdict",
            description="The iron-clad jailer of the deep halls. No prisoner has left its keep.",
        ),
    ],
    # Waits at the end of act 2 - same budget as the Warden, escalate() makes
    # it the stronger of the two.
    "boss2": [
        Enemy(
            id="the-architect",
            name="The Architect",
            hp=102,
            attack=13,
            attack_name="Null Decree",
            description="The mind that drew every corridor of this place - and every trap in them.",
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
    floor: int,
    num_floors: int,
    elite: bool,
    boss: bool,
    rng: random.Random,
    act: int = 1,
    style: PlayStyle | None = None,
) -> Enemy:
    """A tier's enemy - with a `style`, the ones answering it COUNTER_WEIGHT
    times as likely (bosses excepted: their moves are fixed)."""
    floor = tier_floor(floor, num_floors, act)
    if boss:
        pool = ENEMY_POOL["boss2" if act >= 2 else "boss"]
    elif elite:
        pool = ENEMY_POOL["elite"]
    elif floor < num_floors // 2:
        pool = ENEMY_POOL["early"]
    else:
        pool = ENEMY_POOL["mid"]
    weights = [COUNTER_WEIGHT if answers(e, style) else 1 for e in pool]
    if boss or max(weights) == 1:
        # Same draw as before styles existed, so seeded runs stay put.
        return rng.choice(pool).model_copy(deep=True)
    return rng.choices(pool, weights=weights)[0].model_copy(deep=True)


# Enemies get +10% HP and attack (and with it block - a defending enemy
# blocks its attack stat, see combat.py) for every half of the map
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


def with_affix(enemy: Enemy, rng: random.Random, style: PlayStyle | None = None) -> Enemy:
    """`enemy` with a random elite affix, its HP rescaled so its threat
    (threat.py) stays what it was - the affix changes how the fight plays,
    not how hard it is. Threat is proportional to HP, so one ratio does it.
    With a `style`, the affix answering it is COUNTER_WEIGHT times as likely."""
    counter = None if style is None else COUNTER_AFFIX[style]
    if counter is None:
        affix = rng.choice(list(Affix))
    else:
        weights = [COUNTER_WEIGHT if a is counter else 1 for a in Affix]
        affix = rng.choices(list(Affix), weights=weights)[0]
    armed = enemy.model_copy(update={"affix": affix})
    hp = max(1, round(enemy.hp * threat(enemy) / threat(armed)))
    return armed.model_copy(update={"hp": hp})


# An interrupt comes up this share of an enemy's turns (by move weight) -
# the second share once the AGI answers a program-heavy deck.
INTERRUPT_SHARE = 0.25
COUNTER_INTERRUPT_SHARE = 0.4


def with_interrupt(enemy: Enemy, style: PlayStyle | None = None) -> Enemy:
    """Program mode: `enemy` with an interrupt move - now and then it cuts the
    player's program off after a couple of lines, so what runs first matters.
    Against a deck leaning on control flow (style PROGRAM) it interrupts more
    often. Like with_affix, its HP is rescaled to keep its threat (threat.py)."""
    if any(m.kind is MoveKind.INTERRUPT for m in enemy.moves):
        return enemy
    share = COUNTER_INTERRUPT_SHARE if style is PlayStyle.PROGRAM else INTERRUPT_SHARE
    total = sum(m.weight for m in enemy.moves)
    weight = max(1, round(total * share / (1 - share)))
    move = EnemyMove(kind=MoveKind.INTERRUPT, name="Interrupt", weight=min(weight, 10))
    armed = enemy.model_copy(update={"moves": [*enemy.moves, move]})
    hp = max(1, round(enemy.hp * threat(enemy) / threat(armed)))
    return armed.model_copy(update={"hp": hp})
