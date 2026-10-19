"""How dangerous an enemy is, as one number - what its move set costs.

`threat(enemy)` estimates the damage an enemy deals to the player before it
dies, in HP, from its HP, attack stat and move set alone - no simulation.
That turns "is this move set balanced?" into a number the encounter agent
can be held to (see EnemyBudget.threat_range), the way the plain HP/attack
ranges did when every enemy had the same two moves.

The model, per enemy turn on average - each move weighted by how often it
comes up in the long run (see _intent_frequencies):

    damage  = what of the telegraphed hits gets through: every hit shaved by
              `armor` (so a barrage pays for its many small hits), the
              turn's total then soaked by `player_block`; plus
              `purge_damage` for every permanent a purge destroys
    block   = block the enemy raises
    turns   = hp / (player_damage - block)
    threat  = scale * turns * damage

The parameters are not guesses but fitted: `balance-sim --calibrate-threat`
simulates fights against a few hundred random move sets and picks the values
whose threat best predicts the damage those fights dealt. They are fitted
numbers, not measurements - player_damage in particular comes out higher
than what a starter deck deals per turn, because it also soaks up effects
the model leaves out. Re-run the calibration after changing the starter
deck, the player's stats or how moves work, and update DEFAULT_MODEL and the
fit quality noted next to it.

Bosses are left out - they fight with their own phased move set
(combat._roll_boss_intent), which threat() does not model.
"""

from __future__ import annotations

from dataclasses import dataclass

from .combat import ARMORED_BLOCK_FACTOR, ENRAGE_FACTOR, REGEN_FACTOR, THORNY_DAMAGE
from .models import Affix, Enemy, EnemyMove, MoveKind


@dataclass(frozen=True)
class ThreatModel:
    player_damage: float  # damage per turn the enemy's HP has to soak
    armor: float  # flat reduction of every hit
    player_block: float  # block up against an attacking turn, soaks all its hits
    purge_damage: float  # what losing a permanent is worth, in HP
    scale: float = 1.0  # maps the estimate onto damage actually taken


# `balance-sim --calibrate-threat` (seed 1, smart bot, starter deck, 600
# random move sets x 100 fights, fitted on 400): on the 200 held-out move sets
# threat explains 90% of the variance in damage taken (R^2), with a median
# error of 9% per move set. Damage taken ranged from 1 to 95 HP there.
DEFAULT_MODEL = ThreatModel(
    player_damage=24.0, armor=1.0, player_block=6.0, purge_damage=6.0, scale=1.0
)

# Mean of the roll on top of each kind of hit (combat.intent_hits).
_D6_MEAN = 3.5
_D3_MEAN = 2.0
_CHARGE_BLOCK_FACTOR = 0.25  # combat.CHARGE_BLOCK_FACTOR - a charge's own block
# The model never lets an enemy out-block the player completely.
_MIN_NET_PLAYER_DAMAGE = 1.0


@dataclass(frozen=True)
class ThreatProfile:
    """The per-turn averages threat() is built from - handy for explaining a score."""

    damage_per_turn: float
    block_per_turn: float
    turns: float
    threat: float


# A state of the intent chain: a move's index, or ("overload", i) for the
# overload following the charge at index i.
_State = int | tuple[str, int]


def _intent_frequencies(moves: list[EnemyMove]) -> dict[_State, float]:
    """How often each intent comes up in the long run, as fractions of all turns.

    Rolls follow combat._roll_enemy_move: weighted among the moves, a charge
    is always followed by its overload and an overload never straight by a
    charge. A purge is assumed to always be available - the worst case, and
    the usual one once permanents are down.
    """

    def roll(after_overload: bool) -> dict[int, float]:
        options = {
            i: m.weight
            for i, m in enumerate(moves)
            if not (after_overload and m.kind is MoveKind.CHARGE)
        }
        total = sum(options.values())
        return {i: w / total for i, w in options.items()}

    after_move, after_overload = roll(after_overload=False), roll(after_overload=True)
    states: list[_State] = list(range(len(moves)))
    states += [("overload", i) for i, m in enumerate(moves) if m.kind is MoveKind.CHARGE]
    # Power iteration on the (at most 7-state) Markov chain of intents.
    dist = dict.fromkeys(states, 1 / len(states))
    for _ in range(500):
        nxt = dict.fromkeys(states, 0.0)
        for state, p in dist.items():
            if isinstance(state, tuple):
                for i, q in after_overload.items():
                    nxt[i] += p * q
            elif moves[state].kind is MoveKind.CHARGE:
                nxt[("overload", state)] += p
            else:
                for i, q in after_move.items():
                    nxt[i] += p * q
        done = max(abs(nxt[s] - dist[s]) for s in states) < 1e-12
        dist = nxt
        if done:
            break
    return dist


# Attack cards the player plays per turn, for pricing a thorny elite: the
# value at which thorny elites, HP rescaled by with_affix, deal what their
# plain selves do in simulated fights (tests/test_threat.py checks it).
ATTACKS_PER_TURN = 2.2


def _per_turn(enemy: Enemy, attack: int, model: ThreatModel) -> tuple[float, float]:
    """(damage, block) per enemy turn for `enemy` hitting with `attack`."""

    def hit(power: int, die_mean: float) -> float:
        return max(0.0, round(attack * power / 100) + die_mean - model.armor)

    def through_block(hits: float) -> float:
        return max(0.0, hits - model.player_block)

    damage = block = 0.0
    for state, p in _intent_frequencies(enemy.moves).items():
        if isinstance(state, tuple):  # an overload hits with its charge's power
            damage += p * through_block(hit(enemy.moves[state[1]].power, _D6_MEAN))
            continue
        move = enemy.moves[state]
        if move.kind is MoveKind.ATTACK:
            damage += p * through_block(hit(move.power, _D6_MEAN))
        elif move.kind is MoveKind.BARRAGE:
            damage += p * through_block(move.hits * hit(move.power, _D3_MEAN))
        elif move.kind is MoveKind.PURGE:
            damage += p * (through_block(hit(move.power, _D6_MEAN)) + model.purge_damage)
        elif move.kind is MoveKind.DEFEND:
            block += p * round(enemy.attack * move.power / 100)
        elif move.kind is MoveKind.CHARGE:
            block += p * round(enemy.attack * _CHARGE_BLOCK_FACTOR)
    return damage, block


def threat_profile(enemy: Enemy, model: ThreatModel = DEFAULT_MODEL) -> ThreatProfile:
    damage, block = _per_turn(enemy, enemy.attack, model)
    # Elite affixes (combat._affix_after_turn and friends): healing soaks up
    # the player's damage just like block does, rage hits harder for the
    # second half of the enemy's HP - about half its turns.
    if enemy.affix is Affix.ARMORED:
        block += round(enemy.attack * ARMORED_BLOCK_FACTOR)
    elif enemy.affix is Affix.REGENERATING:
        block += round(enemy.attack * REGEN_FACTOR)
    elif enemy.affix is Affix.ENRAGED:
        raged = enemy.attack + round(enemy.attack * ENRAGE_FACTOR)
        damage = (damage + _per_turn(enemy, raged, model)[0]) / 2
    elif enemy.affix is Affix.THORNY:
        damage += THORNY_DAMAGE * ATTACKS_PER_TURN
    turns = enemy.hp / max(model.player_damage - block, _MIN_NET_PLAYER_DAMAGE)
    return ThreatProfile(damage, block, turns, model.scale * turns * damage)


def threat(enemy: Enemy, model: ThreatModel = DEFAULT_MODEL) -> float:
    """Expected HP the enemy takes off the player before it dies (see the module docstring)."""
    return threat_profile(enemy, model).threat
