import random

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agentic_rogue_like.api import app
from agentic_rogue_like.balance_sim import mean_damage_taken, smart_bot
from agentic_rogue_like.cards import starter_deck
from agentic_rogue_like.combat import (
    EnemyIntentType,
    action_preview,
    end_turn,
    free_slots,
    play_card,
    start_combat,
)
from agentic_rogue_like.enemies import ENEMY_POOL
from agentic_rogue_like.models import CardType, Enemy, EnemyMove, MoveKind, PlayerState
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.threat import threat

LOCK = EnemyMove(kind=MoveKind.LOCK, name="Jam")
CORRUPT = EnemyMove(kind=MoveKind.CORRUPT, name="Smudge", stacks=3)


def _fight(move: EnemyMove):
    enemy = Enemy(
        id="e",
        name="Foe",
        hp=200,
        attack=8,
        attack_name="Hit",
        moves=[EnemyMove(kind=MoveKind.ATTACK), move],
    )
    player = PlayerState(hp=200, max_hp=200, attack=2, deck=starter_deck())
    state, _ = start_combat(player.deck, enemy, random.Random(1))
    state.enemy_move = 1
    state.enemy_intent = EnemyIntentType(move.kind.value)
    return state, player


def test_lock_shuts_one_empty_slot_for_the_next_turn() -> None:
    state, player = _fight(LOCK)
    state.field[0] = state.hand[0]  # an occupied slot can't be locked

    log = end_turn(state, player, random.Random(2))

    assert len(state.locked_slots) == 1
    locked = state.locked_slots[0]
    assert locked != 0  # only empty slots get locked
    assert any("is locked" in line for line in log)
    assert locked not in free_slots(state)
    assert action_preview(state, state.hand[0], player, locked) is None
    with pytest.raises(ValueError, match="locked"):
        play_card(state, 0, locked, player, random.Random(3))

    state.enemy_intent = EnemyIntentType.DEFEND
    end_turn(state, player, random.Random(4))
    assert state.locked_slots == []


def test_lock_on_a_full_field_locks_nothing() -> None:
    state, player = _fight(LOCK)
    state.field = [state.hand[0]] * 5
    end_turn(state, player, random.Random(2))
    assert state.locked_slots == []


def test_corrupt_shuffles_glitches_that_vanish_when_played() -> None:
    state, player = _fight(CORRUPT)
    deck_before = list(player.deck)

    end_turn(state, player, random.Random(2))
    pile = state.draw_pile + state.hand
    glitches = [c for c in pile if c.type is CardType.GLITCH]
    assert len(glitches) == 3
    assert len({c.id for c in glitches}) == 3

    state.hand.insert(0, glitches[0])
    line = play_card(state, 0, free_slots(state)[0], player, random.Random(3))
    assert "flush" in line
    assert glitches[0] in state.banished_pile
    assert player.deck == deck_before  # the run's deck never sees a glitch


def test_lock_and_corrupt_are_only_moves_with_their_own_fields() -> None:
    assert EnemyMove(kind=MoveKind.CORRUPT).stacks == 2
    with pytest.raises(ValidationError):
        EnemyMove(kind=MoveKind.LOCK, stacks=2)


@pytest.mark.parametrize("enemy_id", ["gremlin", "corrupted-scribe"])
def test_field_move_enemies_hit_about_as_hard_as_their_threat_says(enemy_id: str) -> None:
    enemy = next(e for tier in ENEMY_POOL.values() for e in tier if e.id == enemy_id)
    plain = Enemy(id="p", name="Plain", hp=60, attack=enemy.attack, attack_name="Hit")
    plain = plain.model_copy(update={"hp": round(plain.hp * threat(enemy) / threat(plain))})
    assert mean_damage_taken(enemy, smart_bot, 300, enemy_id) == pytest.approx(
        mean_damage_taken(plain, smart_bot, 300, "plain"), rel=0.25
    )


def test_api_shows_and_enforces_locked_slots() -> None:
    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 3}).json()["run_id"]
    run = get_session(run_id).run
    run.artifact_offer = run.kit_offer = None
    client.post(f"/runs/{run_id}/resolve")
    get_session(run_id).combat.locked_slots = [2]

    view = client.get(f"/runs/{run_id}").json()["pending_combat"]
    response = client.post(
        f"/runs/{run_id}/combat/play-card",
        json={"hand_index": view["hand"][0]["hand_index"], "slot_index": 2},
    )

    assert view["locked_slots"] == [2]
    assert response.status_code == 400
