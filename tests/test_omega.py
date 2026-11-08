"""The final fight answers the run: OMEGA's moves from phase 2, its law from
phase 3, its lines, and the toll on the AGI's own card (omega.py)."""

import random
from collections import Counter

from agentic_rogue_like.cards import REWARD_POOL, starter_deck
from agentic_rogue_like.combat import (
    LAW_ARMOR,
    ONE_SHOT_TAX,
    TRAP_COST,
    EnemyIntentType,
    Law,
    _damage_enemy,
    _laws_after_turn,
    _roll_boss_intent,
    _tick_statuses,
    end_turn,
    incoming_damage,
    play_card,
    program_preview,
    start_combat,
)
from agentic_rogue_like.enemies import ENEMY_POOL
from agentic_rogue_like.engine import NUM_ACTS, NUM_FLOORS, new_run, start_combat_node
from agentic_rogue_like.forge import fallback_card
from agentic_rogue_like.models import Card, PlayerState, RunStats, Status
from agentic_rogue_like.omega import adapt_omega, omega_taunts
from agentic_rogue_like.style import PlayStyle


def _card(name: str) -> Card:
    return next(c for c in REWARD_POOL + starter_deck() if c.name == name).model_copy(deep=True)


def _omega(style: PlayStyle | None, phase: int = 3, program_mode: bool = False):
    omega = ENEMY_POOL["final"][0]
    player = PlayerState(hp=100, max_hp=100, attack=0, deck=starter_deck())
    state, _ = start_combat(
        player.deck, omega, random.Random(1), boss=True, boss_phases=3, program_mode=program_mode
    )
    adapt_omega(state, player.deck, style)
    state.phase = phase
    state.hand = []
    return state, player


def test_the_law_follows_the_style_and_waits_for_phase_3() -> None:
    state, _ = _omega(PlayStyle.AGGRO, phase=2)
    assert state.omega_law is Law.ARMOR
    _, dealt = _damage_enemy(state, 10)
    assert dealt == 10  # phase 2: not yet
    state.phase = 3
    _, dealt = _damage_enemy(state, 10)
    assert dealt == 10 - LAW_ARMOR


def test_phase_2_plays_more_of_the_counter_moves() -> None:
    state, _ = _omega(PlayStyle.GRAVEYARD, phase=2)
    rolls = Counter(_roll_boss_intent(state, random.Random(i)) for i in range(300))
    assert rolls[EnemyIntentType.CORRUPT] > 60
    plain, _ = _omega(None, phase=2)
    rolls = Counter(_roll_boss_intent(plain, random.Random(i)) for i in range(300))
    assert rolls[EnemyIntentType.CORRUPT] == 0


def test_pierce_counts_half_the_block() -> None:
    state, _ = _omega(PlayStyle.TURTLE)
    state.enemy_intent = EnemyIntentType.ATTACK
    state.player_block = 20
    pierced = incoming_damage(state)
    state.omega_law = None
    assert incoming_damage(state) == (0, 0) and pierced[1] > 0


def test_end_of_turn_laws_delete_a_permanent_and_collect_the_graveyard() -> None:
    state, _ = _omega(PlayStyle.PERMANENTS)
    state.field[1], state.field[3] = _card("Overclock"), _card("Encryption")
    _laws_after_turn(state, random.Random(1))
    assert state.field[3] is None and state.field[1] is not None
    assert state.banished_pile[-1].name == "Encryption"

    state, _ = _omega(PlayStyle.GRAVEYARD)
    state.discard_pile = [_card("Exploit"), _card("Firewall")]
    drawn = len(state.draw_pile)
    _laws_after_turn(state, random.Random(1))
    assert state.discard_pile == [] and len(state.draw_pile) == drawn + 2


def test_one_shots_are_taxed_and_the_agis_card_costs_hp() -> None:
    state, player = _omega(PlayStyle.ONE_SHOT)
    state.hand = [_card("Zero-Day")]
    play_card(state, 0, 0, player, random.Random(1))
    assert player.hp == 100 - ONE_SHOT_TAX

    forged = fallback_card(PlayStyle.AGGRO, program_mode=False)
    forged = forged.model_copy(update={"id": f"{forged.id}-0"})
    state, player = _omega(None)
    adapt_omega(state, [*starter_deck(), forged])
    assert state.trap_cost == TRAP_COST
    state.hand = [forged]
    line = play_card(state, 0, 0, player, random.Random(1))
    assert player.hp == 100 - TRAP_COST and "I know its flaw" in line


def test_malware_bites_omega_for_half_under_its_law() -> None:
    state, player = _omega(PlayStyle.MALWARE)
    state.enemy_status[Status.MALWARE] = 6
    hp = state.enemy_hp
    _tick_statuses(state, player)
    assert hp - state.enemy_hp == 3


def test_every_program_run_loses_its_last_line() -> None:
    state, player = _omega(PlayStyle.PROGRAM, program_mode=True)
    state.enemy_intent = EnemyIntentType.DEFEND
    for slot in (0, 1):
        state.hand.append(_card("Exploit"))
        play_card(state, len(state.hand) - 1, slot, player, random.Random(slot))
    assert [s.outcome for s in program_preview(state, player).steps] == ["ran", "collected"]
    end_turn(state, player, random.Random(2))


def test_omega_speaks_about_the_run() -> None:
    omega = ENEMY_POOL["final"][0]
    deck = [*starter_deck(), *[_card("Stack Overflow")] * 3]
    stats = RunStats(mvp_card=_card("Exploit"), play_counts={"Exploit": 42})
    forged = fallback_card(PlayStyle.GRAVEYARD, program_mode=False)
    spoken = omega_taunts(omega, [*deck, forged.model_copy(update={"id": "agi-x-0"})], stats)
    assert "You played Exploit 42 times" in spoken.taunt
    assert "you took my card" in spoken.taunt
    assert "your Graveyard has been analysed" in spoken.phase_taunts[0]
    # without a style or stats: its own lines
    assert omega_taunts(omega, starter_deck(), RunStats()).taunt == omega.taunt


def test_the_final_fight_is_set_up_from_the_run() -> None:
    run = new_run(5)
    run.act = NUM_ACTS
    run.current_node_id = f"{NUM_FLOORS - 1}-0"
    run.player.deck += [_card("Stack Overflow")] * 3
    state = start_combat_node(run, random.Random(5))
    assert state.omega_style is PlayStyle.GRAVEYARD
    assert state.omega_law is Law.COLLECT_GRAVEYARD
