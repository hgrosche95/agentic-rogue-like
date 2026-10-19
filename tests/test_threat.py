import pytest

from agentic_rogue_like.agent.budgets import _BUDGETS
from agentic_rogue_like.balance_sim import (
    calibrate_threat,
    evaluate_threat,
    mean_damage_taken,
    smart_bot,
    threat_samples,
)
from agentic_rogue_like.enemies import ENEMY_POOL
from agentic_rogue_like.models import Enemy, EnemyMove, MoveKind
from agentic_rogue_like.threat import _intent_frequencies, threat, threat_profile


def _enemy(hp: int = 50, attack: int = 10, moves: list[EnemyMove] | None = None) -> Enemy:
    extra = {} if moves is None else {"moves": moves}
    return Enemy(id="e", name="E", hp=hp, attack=attack, attack_name="Hit", **extra)


def test_default_move_set_braces_thirty_percent_of_the_time() -> None:
    assert _intent_frequencies(_enemy().moves) == pytest.approx({0: 0.3, 1: 0.7})


def test_every_charge_is_followed_by_its_overload() -> None:
    moves = [EnemyMove(kind=MoveKind.ATTACK), EnemyMove(kind=MoveKind.CHARGE)]
    # attack -> attack or charge (1:1), charge -> overload, overload -> attack
    expected = {0: 0.5, 1: 0.25, ("overload", 1): 0.25}
    assert _intent_frequencies(moves) == pytest.approx(expected)


def test_threat_grows_with_hp_and_attack() -> None:
    assert threat(_enemy(hp=60)) > threat(_enemy(hp=50))
    assert threat(_enemy(attack=12)) > threat(_enemy(attack=10))


def test_block_makes_an_enemy_last_longer() -> None:
    tank = [EnemyMove(kind=MoveKind.ATTACK), EnemyMove(kind=MoveKind.DEFEND, power=150)]
    weaker_guard = [EnemyMove(kind=MoveKind.ATTACK), EnemyMove(kind=MoveKind.DEFEND, power=50)]

    assert (
        threat_profile(_enemy(moves=tank)).turns > threat_profile(_enemy(moves=weaker_guard)).turns
    )


def test_armor_hurts_a_barrage_more_than_one_big_hit() -> None:
    from agentic_rogue_like.threat import DEFAULT_MODEL, ThreatModel

    barrage = _enemy(moves=[EnemyMove(kind=MoveKind.BARRAGE, hits=4, power=25)])
    attack = _enemy(moves=[EnemyMove(kind=MoveKind.ATTACK)])
    armored = ThreatModel(**{**DEFAULT_MODEL.__dict__, "armor": DEFAULT_MODEL.armor + 2})

    def loss(enemy: Enemy) -> float:
        return 1 - threat(enemy, armored) / threat(enemy)

    assert loss(barrage) > loss(attack)


@pytest.mark.parametrize("tier", ["early", "mid", "elite"])
def test_static_pool_sits_inside_its_tiers_threat_range(tier: str) -> None:
    low, high = _BUDGETS[tier].threat_range()
    for enemy in ENEMY_POOL[tier]:
        assert low <= threat(enemy) <= high


def test_tier_threat_ranges_rise() -> None:
    ranges = [_BUDGETS[t].threat_range() for t in ("early", "mid", "elite", "boss")]
    assert all(a[0] < b[0] and a[1] < b[1] for a, b in zip(ranges, ranges[1:], strict=False))


# Very different move sets, each given the HP that puts its threat at 12 -
# the promise behind threat budgets: same threat, similar fight.
_ARCHETYPES = {
    "default": None,
    "tank": [
        EnemyMove(kind=MoveKind.DEFEND, weight=3, power=150),
        EnemyMove(kind=MoveKind.ATTACK, weight=2),
    ],
    "barrage": [
        EnemyMove(kind=MoveKind.BARRAGE, weight=3, hits=4, power=35),
        EnemyMove(kind=MoveKind.ATTACK, weight=1),
    ],
    "charger": [
        EnemyMove(kind=MoveKind.ATTACK, weight=2),
        EnemyMove(kind=MoveKind.CHARGE, weight=2, power=180),
    ],
    "purger": [
        EnemyMove(kind=MoveKind.ATTACK, weight=2),
        EnemyMove(kind=MoveKind.PURGE, weight=2, power=60),
        EnemyMove(kind=MoveKind.DEFEND, weight=1),
    ],
}


@pytest.mark.parametrize("name", list(_ARCHETYPES))
def test_equal_threat_means_similar_damage_in_simulated_fights(name: str) -> None:
    target = 12.0
    moves = _ARCHETYPES[name]
    hp = min(range(15, 200), key=lambda h: abs(threat(_enemy(hp=h, moves=moves)) - target))
    enemy = _enemy(hp=hp, moves=moves)

    taken = mean_damage_taken(enemy, smart_bot, fights=300, seed=name)

    assert taken == pytest.approx(target, rel=0.3)


def test_calibration_recovers_a_useful_model_from_a_small_sample() -> None:
    samples = threat_samples(smart_bot, enemies=60, fights=20, seed=3)
    fit = calibrate_threat(samples[:40])

    assert fit.r2 > 0.7
    assert evaluate_threat(fit.model, samples[40:]).r2 > 0.6
