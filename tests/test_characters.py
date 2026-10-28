import random

import pytest

from agentic_rogue_like import combat
from agentic_rogue_like.artifacts import (
    ARTIFACT_POOL,
    VIBE_CODER_ARTIFACT_POOL,
    gain_artifact,
    roll_artifact_offer,
)
from agentic_rogue_like.cards import (
    REWARD_POOL,
    VIBE_CODER_REWARD_POOL,
    can_upgrade,
    roll_card_reward,
    starter_deck,
    vibe_coder_starter_deck,
)
from agentic_rogue_like.characters import CHARACTERS
from agentic_rogue_like.combat import (
    CARDS_PER_TURN,
    CHAIN_MAX_PLAYS,
    HAND_SIZE,
    action_preview,
    auto_resolve_combat,
    end_turn,
    hallucination_chance,
    play_card,
    start_combat,
)
from agentic_rogue_like.engine import new_run
from agentic_rogue_like.models import (
    CONTROL_FLOW_TYPES,
    Card,
    CardType,
    Character,
    Enemy,
    PlayerState,
    Rarity,
)
from agentic_rogue_like.shop import roll_shop
from agentic_rogue_like.style import PlayStyle, card_styles

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


def _vibe_fight(hand: list[Card], deck: list[Card] | None = None, artifacts=None):
    """A Vibe-Coder fight whose hand is exactly `hand`, with `deck` left to draw."""
    player = _vibe_player(hand)
    state, _ = start_combat(
        [], _enemy(), random.Random(1), artifacts, character=Character.VIBE_CODER
    )
    state.hand = list(hand)
    state.draw_pile = list(deck if deck is not None else [PROMPT] * 20)
    return player, state


def test_new_run_as_vibe_coder_uses_his_stats_and_deck() -> None:
    run = new_run(1, character=Character.VIBE_CODER)

    assert run.player.character is Character.VIBE_CODER
    assert run.player.hp == run.player.max_hp == VIBE.hp
    assert [c.name for c in run.player.deck] == [c.name for c in vibe_coder_starter_deck()]


def test_every_starter_deck_shows_every_strategy() -> None:
    # One card of each style the AGI reads (style.py) - control flow only in
    # program mode, where it does something - and all of them STARTER, so the
    # rewards stay upgrades and the AGI still reads no style off a fresh deck.
    for hero in CHARACTERS.values():
        for program_mode in (False, True):
            deck = hero.deck(program_mode)
            shown = set().union(*(card_styles(c) for c in deck))
            wanted = set(PlayStyle) if program_mode else set(PlayStyle) - {PlayStyle.PROGRAM}
            assert shown == wanted, (hero.name, program_mode)
            assert all(c.rarity is Rarity.STARTER for c in deck)
            assert all(can_upgrade(c) for c in deck if c.name != "Prefetch")
            assert len({c.id for c in deck}) == len(deck)


def test_a_program_mode_run_starts_with_the_program_deck() -> None:
    for character in Character:
        hero = CHARACTERS[character]
        run = new_run(1, character=character, program_mode=True)

        assert [c.name for c in run.player.deck] == [c.name for c in hero.deck(True)]
        assert any(c.type in CONTROL_FLOW_TYPES for c in run.player.deck)


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


# ---- the Vibe-Coder's reward cards


def _vibe_card(name: str) -> Card:
    return next(c for c in VIBE_CODER_REWARD_POOL if c.name == name).model_copy(deep=True)


def test_vibe_reward_cards_are_well_formed() -> None:
    names = [c.name for c in REWARD_POOL + VIBE_CODER_REWARD_POOL]
    assert len(set(names)) == len(names)
    assert all(c.rarity is not Rarity.STARTER for c in VIBE_CODER_REWARD_POOL)
    # token-free cards that refill the hand could otherwise loop forever
    for card in VIBE_CODER_REWARD_POOL:
        if card.type is CardType.RETRIEVE or card.draw:
            assert card.exhaust, card.name


def test_only_the_vibe_coder_is_offered_his_cards() -> None:
    vibe_names = {c.name for c in VIBE_CODER_REWARD_POOL}
    rng = random.Random(1)
    chronos_offers = {c.name for _ in range(300) for c in roll_card_reward(rng)}
    vibe_offers = {c.name for _ in range(300) for c in roll_card_reward(rng, pool=VIBE.reward_pool)}

    assert not chronos_offers & vibe_names
    assert vibe_names <= vibe_offers


def test_vibe_coder_rewards_and_shops_come_from_his_pool() -> None:
    pool = {c.name for c in VIBE.reward_pool}
    vibe_names = {c.name for c in VIBE_CODER_REWARD_POOL}
    seen: set[str] = set()
    for seed in range(40):
        run = new_run(seed, character=Character.VIBE_CODER)
        seen |= {c.name for kit in run.kit_offer for c in kit.cards}
        seen |= {item.card.name for item in roll_shop(run).cards}

    assert seen <= pool
    assert seen & vibe_names


def test_tab_tab_tab_makes_the_next_card_free() -> None:
    player, state = _vibe_fight([_vibe_card("Tab-Tab-Tab"), BIG, BIG])

    play_card(state, 0, 0, player, random.Random(2))
    play_card(state, 0, 0, player, random.Random(2))
    assert state.tokens_used == 0
    play_card(state, 0, 0, player, random.Random(2))
    assert state.tokens_used == BIG.token_cost


def test_a_free_play_doesnt_carry_over_to_the_next_turn() -> None:
    player, state = _vibe_fight([_vibe_card("Tab-Tab-Tab")])
    play_card(state, 0, 0, player, random.Random(2))

    end_turn(state, player, random.Random(2))

    assert state.free_plays == 0


def test_pair_programming_makes_the_first_card_of_every_turn_free() -> None:
    player, state = _vibe_fight([_vibe_card("Pair Programming")])
    play_card(state, 0, 4, player, random.Random(2))
    end_turn(state, player, random.Random(2))
    used = state.tokens_used
    state.hand = [BIG, BIG]

    play_card(state, 0, 0, player, random.Random(2))
    assert state.tokens_used == used
    play_card(state, 0, 0, player, random.Random(2))
    assert state.tokens_used == used + BIG.token_cost


def test_copy_paste_is_free_and_fetches_the_last_card() -> None:
    copy_paste = _vibe_card("Copy-Paste")
    player, state = _vibe_fight([BIG, copy_paste], deck=[])

    play_card(state, 0, 0, player, random.Random(2))
    play_card(state, 0, 0, player, random.Random(2))

    assert state.tokens_used == BIG.token_cost
    assert state.hand == [BIG]
    assert copy_paste in state.banished_pile


def test_ship_it_grows_with_every_card_played_this_turn() -> None:
    ship_it = _vibe_card("Ship It")
    player, state = _vibe_fight([PROMPT, PROMPT])

    assert action_preview(state, ship_it, player, 0) == 0
    play_card(state, 0, 0, player, random.Random(2))
    play_card(state, 0, 0, player, random.Random(2))
    assert action_preview(state, ship_it, player, 0) == 2 * ship_it.scale_value


def test_vibe_check_blocks_more_the_emptier_the_field() -> None:
    vibe_check = _vibe_card("Vibe Check")
    player, state = _vibe_fight([COPILOT])

    assert action_preview(state, vibe_check, player, 1) == 1 + 5 * 2
    play_card(state, 0, 0, player, random.Random(2))
    state.plays_this_turn = 0  # leave Copilot's bonus out of it
    assert action_preview(state, vibe_check, player, 1) == 1 + 4 * 2


def test_rubber_duck_makes_hallucinations_fizzle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(combat, "HALLUCINATION_CHANCE", 1.0)
    player, state = _vibe_fight([_vibe_card("Rubber Duck"), BIG])
    play_card(state, 0, 4, player, random.Random(2))
    state.tokens_used = VIBE.token_limit

    log = play_card(state, 0, 0, player, random.Random(2))

    assert "rubber duck" in log
    assert player.hp == 50
    assert state.enemy_hp == 200


# ---- the Vibe-Coder's artifacts


def _vibe_artifact(name: str):
    return next(a for a in VIBE_CODER_ARTIFACT_POOL if a.name == name)


def test_only_the_vibe_coder_is_offered_his_artifacts() -> None:
    vibe_ids = {a.id for a in VIBE_CODER_ARTIFACT_POOL}
    rng = random.Random(1)
    chronos_offers = {a.id for _ in range(200) for a in roll_artifact_offer(rng, [])}
    vibe_offers = {
        a.id for _ in range(200) for a in roll_artifact_offer(rng, [], pool=VIBE.artifact_pool)
    }

    assert not chronos_offers & vibe_ids
    assert vibe_ids <= vibe_offers
    assert len({a.id for a in ARTIFACT_POOL + VIBE_CODER_ARTIFACT_POOL}) == len(
        ARTIFACT_POOL + VIBE_CODER_ARTIFACT_POOL
    )


def test_vibe_coder_artifact_offers_and_shops_come_from_his_pool() -> None:
    pool = {a.id for a in VIBE.artifact_pool}
    seen: set[str] = set()
    for seed in range(40):
        run = new_run(seed, character=Character.VIBE_CODER)
        seen |= {a.id for a in run.artifact_offer}
        seen |= {item.artifact.id for item in roll_shop(run).artifacts}

    assert seen <= pool
    assert seen & {a.id for a in VIBE_CODER_ARTIFACT_POOL}


def test_pro_plan_widens_the_context_window() -> None:
    _, state = _vibe_fight([], artifacts=[_vibe_artifact("Pro Plan")])

    assert state.token_limit == VIBE.token_limit + 1


def test_lo_fi_beats_and_max_mode_change_the_tokens_freed_per_turn() -> None:
    for name, delta in (("Lo-fi Beats", 1), ("Max Mode", -1)):
        player, state = _vibe_fight([], artifacts=[_vibe_artifact(name)])
        state.tokens_used = VIBE.token_limit

        end_turn(state, player, random.Random(2))

        assert state.tokens_used == VIBE.token_limit - (VIBE.token_regen + delta), name


def test_max_mode_raises_attack() -> None:
    player = _vibe_player([])

    gain_artifact(player, _vibe_artifact("Max Mode"))

    assert player.attack == 3


def test_mechanical_keyboard_makes_the_first_card_of_the_fight_free() -> None:
    player, state = _vibe_fight([BIG, BIG, BIG], artifacts=[_vibe_artifact("Mechanical Keyboard")])

    play_card(state, 0, 0, player, random.Random(2))
    assert state.tokens_used == 0
    play_card(state, 0, 0, player, random.Random(2))
    assert state.tokens_used == BIG.token_cost

    end_turn(state, player, random.Random(2))
    assert state.free_plays == 0


def test_system_prompt_halves_the_hallucination_chance() -> None:
    _, plain = _vibe_fight([])
    _, prompted = _vibe_fight([], artifacts=[_vibe_artifact("System Prompt")])

    assert hallucination_chance(prompted) == hallucination_chance(plain) / 2
