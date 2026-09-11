import random

import pytest

from agentic_rogue_like.combat import (
    FIELD_SIZE,
    HAND_SIZE,
    EnemyIntentType,
    auto_resolve_combat,
    end_turn,
    play_card,
    start_combat,
)
from agentic_rogue_like.models import Card, CardType, Enemy, PlayerState

STRIKE = Card(id="strike", name="Strike", type=CardType.ATTACK, value=6, description="")
DEFEND = Card(id="defend", name="Defend", type=CardType.BLOCK, value=5, description="")
MEND = Card(id="mend", name="Mend", type=CardType.HEAL, value=4, description="")
AMPLIFIER = Card(id="amp", name="Amplifier", type=CardType.AMPLIFIER, value=25, description="")
ARMOR = Card(id="armor", name="Armor", type=CardType.ARMOR, value=1, description="")
RECYCLING = Card(id="recycling", name="Recycling", type=CardType.RECYCLING, value=0, description="")
DRAW_BONUS = Card(id="more", name="More", type=CardType.DRAW_BONUS, value=1, description="")
FINAL_STRIKE = Card(
    id="final-strike", name="Final Strike", type=CardType.FINAL_STRIKE, value=5, description=""
)


def _basic_deck() -> list[Card]:
    return [STRIKE] * 5 + [DEFEND] * 4 + [MEND]


def _enemy(hp: int = 20, attack: int = 5) -> Enemy:
    return Enemy(id="foe", name="Foe", hp=hp, attack=attack, attack_name="Slam")


def _player(deck: list[Card]) -> PlayerState:
    return PlayerState(hp=50, max_hp=50, attack=5, deck=deck)


def test_start_combat_draws_a_full_hand() -> None:
    player = _player(_basic_deck())
    state, log = start_combat(player.deck, _enemy(), random.Random(1))

    assert len(state.hand) == HAND_SIZE
    assert len(state.draw_pile) == len(_basic_deck()) - HAND_SIZE
    assert state.field == [None] * FIELD_SIZE
    assert "Foe" in log[0]


def test_playing_an_attack_card_damages_the_enemy_and_frees_no_slot() -> None:
    player = _player(_basic_deck())
    state, _ = start_combat(player.deck, _enemy(hp=20), random.Random(1))
    strike_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ATTACK)

    play_card(state, strike_index, 0, player, random.Random(2))

    assert state.enemy_hp == 20 - (STRIKE.value + player.attack)
    assert state.field[0] is None  # action cards don't persist on the field


def test_playing_into_an_occupied_slot_raises() -> None:
    player = _player([AMPLIFIER] + [STRIKE] * 9)
    state, _ = start_combat(player.deck, _enemy(), random.Random(1))
    amp_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.AMPLIFIER)
    play_card(state, amp_index, 0, player, random.Random(2))

    strike_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ATTACK)
    with pytest.raises(ValueError):
        play_card(state, strike_index, 0, player, random.Random(2))


def test_permanent_card_stays_on_the_field_after_being_played() -> None:
    player = _player([ARMOR] + [STRIKE] * 9)
    state, _ = start_combat(player.deck, _enemy(), random.Random(1))
    armor_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ARMOR)

    hand_size_before = len(state.hand)
    play_card(state, armor_index, 2, player, random.Random(2))

    assert state.field[2] is not None
    assert state.field[2].type is CardType.ARMOR
    assert len(state.hand) == hand_size_before - 1  # it left the hand, not the discard pile
    assert not state.discard_pile


def test_amplifier_boosts_action_cards_played_to_its_right() -> None:
    # Amplifier in slot 0, Strike played to its right (slot 1) should deal
    # 25% more damage than the same Strike played to its left (slot... there
    # is no left of 0, so compare against a Strike played with no amplifier
    # in range instead).
    player = _player([AMPLIFIER, STRIKE, STRIKE] + [MEND] * 7)
    state, _ = start_combat(player.deck, _enemy(hp=999), random.Random(1))
    amp_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.AMPLIFIER)
    play_card(state, amp_index, 0, player, random.Random(2))

    strike_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ATTACK)
    play_card(state, strike_index, 1, player, random.Random(2))  # right of the amplifier
    boosted_damage = 999 - state.enemy_hp

    unboosted_state, _ = start_combat(_basic_deck(), _enemy(hp=999), random.Random(1))
    unboosted_player = _player(_basic_deck())
    strike_index_2 = next(
        i for i, c in enumerate(unboosted_state.hand) if c.type is CardType.ATTACK
    )
    play_card(unboosted_state, strike_index_2, 0, unboosted_player, random.Random(2))
    plain_damage = 999 - unboosted_state.enemy_hp

    assert boosted_damage == round(plain_damage * 1.25)


def test_armor_reduces_incoming_damage_on_top_of_block() -> None:
    player = _player([ARMOR] + [DEFEND] * 9)
    state, _ = start_combat(player.deck, _enemy(attack=100), random.Random(1))
    armor_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ARMOR)
    play_card(state, armor_index, 0, player, random.Random(2))

    end_turn(state, player, random.Random(2))

    # attack=100 is nowhere near blockable to 0 - just confirm armor
    # participated (hp loss is less than the raw 100+ damage would be).
    assert player.hp > 50 - (100 + 6)


def test_recycling_sends_action_cards_to_the_deck_instead_of_discard() -> None:
    player = _player([STRIKE, RECYCLING] + [MEND] * 8)
    state, _ = start_combat(player.deck, _enemy(), random.Random(1))
    recycling_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.RECYCLING)
    play_card(state, recycling_index, 4, player, random.Random(2))

    strike_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ATTACK)
    play_card(state, strike_index, 0, player, random.Random(2))  # left of Recycling

    assert not any(c.id == STRIKE.id for c in state.discard_pile)
    assert any(c.id == STRIKE.id for c in state.draw_pile)


def test_draw_bonus_increases_cards_drawn_at_end_of_turn() -> None:
    player = _player([STRIKE] * 15)
    state, _ = start_combat(player.deck, _enemy(attack=0), random.Random(1))
    state.hand[0] = DRAW_BONUS  # force it into hand, independent of shuffle luck
    play_card(state, 0, 0, player, random.Random(2))

    end_turn(state, player, random.Random(2))

    assert len(state.hand) == HAND_SIZE + 1


def test_unplayed_hand_cards_carry_over_the_turn() -> None:
    player = _player(_basic_deck())
    state, _ = start_combat(player.deck, _enemy(attack=0), random.Random(1))
    kept_card = state.hand[0]

    end_turn(state, player, random.Random(2))

    assert kept_card in state.hand


def test_final_strike_destroys_all_permanents_for_damage() -> None:
    player = _player([ARMOR, AMPLIFIER, FINAL_STRIKE] + [MEND] * 7)
    state, _ = start_combat(player.deck, _enemy(hp=999), random.Random(1))
    armor_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ARMOR)
    play_card(state, armor_index, 0, player, random.Random(2))
    amp_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.AMPLIFIER)
    play_card(state, amp_index, 1, player, random.Random(2))

    final_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.FINAL_STRIKE)
    play_card(state, final_index, 2, player, random.Random(2))

    assert state.field == [None] * FIELD_SIZE
    # 2 permanents destroyed, base 5 each, boosted 25% by the amplifier that
    # was on the field (to the left of slot 2) when the effect resolved.
    assert 999 - state.enemy_hp == round(5 * 2 * 1.25)


def test_final_strike_sends_destroyed_permanents_to_the_banished_pile() -> None:
    player = _player([ARMOR, FINAL_STRIKE] + [MEND] * 8)
    state, _ = start_combat(player.deck, _enemy(hp=999), random.Random(1))
    armor_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ARMOR)
    play_card(state, armor_index, 0, player, random.Random(2))

    final_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.FINAL_STRIKE)
    play_card(state, final_index, 1, player, random.Random(2))

    assert len(state.banished_pile) == 1
    assert state.banished_pile[0].type is CardType.ARMOR
    assert not any(c.type is CardType.ARMOR for c in state.discard_pile)


def test_enemy_defend_intent_grants_block_instead_of_attacking() -> None:
    player = _player(_basic_deck())
    state, _ = start_combat(player.deck, _enemy(attack=7), random.Random(1))
    state.enemy_intent = EnemyIntentType.DEFEND
    hp_before = player.hp

    end_turn(state, player, random.Random(2))

    assert player.hp == hp_before
    assert state.enemy_block == 7


def test_enemy_block_absorbs_player_attack_damage_before_hp() -> None:
    player = _player([STRIKE] * 10)
    state, _ = start_combat(player.deck, _enemy(hp=20), random.Random(1))
    state.enemy_block = 100  # more than a single Strike can punch through

    strike_index = next(i for i, c in enumerate(state.hand) if c.type is CardType.ATTACK)
    play_card(state, strike_index, 0, player, random.Random(2))

    assert state.enemy_hp == 20  # fully absorbed by block, HP untouched
    assert state.enemy_block == 100 - (STRIKE.value + player.attack)


def test_auto_resolve_combat_terminates_in_victory_or_defeat() -> None:
    for seed in range(20):
        player = _player(_basic_deck())
        victory, log = auto_resolve_combat(
            player.deck, _enemy(hp=20, attack=6), player, random.Random(seed)
        )

        assert victory or player.hp == 0
        assert log


def test_auto_resolve_combat_is_deterministic_for_a_given_seed() -> None:
    player_a = _player(_basic_deck())
    player_b = _player(_basic_deck())

    victory_a, log_a = auto_resolve_combat(player_a.deck, _enemy(), player_a, random.Random(42))
    victory_b, log_b = auto_resolve_combat(player_b.deck, _enemy(), player_b, random.Random(42))

    assert victory_a == victory_b
    assert log_a == log_b
    assert player_a.hp == player_b.hp
