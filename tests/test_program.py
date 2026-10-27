import random

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like.api import app
from agentic_rogue_like.artifacts import PROGRAM_ARTIFACT_POOL
from agentic_rogue_like.balance_sim import _program_score, arrange_program, smart_bot
from agentic_rogue_like.cards import (
    CARD_UPGRADES,
    PROGRAM_REWARD_POOL,
    REWARD_POOL,
    VIBE_CODER_PROGRAM_POOL,
    VIBE_CODER_REWARD_POOL,
    starter_deck,
    upgrade_card,
)
from agentic_rogue_like.characters import artifact_pool, reward_pool
from agentic_rogue_like.combat import (
    EnemyIntentType,
    _roll_boss_intent,
    action_preview,
    end_turn,
    free_slots,
    move_queued,
    play_card,
    program_preview,
    start_combat,
)
from agentic_rogue_like.enemies import ENEMY_POOL, with_interrupt
from agentic_rogue_like.engine import _room_enemy, available_choices, move_to, new_run, resolve_node
from agentic_rogue_like.models import (
    Artifact,
    Card,
    Character,
    Enemy,
    EnemyMove,
    MoveKind,
    NodeType,
    PlayerState,
    RunStatus,
)
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.style import PlayStyle, agent_hint, answers, play_style
from agentic_rogue_like.threat import threat


def _card(name: str) -> Card:
    pool = (
        PROGRAM_REWARD_POOL
        + VIBE_CODER_PROGRAM_POOL
        + REWARD_POOL
        + VIBE_CODER_REWARD_POOL
        + starter_deck()
    )
    return next(c for c in pool if c.name == name).model_copy(deep=True)


def _artifact(name: str) -> Artifact:
    return next(a for a in PROGRAM_ARTIFACT_POOL if a.name == name)


def _fight(hp: int = 100, program_mode: bool = True, artifact: str | None = None):
    enemy = Enemy(id="e", name="Foe", hp=hp, attack=8, attack_name="Hit")
    player = PlayerState(hp=100, max_hp=100, attack=0, deck=starter_deck())
    artifacts = [_artifact(artifact)] if artifact else []
    state, _ = start_combat(
        player.deck, enemy, random.Random(1), artifacts, program_mode=program_mode
    )
    state.enemy_intent = EnemyIntentType.DEFEND  # nothing hits back
    state.hand = []
    return state, player


def _queue(state, player, *names: str, slots: list[int] | None = None) -> None:
    for i, name in enumerate(names):
        state.hand.append(_card(name))
        play_card(
            state, len(state.hand) - 1, i if slots is None else slots[i], player, random.Random(i)
        )


def _damage_dealt(
    *names: str,
    hp: int = 100,
    artifact: str | None = None,
    slots: list[int] | None = None,
    turn: int = 1,
) -> int:
    state, player = _fight(hp, artifact=artifact)
    state.turn = turn
    _queue(state, player, *names, slots=slots)
    end_turn(state, player, random.Random(9))
    return state.enemy.hp - state.enemy_hp


def test_actions_wait_for_the_end_of_the_turn() -> None:
    state, player = _fight()
    state.hand.append(_card("Exploit"))
    line = play_card(state, 0, 2, player, random.Random(1))

    assert "queue" in line
    assert state.enemy_hp == 100
    assert state.program[2] is not None
    assert 2 not in free_slots(state, _card("Exploit"))
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 95
    assert state.program == [None] * 5


def test_a_permanent_and_a_queued_action_share_a_slot() -> None:
    state, player = _fight()
    _queue(state, player, "Overclock", "Exploit", slots=[0, 0])
    assert len(state.field) == 1 and state.program[0] is not None


def test_permanents_run_in_the_background_without_a_limit() -> None:
    state, player = _fight()
    _queue(state, player, *["Encryption"] * 7, slots=[0] * 7)
    assert len(state.field) == 7
    assert state.program == [None] * 5


def test_overclock_boosts_every_line_of_a_program() -> None:
    # played after the Exploit and into a line to its right - still counts
    state, player = _fight()
    _queue(state, player, "Exploit", "Overclock", slots=[0, 4])
    end_turn(state, player, random.Random(2))
    assert state.enemy.hp - state.enemy_hp == 6


def test_a_locked_line_takes_no_action_but_a_permanent() -> None:
    state, player = _fight()
    state.locked_slots = [0]
    assert 0 not in free_slots(state, _card("Exploit"))
    assert 0 in free_slots(state, _card("Overclock"))
    _queue(state, player, "Overclock", slots=[0])
    assert len(state.field) == 1


def test_card_flow_still_resolves_on_the_spot() -> None:
    state, player = _fight()
    state.hand.append(_card("Phishing"))
    play_card(state, 0, 0, player, random.Random(1))
    assert state.program == [None] * 5
    assert len(state.hand) == 2


def test_fork_doubles_only_the_action_to_its_right() -> None:
    assert _damage_dealt("Fork", "Exploit") == 10
    assert _damage_dealt("Exploit", "Fork") == 5


def test_loop_repeats_the_last_action_to_its_left() -> None:
    assert _damage_dealt("Exploit", "Loop") == 10
    assert _damage_dealt("Loop", "Exploit") == 5


def test_upgraded_loop_repeats_twice() -> None:
    state, player = _fight()
    state.hand = [_card("Exploit"), upgrade_card(_card("Loop"))]
    play_card(state, 0, 0, player, random.Random(1))
    play_card(state, 0, 1, player, random.Random(2))
    end_turn(state, player, random.Random(3))
    assert state.enemy_hp == 85


def test_if_wounded_depends_on_what_ran_before_it() -> None:
    # 20 HP: one Exploit leaves it above half, the gate stays shut...
    assert _damage_dealt("Exploit", "If Wounded", "Exploit", hp=20) == 10
    # ... two take it to half, and the third runs twice.
    assert _damage_dealt("Exploit", "Exploit", "If Wounded", "Exploit", hp=20) == 20


def test_a_program_stops_once_the_enemy_is_down() -> None:
    state, player = _fight(hp=5)
    _queue(state, player, "Exploit", "Zero-Day")
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 0
    # Zero-Day never ran, so it isn't used up.
    assert any(c.name == "Zero-Day" for c in state.discard_pile)
    assert not any(c.name == "Zero-Day" for c in state.banished_pile)


def test_moving_a_queued_action_swaps_lines() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Fork")
    move_queued(state, 1, 0)
    assert [c and c.name for c in state.program[:2]] == ["Fork", "Exploit"]
    move_queued(state, 0, 4)
    assert state.program[0] is None and state.program[4].name == "Fork"

    state.locked_slots = [3]
    with pytest.raises(ValueError, match="locked"):
        move_queued(state, 4, 3)
    with pytest.raises(ValueError, match="no queued card"):
        move_queued(state, 2, 3)


def test_classic_play_has_no_program() -> None:
    state, player = _fight(program_mode=False)
    state.hand = [_card("Fork"), _card("Exploit")]
    assert "does nothing" in play_card(state, 0, 0, player, random.Random(1))
    play_card(state, 0, 0, player, random.Random(2))
    assert state.enemy_hp == 95  # an action resolves right away
    with pytest.raises(ValueError):
        move_queued(state, 0, 1)


def test_control_flow_is_only_offered_in_program_runs() -> None:
    names = {c.name for c in PROGRAM_REWARD_POOL}
    assert not names & {c.name for c in reward_pool(new_run(1))}
    program_run = new_run(1, program_mode=True)
    assert program_run.program_mode
    assert all(c in reward_pool(program_run) for c in PROGRAM_REWARD_POOL)
    assert all(c.name in CARD_UPGRADES for c in PROGRAM_REWARD_POOL)


def test_the_bot_finds_the_better_order() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Fork")  # Fork after its target: wasted
    played = _program_score(state, player, random.Random(1))
    arrange_program(state, player, random.Random(1), "best")
    assert _program_score(state, player, random.Random(1)) > played
    names = [c.name for c in state.program if c is not None]
    assert names == ["Fork", "Exploit"]


def test_api_runs_a_program() -> None:
    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 3, "program_mode": True}).json()["run_id"]
    run = get_session(run_id).run
    run.artifact_offer = run.kit_offer = None
    client.post(f"/runs/{run_id}/resolve")
    get_session(run_id).combat.hand = [_card("Exploit")]

    view = client.get(f"/runs/{run_id}").json()["pending_combat"]
    assert view["program_mode"] and view["program"] == [None] * 5
    client.post(f"/runs/{run_id}/combat/play-card", json={"hand_index": 0, "slot_index": 1})
    response = client.post(
        f"/runs/{run_id}/combat/move-queued", json={"from_slot": 1, "to_slot": 3}
    )
    assert response.json()["pending_combat"]["program"][3]["name"] == "Exploit"
    preview = response.json()["pending_combat"]["program_preview"]
    assert preview["enemy_hp"] < get_session(run_id).combat.enemy_hp
    bad = client.post(f"/runs/{run_id}/combat/move-queued", json={"from_slot": 0, "to_slot": 2})
    assert bad.status_code == 400


def test_a_program_run_plays_out_on_its_own() -> None:
    run = new_run(5, program_mode=True)
    rng = random.Random(5)
    for _ in range(200):
        if run.status is not RunStatus.ONGOING:
            break
        resolve_node(run, rng)
        if run.status is RunStatus.ONGOING:
            move_to(run, available_choices(run)[0])
    assert any("queue" in line for line in run.history)
    assert any(line.startswith("[") for line in run.history)  # program lines ran


# ---- program artifacts


def test_hot_path_runs_its_line_upgraded() -> None:
    assert _damage_dealt("Exploit", artifact="Hot Path", slots=[0]) == 5
    assert _damage_dealt("Exploit", artifact="Hot Path", slots=[1]) == 8

    state, player = _fight(artifact="Hot Path")
    assert state.enemy_hp == 110  # its price
    _queue(state, player, "Exploit", slots=[1])
    end_turn(state, player, random.Random(2))
    assert [c.name for c in state.discard_pile] == ["Exploit"]  # the deck's card stays plain


def test_branch_predictor_boosts_what_runs_after_half_hp() -> None:
    names = ("Exploit", "Exploit", "Exploit")
    assert _damage_dealt(*names, hp=20) == 15
    assert _damage_dealt(*names, hp=20, artifact="Branch Predictor") == 18


def test_tail_call_runs_the_last_line_again_every_second_turn() -> None:
    assert _damage_dealt("Exploit", artifact="Tail Call", slots=[4], turn=1) == 5
    assert _damage_dealt("Exploit", artifact="Tail Call", slots=[4], turn=2) == 10
    assert _damage_dealt("Exploit", artifact="Tail Call", slots=[3], turn=2) == 5


def test_pipeline_boosts_the_action_after_control_flow() -> None:
    assert _damage_dealt("Fork", "Exploit", artifact="Pipeline") == 16
    assert _damage_dealt("Exploit", "Fork", artifact="Pipeline") == 5


def test_compiler_counts_the_other_types_before_the_last_line() -> None:
    assert _damage_dealt("Firewall", "Exploit", artifact="Compiler", slots=[0, 4]) == 6
    assert _damage_dealt("Firewall", "Exploit", artifact="Compiler", slots=[0, 3]) == 5


def test_extra_line_takes_an_action() -> None:
    state, player = _fight(artifact="Extra Line")
    assert len(state.program) == 6
    assert 5 in free_slots(state, _card("Exploit"))
    _queue(state, player, "Exploit", slots=[5])
    with pytest.raises(ValueError, match="occupied"):
        _queue(state, player, "Firewall", slots=[5])
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 95


def test_program_artifacts_are_only_offered_in_program_runs() -> None:
    names = {a.name for a in PROGRAM_ARTIFACT_POOL}
    assert not names & {a.name for a in artifact_pool(new_run(1))}
    assert names <= {a.name for a in artifact_pool(new_run(1, program_mode=True))}


def test_the_preview_shows_what_the_program_will_do() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Firewall")
    preview = program_preview(state, player)
    assert (preview.enemy_hp, preview.player_block) == (95, 5)
    assert state.enemy_hp == 100 and state.program[0] is not None  # nothing ran yet

    classic, player = _fight(program_mode=False)
    assert program_preview(classic, player).enemy_hp == 100


def test_ship_it_counts_every_card_played_this_turn() -> None:
    # Queued first, it still runs after two other cards were played.
    assert _damage_dealt("Ship It", "Exploit", "Exploit") == 20


def test_the_bot_stops_once_the_program_is_lethal() -> None:
    state, player = _fight(hp=5)
    state.hand = [_card("Exploit"), _card("Exploit")]
    smart_bot(state, player, random.Random(1))
    assert sum(c is not None for c in state.program) == 1
    assert len(state.hand) == 1


def test_the_vibe_coder_gets_a_sixth_line() -> None:
    enemy = Enemy(id="e", name="Foe", hp=10, attack=1, attack_name="Hit")
    lines = {
        (character, mode): len(
            start_combat(
                starter_deck(), enemy, random.Random(1), character=character, program_mode=mode
            )[0].program
        )
        for character in Character
        for mode in (False, True)
    }
    assert lines[Character.VIBE_CODER, True] == 6
    assert lines[Character.CHRONOS, True] == 5
    assert lines[Character.VIBE_CODER, False] == 5


def test_previews_count_hot_path_and_the_queued_block() -> None:
    state, player = _fight(artifact="Hot Path")
    exploit = _card("Exploit")
    assert action_preview(state, exploit, player, 0) == 5
    assert action_preview(state, exploit, player, 1) == 8

    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 3, "program_mode": True}).json()["run_id"]
    run = get_session(run_id).run
    run.artifact_offer = run.kit_offer = None
    client.post(f"/runs/{run_id}/resolve")
    combat = get_session(run_id).combat
    combat.enemy_intent = EnemyIntentType.ATTACK
    combat.hand = [_card("Firewall")]
    before = client.get(f"/runs/{run_id}").json()["pending_combat"]["incoming_max"]
    after = client.post(
        f"/runs/{run_id}/combat/play-card", json={"hand_index": 0, "slot_index": 0}
    ).json()["pending_combat"]["incoming_max"]
    assert after == max(0, before - 5)


# ---- interrupt


def _interrupting(hp: int = 100):
    state, player = _fight(hp)
    state.enemy = state.enemy.model_copy(
        update={"moves": [*state.enemy.moves, EnemyMove(kind=MoveKind.INTERRUPT, stacks=2)]}
    )
    state.enemy_move = len(state.enemy.moves) - 1
    state.enemy_intent = EnemyIntentType.INTERRUPT
    return state, player


def test_an_interrupt_cuts_the_program_after_its_lines() -> None:
    state, player = _interrupting()
    _queue(state, player, "Exploit", "Fork", "Zero-Day", "Exploit")
    # Exploit and Fork run, then the cut - the Fork has nothing left to fork
    assert program_preview(state, player).enemy_hp == 95
    log = end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 95
    assert any("interrupts your program after 2 line(s)" in line for line in log)
    # what was cut never ran: back to the graveyard, the one-shot not used up
    assert {"Zero-Day", "Exploit"} <= {c.name for c in state.discard_pile}
    assert not state.banished_pile


def test_order_decides_what_survives_an_interrupt() -> None:
    state, player = _interrupting()
    _queue(state, player, "Fork", "Zero-Day", "Exploit", "Exploit")
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 100 - 2 * 16


def test_with_interrupt_keeps_the_threat() -> None:
    enemy = ENEMY_POOL["mid"][0]
    armed = with_interrupt(enemy)
    assert any(m.kind is MoveKind.INTERRUPT for m in armed.moves)
    assert abs(threat(armed) - threat(enemy)) / threat(enemy) < 0.05
    assert with_interrupt(armed) == armed


def test_only_program_runs_meet_interrupts() -> None:
    for program_mode in (False, True):
        run = new_run(2, program_mode=program_mode)
        node = run.nodes[available_choices(run)[0]]
        node = node.model_copy(update={"type": NodeType.COMBAT})
        enemy = _room_enemy(run, node, random.Random(1))
        has = any(m.kind is MoveKind.INTERRUPT for m in enemy.moves)
        assert has is program_mode


# ---- refactor (bosses)


def test_a_refactor_runs_the_program_right_to_left() -> None:
    state, player = _fight()
    state.boss = True
    state.enemy_intent = EnemyIntentType.REFACTOR
    _queue(state, player, "Exploit", "Fork")  # left to right the Fork comes too late
    assert program_preview(state, player).enemy_hp == 90
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 90


def test_only_bosses_against_a_program_refactor() -> None:
    def intents(program_mode: bool) -> set[EnemyIntentType]:
        state, _ = _fight(program_mode=program_mode)
        state.boss = True
        rng = random.Random(5)
        seen = set()
        for _ in range(300):
            state.enemy_intent = _roll_boss_intent(state, rng)
            seen.add(state.enemy_intent)
        return seen

    assert EnemyIntentType.REFACTOR in intents(True)
    assert EnemyIntentType.REFACTOR not in intents(False)


# ---- the Vibe-Coder's control flow


def test_pipe_pays_for_the_actions_before_it() -> None:
    assert _damage_dealt("Exploit", "Exploit", "Pipe", "Exploit") == 5 + 5 + (5 + 4)
    assert _damage_dealt("Pipe", "Exploit", "Exploit", "Exploit") == 15


def test_batch_frees_tokens_for_the_actions_after_it() -> None:
    state, player = _fight()
    state.token_limit, state.tokens_used = 10, 0
    _queue(state, player, "Batch", "Exploit", "Exploit")
    used = state.tokens_used
    end_turn(state, player, random.Random(2))
    # 2 freed by Batch, before the turn's own regen (none in this fight)
    assert state.tokens_used == used - 2


def test_only_the_vibe_coder_gets_pipe_and_batch() -> None:
    names = {c.name for c in VIBE_CODER_PROGRAM_POOL}
    vibe = new_run(1, character=Character.VIBE_CODER, program_mode=True)
    assert names <= {c.name for c in reward_pool(vibe)}
    assert not names & {c.name for c in reward_pool(new_run(1, program_mode=True))}
    vibe_classic = new_run(1, character=Character.VIBE_CODER)
    assert not names & {c.name for c in reward_pool(vibe_classic)}
    assert all(c.name in CARD_UPGRADES for c in VIBE_CODER_PROGRAM_POOL)


# ---- the AGI reads a program


def test_control_flow_is_a_style_the_agi_answers_with_interrupts() -> None:
    deck = starter_deck() + [_card(n) for n in ("Fork", "Loop", "If Wounded", "Pipe")]
    for i, card in enumerate(deck):
        card.id = f"c{i}"
    assert play_style(deck) is PlayStyle.PROGRAM
    assert agent_hint(PlayStyle.PROGRAM) is None  # the game answers it itself

    enemy = ENEMY_POOL["mid"][0]

    def share(armed) -> float:
        interrupt = next(m for m in armed.moves if m.kind is MoveKind.INTERRUPT)
        return interrupt.weight / sum(m.weight for m in armed.moves)

    plain, answered = with_interrupt(enemy), with_interrupt(enemy, PlayStyle.PROGRAM)
    assert share(answered) > share(plain)
    assert abs(threat(answered) - threat(enemy)) / threat(enemy) < 0.05
    assert answers(answered, PlayStyle.PROGRAM)


def test_the_preview_plays_out_line_by_line() -> None:
    state, player = _interrupting()
    _queue(state, player, "Fork", "Exploit", "Firewall")
    steps = program_preview(state, player).steps
    assert [(s.name, s.outcome) for s in steps] == [
        ("Fork", "ran"),
        ("Exploit", "ran"),
        ("Firewall", "cut"),
    ]
    fork, exploit, firewall = steps
    assert (fork.runs, fork.dealt) == (0, 0)
    assert (exploit.runs, exploit.damage, exploit.enemy_hp) == (2, 10, 90)
    assert (firewall.runs, firewall.block) == (0, 0)
    assert state.program[0] is not None  # still only a preview
