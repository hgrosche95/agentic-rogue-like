"""Move sets for regular enemies (models.EnemyMove, combat._roll_enemy_move)."""

import random
from collections import Counter

import pytest
from pydantic import ValidationError

from agentic_rogue_like.combat import (
    EnemyIntentType,
    end_turn,
    enemy_block_gain,
    intent_hits,
    start_combat,
)
from agentic_rogue_like.enemies import escalate
from agentic_rogue_like.models import (
    Card,
    CardType,
    Enemy,
    EnemyMove,
    MoveKind,
    PlayerState,
    default_moves,
)

STRIKE = Card(id="strike", name="Strike", type=CardType.ATTACK, value=1, description="")
ARMOR = Card(id="armor", name="Armor", type=CardType.ARMOR, value=1, description="")


def _player() -> PlayerState:
    return PlayerState(hp=500, max_hp=500, attack=0, deck=[STRIKE] * 10)


def _enemy(moves: list[EnemyMove], attack: int = 20) -> Enemy:
    return Enemy(id="foe", name="Foe", hp=999, attack=attack, attack_name="Slam", moves=moves)


def _intents(enemy: Enemy, turns: int = 400, seed: int = 1) -> list[EnemyIntentType]:
    player = _player()
    state, _ = start_combat(player.deck, enemy, random.Random(seed))
    rng = random.Random(seed + 1)
    seen = [state.enemy_intent]
    for _ in range(turns):
        end_turn(state, player, rng, discard=None)
        player.hp = player.max_hp
        seen.append(state.enemy_intent)
    return seen


def test_default_move_set_braces_about_thirty_percent_of_the_time() -> None:
    counts = Counter(_intents(Enemy(id="e", name="E", hp=999, attack=5, attack_name="Hit")))

    assert set(counts) == {EnemyIntentType.ATTACK, EnemyIntentType.DEFEND}
    assert 0.24 < counts[EnemyIntentType.DEFEND] / sum(counts.values()) < 0.36


def test_moves_fill_in_their_kinds_defaults() -> None:
    barrage = EnemyMove(kind=MoveKind.BARRAGE)
    assert (barrage.power, barrage.hits) == (25, 3)
    assert EnemyMove(kind=MoveKind.CHARGE).power == 140
    assert EnemyMove(kind=MoveKind.ATTACK).hits is None


@pytest.mark.parametrize(
    "moves",
    [
        [EnemyMove(kind=MoveKind.DEFEND), EnemyMove(kind=MoveKind.PURGE)],  # no always-on hit
        [EnemyMove(kind=MoveKind.ATTACK)] * 5,  # too many moves
        [],
    ],
)
def test_invalid_move_sets_are_rejected(moves: list[EnemyMove]) -> None:
    with pytest.raises(ValidationError):
        _enemy(moves)


def test_only_a_barrage_has_hits() -> None:
    with pytest.raises(ValidationError):
        EnemyMove(kind=MoveKind.ATTACK, hits=2)


def test_move_power_scales_the_hit_and_the_block() -> None:
    enemy = _enemy(
        [EnemyMove(kind=MoveKind.ATTACK, power=50), EnemyMove(kind=MoveKind.DEFEND, power=150)]
    )
    state, _ = start_combat(_player().deck, enemy, random.Random(1))

    state.enemy_move, state.enemy_intent = 0, EnemyIntentType.ATTACK
    assert intent_hits(state) == [(11, 16)]  # 20 * 50% + d6
    state.enemy_move, state.enemy_intent = 1, EnemyIntentType.DEFEND
    assert enemy_block_gain(state) == 30


def test_regular_enemy_barrage_uses_its_own_hits_and_power() -> None:
    enemy = _enemy([EnemyMove(kind=MoveKind.BARRAGE, hits=4, power=30)])
    state, _ = start_combat(_player().deck, enemy, random.Random(1))

    assert state.enemy_intent is EnemyIntentType.BARRAGE
    assert intent_hits(state) == [(7, 9)] * 4  # 20 * 30% + d3, four times


def test_charge_is_followed_by_its_overload_and_never_straight_by_another_charge() -> None:
    enemy = _enemy(
        [
            EnemyMove(kind=MoveKind.ATTACK, weight=1),
            EnemyMove(kind=MoveKind.CHARGE, weight=10, power=200),
        ]
    )
    intents = _intents(enemy)

    assert EnemyIntentType.OVERLOAD in intents
    for before, after in zip(intents, intents[1:], strict=False):
        if before is EnemyIntentType.CHARGE:
            assert after is EnemyIntentType.OVERLOAD
        if before is EnemyIntentType.OVERLOAD:
            assert after is not EnemyIntentType.CHARGE


def test_overload_hits_with_its_charges_power() -> None:
    enemy = _enemy([EnemyMove(kind=MoveKind.CHARGE, power=200), EnemyMove(kind=MoveKind.ATTACK)])
    state, _ = start_combat(_player().deck, enemy, random.Random(1))
    state.enemy_move, state.enemy_intent = 0, EnemyIntentType.OVERLOAD

    assert intent_hits(state) == [(41, 46)]


def test_purge_is_only_rolled_with_a_permanent_on_the_field() -> None:
    enemy = _enemy(
        [EnemyMove(kind=MoveKind.ATTACK, weight=1), EnemyMove(kind=MoveKind.PURGE, weight=10)]
    )
    assert EnemyIntentType.PURGE not in _intents(enemy, turns=100)

    player = _player()
    state, _ = start_combat(player.deck, enemy, random.Random(1))
    state.field[2] = ARMOR
    state.enemy_move, state.enemy_intent = 1, EnemyIntentType.PURGE
    log = end_turn(state, player, random.Random(2), discard=None)

    assert state.field[2] is None
    assert ARMOR in state.banished_pile
    assert any("purges your Armor" in line for line in log)


def test_named_moves_show_up_in_the_log() -> None:
    enemy = _enemy(
        [
            EnemyMove(kind=MoveKind.ATTACK, name="Tusk Charge"),
            EnemyMove(kind=MoveKind.BARRAGE, name="Bristle Volley"),
        ]
    )
    player = _player()
    state, _ = start_combat(player.deck, enemy, random.Random(1))

    state.enemy_move, state.enemy_intent = 0, EnemyIntentType.ATTACK
    assert "uses Tusk Charge" in end_turn(state, player, random.Random(2), discard=None)[0]
    state.enemy_move, state.enemy_intent = 1, EnemyIntentType.BARRAGE
    assert "uses Bristle Volley" in end_turn(state, player, random.Random(2), discard=None)[0]


def test_escalation_scales_every_move_through_the_attack_stat() -> None:
    enemy = _enemy([EnemyMove(kind=MoveKind.BARRAGE, power=50)], attack=10)
    stronger = escalate(enemy, floor=0, num_floors=8, act=2)  # x1.21

    assert stronger.moves == enemy.moves
    state, _ = start_combat(_player().deck, stronger, random.Random(1))
    assert intent_hits(state)[0] == (7, 9)  # round(12 * 50%) + d3


def test_default_moves_are_independent_copies() -> None:
    first, second = default_moves(), default_moves()
    first[0].weight = 9
    assert second[0].weight == 3
