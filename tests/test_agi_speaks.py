"""The AGI speaking in combat: RunState.voice lines on fixed triggers."""

from __future__ import annotations

import random
from unittest.mock import patch

import pytest

from agentic_rogue_like import engine
from agentic_rogue_like.agent.voice import VoiceTrigger, fallback_voice, pick_line
from agentic_rogue_like.cards import starter_deck
from agentic_rogue_like.combat import (
    BIG_HIT_DEALT,
    BIG_HIT_TAKEN,
    CombatVoice,
    EnemyIntentType,
    auto_resolve_combat,
    end_turn,
    free_slots,
    play_card,
    start_combat,
    voice_lines,
)
from agentic_rogue_like.engine import (
    NUM_ACTS,
    available_choices,
    new_run,
    resolve_node,
    start_combat_node,
)
from agentic_rogue_like.models import Enemy, EnemyMove, MoveKind, NodeType, RunStatus

SEED = "test-room"


def _voice(**kwargs) -> CombatVoice:
    return CombatVoice(lines=fallback_voice(), seed=SEED, **kwargs)


def _line(trigger: VoiceTrigger) -> str:
    return pick_line(fallback_voice(), SEED, trigger)


def _agi(log: list[str]) -> list[str]:
    return [line for line in log if line.startswith("AGI:")]


def _hitter(attack: int, hp: int = 200) -> Enemy:
    """Attacks every turn, nothing else."""
    return Enemy(
        id="e",
        name="Hammer",
        hp=hp,
        attack=attack,
        attack_name="Slam",
        moves=[
            EnemyMove(kind=MoveKind.ATTACK, name="Slam", weight=1, power=100),
            EnemyMove(kind=MoveKind.BARRAGE, name="Rain", weight=1, power=100, hits=2),
        ],
    )


def _player(hp: int | None = None, attack: int | None = None):
    player = new_run(1).player
    if hp is not None:
        player.hp = hp
    if attack is not None:
        player.attack = attack
    return player


def _exploits() -> list:
    exploit = next(c for c in starter_deck() if c.name == "Exploit")
    return [exploit.model_copy(update={"id": f"x{i}"}) for i in range(12)]


def _turns(state, player, rng, count: int) -> list[str]:
    log: list[str] = []
    for _ in range(count):
        if state.enemy_hp <= 0 or player.hp <= 0:
            break
        state.enemy_intent = EnemyIntentType.ATTACK
        state.enemy_move = 0
        log += end_turn(state, player, rng, discard=list(range(max(0, len(state.hand) - 8))))
        log += voice_lines(state)
    return log


def _plays(state, player, rng, count: int) -> list[str]:
    log: list[str] = []
    for _ in range(count):
        index = next(i for i, c in enumerate(state.hand) if c.name == "Exploit")
        log.append(play_card(state, index, free_slots(state, state.hand[index])[0], player, rng))
        log += voice_lines(state)
        state.field = [None] * len(state.field)  # room for the next one
    return log


def test_an_elite_fight_opens_with_one_line() -> None:
    _, log = start_combat(
        starter_deck(),
        _hitter(9),
        random.Random(1),
        voice=_voice(opening=[VoiceTrigger.ELITE_START]),
    )

    assert _agi(log) == [_line(VoiceTrigger.ELITE_START)]


def test_an_answering_enemy_taunts_with_the_style_line_once() -> None:
    run = new_run(2)
    run.artifact_offer = run.card_reward = None
    run.current_node_id = next(
        i for i, n in run.nodes.items() if n.type is NodeType.COMBAT and n.floor >= 4
    )
    seed = engine._voice_seed(run, run.nodes[run.current_node_id])
    expected = pick_line(run.voice, seed, VoiceTrigger.STYLE_DETECTED)

    with (
        patch("agentic_rogue_like.engine.answers", return_value=True),
        patch("agentic_rogue_like.engine.play_style", return_value="aggro"),
    ):
        state = start_combat_node(run, random.Random(1))

    assert state.enemy.taunt == expected  # what the frontend's banner shows
    assert _agi(run.history) == [expected]
    assert VoiceTrigger.STYLE_DETECTED in state.voice.fired


def test_a_heavy_enemy_turn_speaks_once() -> None:
    player = _player()
    state, _ = start_combat(
        _exploits(), _hitter(BIG_HIT_TAKEN + 6), random.Random(3), voice=_voice()
    )

    log = _turns(state, player, random.Random(3), 2)

    assert state.tally.damage_taken >= 2 * BIG_HIT_TAKEN  # two heavy turns...
    assert _agi(log).count(_line(VoiceTrigger.BIG_HIT_TAKEN)) == 1  # ...one line


def test_falling_below_thirty_percent_speaks_once() -> None:
    player = _player()
    player.hp = player.max_hp * 40 // 100
    state, _ = start_combat(_exploits(), _hitter(6), random.Random(4), voice=_voice())

    log = _turns(state, player, random.Random(4), 1)
    assert player.hp * 100 < player.max_hp * 30
    assert _agi(log) == [_line(VoiceTrigger.PLAYER_LOW_HP)]

    # Healed back above, then down below again: the same fight, no second line.
    player.hp = player.max_hp * 35 // 100
    log = _turns(state, player, random.Random(5), 1)
    assert 0 < player.hp * 100 < player.max_hp * 30
    assert _line(VoiceTrigger.PLAYER_LOW_HP) not in _agi(log)


def test_a_heavy_card_speaks_once() -> None:
    player = _player(attack=BIG_HIT_DEALT + 5)
    state, _ = start_combat(_exploits(), _hitter(5, hp=500), random.Random(6), voice=_voice())

    log = _plays(state, player, random.Random(6), 2)

    assert state.tally.damage_dealt >= 2 * BIG_HIT_DEALT
    assert _agi(log) == [_line(VoiceTrigger.BIG_HIT_DEALT)]


def test_a_boss_phase_speaks_once_even_over_two_phases() -> None:
    player = _player(attack=60)
    state, _ = start_combat(
        _exploits(), _hitter(5, hp=200), random.Random(7), boss=True, boss_phases=3, voice=_voice()
    )

    log = _plays(state, player, random.Random(7), 4)

    assert state.phase == 3
    assert _agi(log).count(_line(VoiceTrigger.BOSS_PHASE)) == 1


@pytest.mark.parametrize("victory", [True, False])
def test_the_end_of_the_run_speaks_once(victory: bool) -> None:
    run = new_run(9)
    run.act = NUM_ACTS
    node = next(n for n in run.nodes.values() if n.type is NodeType.BOSS)
    trigger = VoiceTrigger.VICTORY if victory else VoiceTrigger.DEFEAT

    engine._finish_combat(run, node, "Boss", victory=victory, rng=random.Random(1))

    assert run.status is (RunStatus.VICTORY if victory else RunStatus.DEFEAT)
    assert _agi(run.history) == [pick_line(run.voice, engine._voice_seed(run, node), trigger)]


def test_without_a_voice_nothing_is_said() -> None:
    player = _player(attack=60)
    state, log = start_combat(_exploits(), _hitter(30), random.Random(8), boss=True)

    log += _plays(state, player, random.Random(8), 2) + _turns(state, player, random.Random(8), 2)

    assert _agi(log) == []


def test_a_fight_plays_the_same_with_and_without_a_voice() -> None:
    def fight(voice):
        player, rng = _player(), random.Random(11)
        won, log = auto_resolve_combat(_exploits(), _hitter(14, hp=90), player, rng, voice=voice)
        return won, [line for line in log if not line.startswith("AGI:")], player.hp, rng.random()

    quiet, spoken = fight(None), fight(_voice(opening=[VoiceTrigger.ELITE_START]))

    assert spoken == quiet


@pytest.mark.parametrize("seed", [3, 11, 27])
def test_a_seeded_run_plays_the_same_with_and_without_a_voice(seed: int) -> None:
    def play(voice: dict) -> tuple:
        run = new_run(seed)
        run.voice = voice
        rng = random.Random(seed)
        for _ in range(100):
            resolve_node(run, rng)
            if run.status is not RunStatus.ONGOING:
                break
            run.current_node_id = available_choices(run)[0]
        story = [line for line in run.history if not line.startswith("AGI:")]
        deck = [card.name for card in run.player.deck]
        return run.status, run.player.hp, run.player.gold, deck, story, rng.random(), run

    *spoken, voiced_run = play(fallback_voice())
    *quiet, quiet_run = play({})

    assert spoken == quiet
    assert _agi(voiced_run.history)  # it did speak...
    assert all(line.startswith('AGI: "') for line in _agi(quiet_run.history))  # ...only taunts
