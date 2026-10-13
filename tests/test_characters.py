import random

import pytest

from agentic_rogue_like import combat
from agentic_rogue_like.cards import starter_deck, vibe_coder_starter_deck
from agentic_rogue_like.characters import CHARACTERS
from agentic_rogue_like.combat import (
    CARDS_PER_TURN,
    CHAIN_MAX_PLAYS,
    HAND_SIZE,
    action_preview,
    auto_resolve_combat,
    end_turn,
    play_card,
    start_combat,
)
from agentic_rogue_like.engine import new_run
from agentic_rogue_like.models import Card, CardType, Character, Enemy, PlayerState

VIBE = CHARACTERS[Character.VIBE_CODER]
PROMPT = Card(id="prompt", name="Prompt", type=CardType.ATTACK, value=4, description="")
SAFE = Card(id="safe", name="Make It Safe", type=CardType.BLOCK, value=4, description="")
BIG = Card(id="big", name="Big", type=CardType.ATTACK, value=10, token_cost=2, description="")
COPILOT = Card(id="copilot", name="Copilot", type=CardType.CHAIN, value=1, description="")
DRINK = Card(id="drink", name="Energy Drink", type=CardType.TOKEN_REGEN, value=1, description="")
COMPACT = Card(
    id="compact", name="/compact", type=CardType.COMPACT, value=4, token_cost=0, description=""
)


def _enemy(hp: int = 200, attack: int = 5) -> Enemy:
    return Enemy(id="foe", name="Foe", hp=hp, attack=attack, attack_name="Slam")


def _vibe_player(deck: list[Card]) -> PlayerState:
    return PlayerState(character=Character.VIBE_CODER, hp=50, max_hp=50, attack=0, deck=deck)


def _vibe_fight(hand: list[Card], deck: list[Card] | None = None):
    """A Vibe-Coder fight whose hand is exactly `hand`, with `deck` left to draw."""
    player = _vibe_player(hand)
    state, _ = start_combat([], _enemy(), random.Random(1), character=Character.VIBE_CODER)
    state.hand = list(hand)
    state.draw_pile = list(deck if deck is not None else [PROMPT] * 20)
    return player, state


def test_new_run_as_vibe_coder_uses_his_stats_and_deck() -> None:
    run = new_run(1, character=Character.VIBE_CODER)

    assert run.player.character is Character.VIBE_CODER
    assert run.player.hp == run.player.max_hp == VIBE.hp
    assert [c.name for c in run.player.deck] == [c.name for c in vibe_coder_starter_deck()]


def test_new_run_defaults_to_dr_chronos() -> None:
    run = new_run(1)

    assert run.player.character is Character.CHRONOS
    assert [c.name for c in run.player.deck] == [c.name for c in starter_deck()]


def test_chronos_ignores_token_costs() -> None:
    player = PlayerState(hp=50, max_hp=50, attack=0, deck=[BIG] * 10)
    state, _ = start_combat(player.deck, _enemy(), random.Random(1))

    for _ in range(HAND_SIZE):
        play_card(state, 0, 0, player, random.Random(2))

    assert state.token_limit is None
    assert state.tokens_used == 0
    assert state.enemy_hp == 200 - HAND_SIZE * BIG.value


def test_vibe_coder_draws_after_every_card_and_pays_tokens() -> None:
    player, state = _vibe_fight([PROMPT, PROMPT, PROMPT])

    log = play_card(state, 0, 0, player, random.Random(2))

    assert len(state.hand) == 3
    assert state.tokens_used == 1
    assert f"1/{VIBE.token_limit} tokens" in log


def test_vibe_coder_draws_one_fewer_at_the_end_of_the_turn() -> None:
    player, state = _vibe_fight([])

    end_turn(state, player, random.Random(2))

    assert len(state.hand) == CARDS_PER_TURN - 1


def test_part_of_the_context_window_frees_up_every_turn() -> None:
    player, state = _vibe_fight([PROMPT] * 4)
    for _ in range(4):
        play_card(state, 0, 0, player, random.Random(2))
    assert state.tokens_used == 4

    end_turn(state, player, random.Random(2))

    assert state.tokens_used == 4 - VIBE.token_regen


def test_energy_drink_frees_an_extra_token_every_turn() -> None:
    player, state = _vibe_fight([DRINK, PROMPT, PROMPT, PROMPT])
    play_card(state, 0, 4, player, random.Random(2))  # the drink stays in slot 5
    for _ in range(3):
        play_card(state, 0, 0, player, random.Random(2))

    end_turn(state, player, random.Random(2))

    assert state.tokens_used == 0


def test_compact_costs_nothing_and_frees_tokens() -> None:
    player, state = _vibe_fight([PROMPT, PROMPT, PROMPT, COMPACT])
    for _ in range(3):
        play_card(state, 0, 0, player, random.Random(2))

    play_card(state, 0, 0, player, random.Random(2))

    assert state.tokens_used == 0


def test_a_card_within_the_window_never_hallucinates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combat, "HALLUCINATION_CHANCE", 1.0)
    player, state = _vibe_fight([PROMPT] * VIBE.token_limit)

    for _ in range(VIBE.token_limit):
        play_card(state, 0, 0, player, random.Random(2))

    assert player.hp == 50
    assert state.enemy_hp == 200 - VIBE.token_limit * PROMPT.value


def test_an_attack_past_the_window_can_hit_yourself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combat, "HALLUCINATION_CHANCE", 1.0)
    player, state = _vibe_fight([BIG])
    state.tokens_used = VIBE.token_limit - 1
    state.player_block = 3

    log = play_card(state, 0, 0, player, random.Random(2))

    assert "hallucinates" in log
    assert state.enemy_hp == 200
    assert player.hp == 50 - (BIG.value - 3)
    assert state.player_block == 0
    assert state.tokens_used == VIBE.token_limit + 1


def test_a_block_past_the_window_can_go_to_the_enemy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combat, "HALLUCINATION_CHANCE", 1.0)
    player, state = _vibe_fight([SAFE])
    state.tokens_used = VIBE.token_limit

    play_card(state, 0, 0, player, random.Random(2))

    assert state.player_block == 0
    assert state.enemy_block == SAFE.value


def test_a_permanent_past_the_window_can_fizzle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combat, "HALLUCINATION_CHANCE", 1.0)
    player, state = _vibe_fight([COPILOT])
    state.tokens_used = VIBE.token_limit

    play_card(state, 0, 0, player, random.Random(2))

    assert state.field[0] is None
    assert COPILOT in state.discard_pile


def test_a_card_past_the_window_can_still_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combat, "HALLUCINATION_CHANCE", 0.0)
    player, state = _vibe_fight([PROMPT])
    state.tokens_used = VIBE.token_limit

    play_card(state, 0, 0, player, random.Random(2))

    assert state.enemy_hp == 200 - PROMPT.value


def test_copilot_boosts_cards_to_its_right_per_card_played_up_to_a_cap() -> None:
    player, state = _vibe_fight([COPILOT])
    play_card(state, 0, 0, player, random.Random(2))  # 1 card played this turn

    assert action_preview(state, PROMPT, player, 1) == PROMPT.value + 1
    state.plays_this_turn = CHAIN_MAX_PLAYS + 5
    assert action_preview(state, PROMPT, player, 1) == PROMPT.value + CHAIN_MAX_PLAYS
    assert action_preview(state, SAFE, player, 1) == SAFE.value + CHAIN_MAX_PLAYS


def test_copilot_count_resets_every_turn() -> None:
    player, state = _vibe_fight([COPILOT])
    play_card(state, 0, 0, player, random.Random(2))

    end_turn(state, player, random.Random(2))

    assert state.plays_this_turn == 0
    assert action_preview(state, PROMPT, player, 1) == PROMPT.value


def test_auto_resolve_never_plays_past_the_window() -> None:
    player = _vibe_player(vibe_coder_starter_deck())
    player.attack = 2

    for seed in range(20):
        player.hp = player.max_hp
        _, log = auto_resolve_combat(player.deck, _enemy(hp=60), player, random.Random(seed))
        assert not any("hallucinates" in line for line in log)
