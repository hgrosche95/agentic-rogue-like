"""The reward card pool and the card mechanics it introduced."""

import random

from agentic_rogue_like.cards import REWARD_POOL, reward_card, roll_card_reward, starter_deck
from agentic_rogue_like.combat import CombatState, end_turn, play_card
from agentic_rogue_like.models import (
    PERMANENT_CARD_TYPES,
    Card,
    CardType,
    Enemy,
    PlayerState,
    Rarity,
)


def _card(name: str) -> Card:
    return next(c for c in REWARD_POOL if c.name == name).model_copy(deep=True)


def _filler(i: int) -> Card:
    return Card(id=f"f{i}", name=f"Filler {i}", type=CardType.BLOCK, value=1, description="")


def _state(hand: list[Card], **piles: list[Card]) -> CombatState:
    return CombatState(
        enemy=Enemy(id="foe", name="Foe", hp=200, attack=5, attack_name="Slam"),
        enemy_hp=200,
        hand=hand,
        draw_pile=piles.get("draw_pile", [_filler(i) for i in range(10, 20)]),
        discard_pile=piles.get("discard_pile", []),
        banished_pile=piles.get("banished_pile", []),
    )


def _player() -> PlayerState:
    return PlayerState(hp=40, max_hp=60, attack=3, deck=[])


def test_pool_has_unique_names_and_ids() -> None:
    assert len({c.name for c in REWARD_POOL}) == len(REWARD_POOL)
    assert len({c.id for c in REWARD_POOL}) == len(REWARD_POOL)
    assert all(c.rarity is not Rarity.STARTER for c in REWARD_POOL)


def test_cards_that_refill_the_hand_are_one_shot() -> None:
    # Without energy, a reusable one of these would allow an endless loop.
    for card in REWARD_POOL:
        if card.type in (CardType.DRAW, CardType.RETRIEVE, CardType.RESTORE) or card.draw:
            assert card.exhaust, card.name


def test_roll_card_reward_offers_three_distinct_cards() -> None:
    rng = random.Random(4)
    for elite in (False, True):
        for _ in range(50):
            offer = roll_card_reward(rng, elite=elite)
            assert len(offer) == 3
            assert len({c.name for c in offer}) == 3


def test_reward_card_gets_an_id_unique_in_the_deck() -> None:
    deck = starter_deck()
    for _ in range(3):
        deck.append(reward_card(_card("Zero-Day"), deck))
    assert len({c.id for c in deck}) == len(deck)


def test_one_shot_card_is_banished_even_next_to_recycling() -> None:
    recycling = next(c for c in starter_deck() if c.type is CardType.RECYCLING)
    state = _state([_card("Zero-Day")])
    state.field[4] = recycling
    play_card(state, 0, 0, _player(), random.Random(1))
    assert state.enemy_hp == 200 - (16 + 3)
    assert [c.name for c in state.banished_pile] == ["Zero-Day"]
    assert all(c.name != "Zero-Day" for c in state.draw_pile)


def test_discard_cost_throws_away_other_hand_cards() -> None:
    state = _state([_card("Brute Force"), _filler(1), _filler(2)])
    play_card(state, 0, 0, _player(), random.Random(1))
    assert len(state.hand) == 1
    assert len(state.discard_pile) == 2  # one filler + Brute Force itself
    assert state.enemy_hp == 200 - 14


def test_multi_hit_adds_attack_stat_per_hit() -> None:
    state = _state([_card("DDoS")])
    play_card(state, 0, 0, _player(), random.Random(1))
    assert state.enemy_hp == 200 - 3 * 3


def test_scaling_attacks_count_their_pile() -> None:
    botnet = _state([_card("Botnet")])
    armor = next(c for c in starter_deck() if c.type is CardType.ARMOR)
    botnet.field[3] = armor
    botnet.field[4] = armor
    play_card(botnet, 0, 0, _player(), random.Random(1))
    assert botnet.enemy_hp == 200 - (1 + 3 + 2 * 3)

    overflow = _state([_card("Stack Overflow")], discard_pile=[_filler(i) for i in range(5)])
    play_card(overflow, 0, 0, _player(), random.Random(1))
    assert overflow.enemy_hp == 200 - (1 + 3 + 5 * 2)

    payload = _state([_card("Payload")], banished_pile=[_filler(1), _filler(2)])
    play_card(payload, 0, 0, _player(), random.Random(1))
    assert payload.enemy_hp == 200 - (2 + 3 + 2 * 4)


def test_load_balancer_boosts_attacks_per_permanent() -> None:
    exploit = next(c for c in starter_deck() if c.name == "Exploit")
    state = _state([exploit])
    state.field[3] = _card("Load Balancer")
    state.field[4] = _card("Daemon")
    play_card(state, 0, 0, _player(), random.Random(1))
    assert state.enemy_hp == 200 - (5 + 3 + 2)


def test_rollback_returns_most_recent_graveyard_cards() -> None:
    state = _state([_card("Rollback")], discard_pile=[_filler(1), _filler(2), _filler(3)])
    play_card(state, 0, 0, _player(), random.Random(1))
    assert [c.name for c in state.hand] == ["Filler 2", "Filler 3"]
    assert [c.name for c in state.discard_pile] == ["Filler 1"]


def test_undelete_never_fetches_another_undelete() -> None:
    first, second = _card("Undelete"), _card("Undelete")
    state = _state([first], banished_pile=[_filler(1), second])
    play_card(state, 0, 0, _player(), random.Random(1))
    assert [c.name for c in state.hand] == ["Filler 1"]
    assert [c.name for c in state.banished_pile] == ["Undelete", "Undelete"]


def test_memory_dump_discards_the_hand_then_draws() -> None:
    state = _state([_card("Memory Dump"), _filler(1), _filler(2)])
    play_card(state, 0, 0, _player(), random.Random(1))
    assert len(state.hand) == 4
    assert {c.name for c in state.discard_pile} == {"Filler 1", "Filler 2"}


def test_daemon_and_mainframe_act_at_end_of_turn() -> None:
    state = _state([])
    state.field[0] = _card("Daemon")
    state.field[1] = _card("Mainframe")
    player = _player()
    end_turn(state, player, random.Random(1))
    assert state.enemy_hp == 200 - 4
    # 2 block from Mainframe (2 permanents) soaks part of the hit
    assert player.hp >= 40 - (5 + 6 - 2)


def test_daemon_kill_skips_the_enemy_attack() -> None:
    state = _state([])
    state.enemy_hp = 3
    state.field[0] = _card("Daemon")
    player = _player()
    end_turn(state, player, random.Random(1))
    assert state.enemy_hp == 0
    assert player.hp == 40


def test_new_permanents_are_permanent() -> None:
    for name in ("Load Balancer", "Daemon", "Mainframe"):
        assert _card(name).type in PERMANENT_CARD_TYPES
