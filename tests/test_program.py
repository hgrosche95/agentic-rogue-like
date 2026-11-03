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
    take_back,
)
from agentic_rogue_like.enemies import (
    ENEMY_POOL,
    PROGRAM_MOVES,
    program_counter,
    with_interrupt,
    with_program_move,
)
from agentic_rogue_like.engine import _room_enemy, available_choices, move_to, new_run, resolve_node
from agentic_rogue_like.models import (
    Artifact,
    Card,
    CardType,
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


def test_undo_runs_as_a_line_and_fetches_what_ran_before_it() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Undo")
    # queued, not played on the spot
    assert [c and c.name for c in state.program[:2]] == ["Exploit", "Undo"]
    preview = program_preview(state, player)
    assert preview.steps[1].retrieved == ["Exploit"]

    end_turn(state, player, random.Random(2))
    assert state.enemy.hp - state.enemy_hp == 5
    assert "Exploit" in [c.name for c in state.hand]
    # one-shot: used up once it ran
    assert any(c.name == "Undo" for c in state.banished_pile)


def test_first_and_last_line_cards_pay_off_in_their_place() -> None:
    # Bootstrap: +7 as the first line to run, Return: +7 as the last
    assert _damage_dealt("Bootstrap", "Exploit") == 10 + 5
    assert _damage_dealt("Exploit", "Bootstrap") == 5 + 3
    assert _damage_dealt("Exploit", "Return") == 5 + 10
    assert _damage_dealt("Return", "Exploit") == 3 + 5
    # alone in the program it is both first and last
    assert _damage_dealt("Return", slots=[2]) == 10


def test_line_count_cards_scale_with_the_programs_length() -> None:
    assert _damage_dealt("Monolith") == 1
    assert _damage_dealt("Monolith", "Firewall", "Firewall") == 1 + 6
    assert _damage_dealt("Microservice") == 11
    assert _damage_dealt("Microservice", "Firewall", "Firewall") == 11 - 4


def test_segfault_ends_the_program() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Segfault", "Exploit")
    steps = program_preview(state, player).steps
    assert [s.outcome for s in steps] == ["ran", "ran", "cut"]
    end_turn(state, player, random.Random(2))
    assert state.enemy.hp - state.enemy_hp == 5 + 16
    # the line it cut never ran, so it isn't used up
    assert sum(c.name == "Exploit" for c in state.discard_pile) == 2


def test_the_hand_preview_knows_where_the_line_will_stand() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", slots=[2])
    bootstrap = _card("Bootstrap")
    assert action_preview(state, bootstrap, player, 0) == 10  # first
    assert action_preview(state, bootstrap, player, 4) == 3  # after the Exploit
    assert state.line_position is None


def test_take_back_returns_a_queued_line_or_a_permanent() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Overclock", slots=[2, 0])
    plays = state.plays_this_turn

    take_back(state, "program", 2)
    assert state.program == [None] * 5
    take_back(state, "field", 0)
    assert state.field == []
    assert sorted(c.name for c in state.hand) == ["Exploit", "Overclock"]
    # taken back, they no longer count as played (Copilot)
    assert state.plays_this_turn == plays - 2

    with pytest.raises(ValueError, match="no queued card"):
        take_back(state, "program", 2)
    with pytest.raises(ValueError, match="no card on the field"):
        take_back(state, "field", 0)


def test_take_back_frees_a_classic_slot() -> None:
    state, player = _fight(program_mode=False)
    _queue(state, player, "Overclock", slots=[3])
    take_back(state, "field", 3)
    assert state.field == [None] * 5
    with pytest.raises(ValueError, match="only a program"):
        take_back(state, "program", 0)


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

    back = client.post(f"/runs/{run_id}/combat/take-back", json={"zone": "program", "index": 3})
    assert back.json()["pending_combat"]["program"] == [None] * 5
    assert [c["name"] for c in back.json()["pending_combat"]["hand"]] == ["Exploit"]
    again = client.post(f"/runs/{run_id}/combat/take-back", json={"zone": "program", "index": 3})
    assert again.status_code == 400


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
    # (a Firewall between them, or three attacks in a row would be a Burst)
    names = ("Exploit", "Firewall", "Exploit", "Exploit")
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
    assert _damage_dealt("Ship It", "Exploit", "Exploit") == 20 + 5  # and a Burst


def test_the_bot_stops_once_the_program_is_lethal() -> None:
    state, player = _fight(hp=5)
    state.hand = [_card("Exploit"), _card("Exploit")]
    smart_bot(state, player, random.Random(1))
    assert sum(c is not None for c in state.program) == 1
    assert len(state.hand) == 1


def test_the_bot_purges_junk_only() -> None:
    glitch = Card(
        id="g", name="Glitch", type=CardType.GLITCH, value=0, exhaust=True, description=""
    )
    state, player = _fight(program_mode=False)
    state.hand = [_card("Purge"), _card("Zero-Day"), glitch]
    smart_bot(state, player, random.Random(1))
    assert [c.name for c in state.banished_pile[:2]] == ["Glitch", "Purge"]

    # Nothing worth banishing: the Purge waits until it is alone in hand,
    # and then only draws - the Zero-Day gets played, not purged.
    state, player = _fight(program_mode=False)
    state.hand = [_card("Purge"), _card("Zero-Day")]
    smart_bot(state, player, random.Random(1))
    assert [c.name for c in state.banished_pile[:2]] == ["Zero-Day", "Purge"]


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


def test_only_program_runs_meet_program_moves() -> None:
    for program_mode in (False, True):
        run = new_run(2, program_mode=program_mode)
        node = run.nodes[available_choices(run)[0]]
        node = node.model_copy(update={"type": NodeType.COMBAT})
        enemy = _room_enemy(run, node, random.Random(1))
        has = any(m.kind in PROGRAM_MOVES for m in enemy.moves)
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
    assert _damage_dealt("Pipe", "Exploit", "Exploit", "Exploit") == 15 + 5  # and a Burst


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


def test_purge_resolves_on_the_spot_in_a_program() -> None:
    # Card flow, like Phishing: it banishes and draws right away, so the
    # drawn cards can still be queued this turn - and it takes no line.
    state, player = _fight()
    _queue(state, player, "Exploit")
    state.hand = [_card("Purge"), _card("Firewall")]
    play_card(state, 0, 0, player, random.Random(1), banish=[1])

    assert [c.name for c in state.banished_pile] == ["Firewall", "Purge"]
    assert len(state.hand) == 2
    assert [c.name for c in state.program if c] == ["Exploit"]


def test_api_purges_the_chosen_card() -> None:
    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 3, "program_mode": True}).json()["run_id"]
    run = get_session(run_id).run
    run.artifact_offer = run.kit_offer = None
    client.post(f"/runs/{run_id}/resolve")
    get_session(run_id).combat.hand = [_card("Purge"), _card("Exploit"), _card("Firewall")]

    view = client.get(f"/runs/{run_id}").json()["pending_combat"]
    assert [c["banish"] for c in view["hand"]] == [1, 0, 0]
    url = f"/runs/{run_id}/combat/play-card"
    bad = client.post(url, json={"hand_index": 0, "slot_index": 0, "banish_indices": [0]})
    assert bad.status_code == 400
    response = client.post(url, json={"hand_index": 0, "slot_index": 0, "banish_indices": [2]})
    assert response.json()["pending_combat"]["banished_count"] == 2
    assert [c.name for c in get_session(run_id).combat.banished_pile] == ["Firewall", "Purge"]


# ---- registers, exceptions and named combos


def test_try_catch_keeps_an_interrupt_from_cutting_the_lines_after_it() -> None:
    state, player = _interrupting()
    _queue(state, player, "Try/Catch", "Exploit", "Firewall", "Exploit")
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 90  # both Exploits ran, past the cut after line 2


def test_buffer_holds_damage_back_until_a_flush_lets_it_out() -> None:
    # the Exploit stores its 5; the Flush deals them +50%
    assert _damage_dealt("Buffer", "Exploit", "Flush") == 7
    # stored and never flushed: lost
    assert _damage_dealt("Buffer", "Exploit") == 0
    # a fork doubles what goes into the buffer
    assert _damage_dealt("Buffer", "Fork", "Exploit", "Flush") == 15


def test_named_combos_pay_out_once_per_run() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Exploit", "Exploit")
    steps = program_preview(state, player).steps
    assert [s.combo for s in steps] == [None, None, "Burst"]
    assert state.enemy.hp - program_preview(state, player).enemy_hp == 15 + 5
    # a block, an attack, a block: block on top
    state, player = _fight()
    _queue(state, player, "Firewall", "Exploit", "Firewall")
    assert program_preview(state, player).player_block == 5 + 5 + 6


def test_a_program_that_gets_five_lines_through_is_a_clean_run() -> None:
    state, player = _fight()
    _queue(state, player, "Exploit", "Firewall", "Exploit", "Firewall", "Exploit")
    steps = program_preview(state, player).steps
    assert steps[-1].combo == "Clean Run"
    assert state.enemy.hp - program_preview(state, player).enemy_hp == 15 + 5


# ---- program moves: garbage collector, race condition, memory leak


def test_a_garbage_collector_throws_the_last_line_away() -> None:
    state, player = _fight()
    state.enemy_intent = EnemyIntentType.COLLECT
    _queue(state, player, "Exploit", "Return")
    steps = program_preview(state, player).steps
    assert [s.outcome for s in steps] == ["ran", "collected"]
    end_turn(state, player, random.Random(2))
    assert state.enemy.hp - state.enemy_hp == 5
    # alone, a line is left alone
    state, player = _fight()
    state.enemy_intent = EnemyIntentType.COLLECT
    _queue(state, player, "Exploit")
    assert program_preview(state, player).steps[0].outcome == "ran"


def test_a_race_condition_swaps_the_first_two_lines() -> None:
    state, player = _fight()
    state.enemy_intent = EnemyIntentType.RACE
    _queue(state, player, "Fork", "Exploit")  # swapped, the Fork comes too late
    steps = program_preview(state, player).steps
    assert [s.name for s in steps] == ["Exploit", "Fork"]
    end_turn(state, player, random.Random(2))
    assert state.enemy.hp - state.enemy_hp == 5


def test_a_memory_leak_locks_the_first_line_for_the_next_turn() -> None:
    state, player = _fight()
    state.enemy_intent = EnemyIntentType.LEAK
    _queue(state, player, "Exploit", "Exploit", slots=[1, 3])
    end_turn(state, player, random.Random(2))
    assert state.locked_slots == [1]


def test_the_agi_picks_the_program_move_that_hurts_the_deck() -> None:
    def deck(*names: str) -> list[Card]:
        return [_card(n) for n in names]

    assert program_counter(deck("Monolith", "Return", "Fork")) is MoveKind.COLLECT
    assert program_counter(deck("Bootstrap", "Bootstrap")) is MoveKind.LEAK
    assert program_counter(deck("Fork", "If Wounded")) is MoveKind.RACE
    assert program_counter(deck("Loop", "Buffer")) is MoveKind.INTERRUPT

    enemy = ENEMY_POOL["mid"][0]
    armed = with_program_move(enemy, PlayStyle.PROGRAM, deck("Bootstrap", "Bootstrap"))
    assert any(m.kind is MoveKind.LEAK for m in armed.moves)
    assert answers(armed, PlayStyle.PROGRAM)
    # without a program style: one move, fixed by the enemy, for variety
    plain = with_program_move(enemy)
    assert sum(m.kind in PROGRAM_MOVES for m in plain.moves) == 1
    assert with_program_move(plain) is plain


# ---- Goto 1


def test_goto_runs_the_first_actions_again_from_their_own_lines() -> None:
    # Bootstrap is the first line both times: 10 + 5, then again 10 + 5
    assert _damage_dealt("Bootstrap", "Exploit", "Goto 1") == 30
    # only the first 2 actions come back (and the three Exploits are a Burst: +5)
    assert _damage_dealt("Exploit", "Exploit", "Exploit", "Goto 1") == 15 + 5 + 10
    # with nothing before it, it idles
    assert _damage_dealt("Goto 1", "Exploit") == 5


# ---- Main Thread, Garbage-Free


def test_main_thread_runs_the_first_line_twice() -> None:
    assert _damage_dealt("Exploit", "Firewall", artifact="Main Thread") == 10
    # control flow in the first line: nothing to run twice
    assert _damage_dealt("Loop", "Exploit", artifact="Main Thread") == 5


def test_garbage_free_softens_segfault_and_stops_the_collector() -> None:
    assert _damage_dealt("Segfault", "Exploit", "Exploit", artifact="Garbage-Free") == 16 + 5
    state, player = _fight(artifact="Garbage-Free")
    state.enemy_intent = EnemyIntentType.COLLECT
    _queue(state, player, "Exploit", "Exploit")
    assert [s.outcome for s in program_preview(state, player).steps] == ["ran", "ran"]
