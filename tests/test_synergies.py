"""The bridges between play styles (cards.py, artifacts.py, style.py) and the
rule that a permanent taken back after its turn is uninstalled."""

import random

from fastapi.testclient import TestClient

from agentic_rogue_like.api import app
from agentic_rogue_like.artifacts import ARTIFACT_POOL
from agentic_rogue_like.cards import (
    PROGRAM_REWARD_POOL,
    REWARD_POOL,
    starter_deck,
    upgrade_card,
)
from agentic_rogue_like.combat import (
    GUARD_BLOCK,
    RECYCLE_MAX_PER_TURN,
    EnemyIntentType,
    attack_damage,
    end_turn,
    incoming_damage,
    play_card,
    quarantine_block,
    start_combat,
    take_back,
    uninstalls,
)
from agentic_rogue_like.models import Card, CardType, Enemy, PlayerState, Status
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.style import PlayStyle, card_styles


def _card(name: str) -> Card:
    pool = REWARD_POOL + PROGRAM_REWARD_POOL + starter_deck()
    return next(c for c in pool if c.name == name).model_copy(deep=True)


def _artifact(name: str):
    return next(a for a in ARTIFACT_POOL if a.name == name)


def _fight(*artifacts: str, program_mode: bool = False, hp: int = 200):
    enemy = Enemy(id="e", name="Foe", hp=hp, attack=8, attack_name="Hit")
    player = PlayerState(hp=100, max_hp=100, attack=0, deck=starter_deck())
    state, _ = start_combat(
        player.deck,
        enemy,
        random.Random(1),
        [_artifact(a) for a in artifacts],
        program_mode=program_mode,
    )
    state.enemy_intent = EnemyIntentType.DEFEND  # nothing hits back
    state.hand = []
    return state, player


def _play(state, player, name: str, slot: int = 0) -> str:
    state.hand.append(_card(name))
    return play_card(state, len(state.hand) - 1, slot, player, random.Random(3))


def _next_turn(state, player) -> None:
    end_turn(state, player, random.Random(4))
    state.enemy_intent = EnemyIntentType.DEFEND
    state.enemy_block = 0


# ---- taking permanents back


def test_a_permanent_played_this_turn_comes_back_to_the_hand() -> None:
    state, player = _fight()
    _play(state, player, "Overclock", 2)
    assert not uninstalls(state, 2)
    take_back(state, "field", 2)
    assert [c.name for c in state.hand] == ["Overclock"]
    assert state.banished_pile == []


def test_a_permanent_from_an_earlier_turn_is_uninstalled() -> None:
    state, player = _fight()
    _play(state, player, "Overclock", 2)
    _next_turn(state, player)
    hand = len(state.hand)
    assert uninstalls(state, 2)
    line = take_back(state, "field", 2, random.Random(0))
    assert "uninstall" in line
    assert state.field[2] is None
    assert [c.name for c in state.banished_pile] == ["Overclock"]
    assert len(state.hand) == hand


def test_uninstalling_works_in_program_mode_too() -> None:
    state, player = _fight(program_mode=True)
    _play(state, player, "Encryption", 0)
    _next_turn(state, player)
    take_back(state, "field", 0, random.Random(0))
    assert state.field == []
    assert [c.name for c in state.banished_pile] == ["Encryption"]


# ---- Failsafe (permanents x one-shot)


def test_failsafe_goes_off_when_kernel_panic_destroys_it() -> None:
    state, player = _fight()
    _play(state, player, "Failsafe", 0)
    _play(state, player, "Kernel Panic", 1)
    # 5 for the one permanent, 14 from the Failsafe itself
    assert state.enemy.hp - state.enemy_hp == 19


def test_failsafe_goes_off_when_it_is_uninstalled_or_purged() -> None:
    state, player = _fight()
    _play(state, player, "Failsafe", 0)
    _next_turn(state, player)
    before = state.enemy_hp
    take_back(state, "field", 0, random.Random(0))
    assert before - state.enemy_hp == 14


def test_failsafe_armors_like_encryption_and_upgrades() -> None:
    assert _card("Failsafe").type is CardType.ARMOR
    assert upgrade_card(_card("Failsafe")).banish_damage > _card("Failsafe").banish_damage


def test_api_finishes_a_fight_an_uninstalled_failsafe_wins() -> None:
    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 3}).json()["run_id"]
    session = get_session(run_id)
    # straight into a fight, whatever the first node is
    enemy = Enemy(id="e", name="Foe", hp=5, attack=1, attack_name="Hit")
    session.combat, _ = start_combat(session.run.player.deck, enemy, random.Random(1))
    state = session.combat
    state.field[0] = _card("Failsafe")
    response = client.post(f"/runs/{run_id}/combat/take-back", json={"zone": "field", "index": 0})
    assert response.status_code == 200
    assert session.combat is None


# ---- Counterstrike (turtle x aggro)


def test_counterstrike_hits_for_the_block_you_have() -> None:
    state, player = _fight()
    counter = _card("Counterstrike")
    assert attack_damage(state, counter, player) == 3
    _play(state, player, "Firewall", 0)
    assert attack_damage(state, counter, player) == 8
    _play(state, player, "Counterstrike", 1)
    assert state.enemy.hp - state.enemy_hp == 8


# ---- Quarantine (malware x turtle)


def test_quarantine_blocks_off_the_enemys_malware() -> None:
    state, player = _fight()
    _play(state, player, "Quarantine", 0)
    state.enemy_status[Status.MALWARE] = 7
    state.enemy_intent = EnemyIntentType.ATTACK
    # one block per Malware, counted in the preview ...
    assert quarantine_block(state) == 7
    unblocked = state.model_copy(update={"enemy_status": {}})
    assert incoming_damage(state)[1] == max(0, incoming_damage(unblocked)[1] - 7)
    # ... and raised at the end of the turn
    log = end_turn(state, player, random.Random(4))
    assert any("quarantine raises 7 block" in line for line in log)


# ---- Recycle Bin (one-shot x graveyard)


def test_recycle_bin_draws_on_a_banish_up_to_its_cap() -> None:
    state, player = _fight()
    state.draw_pile = [_card("Exploit") for _ in range(10)]
    _play(state, player, "Recycle Bin", 0)
    for _ in range(RECYCLE_MAX_PER_TURN + 1):
        _play(state, player, "Zero-Day", 1)
    assert state.recycled_this_turn == RECYCLE_MAX_PER_TURN
    assert sum(c.name == "Exploit" for c in state.hand) == RECYCLE_MAX_PER_TURN
    _next_turn(state, player)
    assert state.recycled_this_turn == 0


def test_glitches_feed_no_banish_payoff() -> None:
    state, player = _fight("Logic Bomb")
    _play(state, player, "Recycle Bin", 0)
    glitch = Card(
        id="g", name="Glitch", type=CardType.GLITCH, value=0, exhaust=True, description=""
    )
    state.hand.append(glitch)
    play_card(state, len(state.hand) - 1, 1, player, random.Random(0))
    assert state.recycled_this_turn == 0
    assert Status.MALWARE not in state.enemy_status


# ---- artifacts


def test_logic_bomb_infects_for_every_banished_card() -> None:
    state, player = _fight("Logic Bomb")
    _play(state, player, "Zero-Day", 0)
    assert state.enemy_status[Status.MALWARE] == 3


def test_stack_trace_adds_damage_per_four_graveyard_cards() -> None:
    state, player = _fight("Stack Trace")
    exploit = _card("Exploit")
    state.discard_pile = [_card("Exploit") for _ in range(11)]
    assert attack_damage(state, exploit, player) == 5 + 2


def test_daemon_worm_infects_when_daemons_fire() -> None:
    state, player = _fight("Daemon Worm")
    _play(state, player, "Daemon", 0)
    _play(state, player, "Daemon", 1)
    end_turn(state, player, random.Random(4))
    # 4 stacks on (2 per Daemon), one fades after biting
    assert state.enemy_status[Status.MALWARE] == 3


def test_retained_state_keeps_block_per_permanent() -> None:
    state, player = _fight("Retained State")
    _play(state, player, "Encryption", 0)
    _play(state, player, "Overclock", 1)
    state.player_block = 9
    end_turn(state, player, random.Random(4))
    assert state.player_block == 6


# ---- Guard Clause (program x turtle)


def _program_damage(*names: str) -> int:
    state, player = _fight(program_mode=True)
    for i, name in enumerate(names):
        _play(state, player, name, i)
    end_turn(state, player, random.Random(4))
    return state.enemy.hp - state.enemy_hp


def test_guard_clause_runs_the_next_action_twice_behind_enough_block() -> None:
    assert GUARD_BLOCK == 5
    # Firewall raises 5 block first: the Exploit after it runs twice
    assert _program_damage("Firewall", "Guard Clause", "Exploit") == 10
    # no block, no second run
    assert _program_damage("Guard Clause", "Exploit") == 5


# ---- style


def test_bridges_feed_both_of_their_styles() -> None:
    assert {PlayStyle.PERMANENTS, PlayStyle.ONE_SHOT} <= card_styles(_card("Failsafe"))
    assert card_styles(_card("Counterstrike")) == {PlayStyle.AGGRO, PlayStyle.TURTLE}
    assert {PlayStyle.MALWARE, PlayStyle.TURTLE} <= card_styles(_card("Quarantine"))
    assert {PlayStyle.ONE_SHOT, PlayStyle.GRAVEYARD} <= card_styles(_card("Recycle Bin"))
    assert card_styles(_card("Guard Clause")) == {PlayStyle.PROGRAM, PlayStyle.TURTLE}


# ---- the balance bot knows the bridges


def test_bot_prefers_a_card_for_the_style_its_deck_leans_on() -> None:
    from agentic_rogue_like.balance_sim import pick_reward

    deck = starter_deck() + [_card("Zero-Day"), _card("Sandbox"), _card("Backup")]
    offer = [_card("Daemon"), _card("Payload")]  # both uncommon
    assert offer[pick_reward(offer, "smart", random.Random(0), deck)].name == "Payload"


def test_bot_skips_a_card_its_deck_cannot_use() -> None:
    from agentic_rogue_like.balance_sim import card_fit

    no_malware = [c for c in starter_deck() if c.applies is None]
    assert card_fit(_card("Quarantine"), no_malware) < 0
    assert card_fit(_card("Quarantine"), starter_deck()) >= 0


def test_bot_takes_bridge_artifacts_only_for_a_fitting_deck() -> None:
    from agentic_rogue_like.balance_sim import pick_artifact

    offer = [_artifact("Daemon Worm"), _artifact("Titanium Chassis")]
    plain = pick_artifact(offer, "smart", random.Random(0), starter_deck())
    assert plain.name == "Titanium Chassis"
    built = pick_artifact(offer, "smart", random.Random(0), starter_deck() + [_card("Daemon")])
    assert built.name == "Daemon Worm"


def test_bot_raises_block_before_counterstrike() -> None:
    from agentic_rogue_like.balance_sim import smart_bot

    state, player = _fight()
    state.enemy_intent = EnemyIntentType.ATTACK
    state.hand = [_card("Counterstrike"), _card("Firewall")]
    smart_bot(state, player, random.Random(0))
    # the Firewall's 5 block went into the Counterstrike
    assert state.enemy.hp - state.enemy_hp == 8


def test_bot_uninstalls_a_failsafe_for_the_kill() -> None:
    from agentic_rogue_like.balance_sim import smart_bot

    state, player = _fight(hp=12)
    _play(state, player, "Failsafe", 0)
    _next_turn(state, player)
    state.hand = []
    smart_bot(state, player, random.Random(0))
    assert state.enemy_hp <= 0


def test_upgraded_quarantine_blocks_more_and_never_less() -> None:
    from agentic_rogue_like.combat import quarantine_block

    state, player = _fight()
    state.field[0] = _card("Quarantine")
    upgraded_state, _ = _fight()
    upgraded_state.field[0] = upgrade_card(_card("Quarantine"))
    for malware in range(1, 9):
        state.enemy_status[Status.MALWARE] = malware
        upgraded_state.enemy_status[Status.MALWARE] = malware
        assert quarantine_block(state) == malware
        assert quarantine_block(upgraded_state) >= malware
    assert quarantine_block(upgraded_state) == 12  # 8 Malware: 1.5 each


def test_every_upgrade_changes_more_than_its_text() -> None:
    from agentic_rogue_like.cards import (
        CARD_UPGRADES,
        VIBE_CODER_PROGRAM_POOL,
        VIBE_CODER_REWARD_POOL,
        vibe_coder_starter_deck,
    )

    pool = (
        REWARD_POOL
        + PROGRAM_REWARD_POOL
        + VIBE_CODER_REWARD_POOL
        + VIBE_CODER_PROGRAM_POOL
        + starter_deck()
        + starter_deck(program_mode=True)
        + vibe_coder_starter_deck()
    )
    for name, changes in CARD_UPGRADES.items():
        card = next(c for c in pool if c.name == name)
        assert any(
            getattr(card, field) != value
            for field, value in changes.items()
            if field != "description"
        ), name
