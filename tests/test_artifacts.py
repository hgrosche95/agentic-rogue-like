import random

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like.api import app
from agentic_rogue_like.artifacts import (
    ARTIFACT_CHOICES,
    ARTIFACT_EVERY_STEPS,
    ARTIFACT_POOL,
    gain_artifact,
    roll_artifact_offer,
)
from agentic_rogue_like.combat import (
    CARDS_PER_TURN,
    HAND_SIZE,
    MAX_HAND_SIZE,
    end_turn,
    max_hand_size,
    play_card,
    start_combat,
)
from agentic_rogue_like.engine import available_choices, choose_artifact, move_to, new_run
from agentic_rogue_like.models import Artifact, Card, CardType, Enemy, PlayerState

STRIKE = Card(id="strike", name="Strike", type=CardType.ATTACK, value=6, description="")
DEFEND = Card(id="defend", name="Defend", type=CardType.BLOCK, value=5, description="")
MEND = Card(id="mend", name="Mend", type=CardType.HEAL, value=4, description="")

client = TestClient(app)


def _artifact(**bonus) -> Artifact:
    return Artifact(id="test", name="Test", description="", **bonus)


def _enemy(hp: int = 999, attack: int = 0) -> Enemy:
    return Enemy(id="foe", name="Foe", hp=hp, attack=attack, attack_name="Slam")


def _player(*artifacts: Artifact, hp: int = 30) -> PlayerState:
    return PlayerState(hp=hp, max_hp=50, attack=0, deck=[STRIKE] * 30, artifacts=list(artifacts))


def test_pool_has_twenty_distinct_artifacts() -> None:
    assert len(ARTIFACT_POOL) == 20
    assert len({a.id for a in ARTIFACT_POOL}) == 20
    assert len({a.name for a in ARTIFACT_POOL}) == 20
    assert all(a.description for a in ARTIFACT_POOL)


def test_offer_is_distinct_and_skips_owned_artifacts() -> None:
    owned = ARTIFACT_POOL[:15]
    for seed in range(20):
        offer = roll_artifact_offer(random.Random(seed), owned)
        assert len(offer) == ARTIFACT_CHOICES
        assert len({a.id for a in offer}) == ARTIFACT_CHOICES
        assert not {a.id for a in offer} & {a.id for a in owned}


def test_gaining_an_artifact_applies_attack_and_max_hp() -> None:
    player = PlayerState(hp=50, max_hp=50, attack=3)

    gain_artifact(player, _artifact(attack=4, max_hp=-12))

    assert player.attack == 7
    assert (player.hp, player.max_hp) == (38, 38)
    gain_artifact(player, _artifact(max_hp=15))
    assert (player.hp, player.max_hp) == (53, 53)


def test_fight_start_artifacts() -> None:
    player = _player(
        _artifact(start_block=8, opening_hand=2, opening_damage=10, enemy_hp_percent=-10)
    )

    state, log = start_combat(player.deck, _enemy(hp=100), random.Random(1), player.artifacts)

    assert state.player_block == 8
    assert len(state.hand) == HAND_SIZE + 2
    assert state.enemy.hp == 90
    assert state.enemy_hp == 80
    assert any("10 damage" in line for line in log)


def test_extra_draw_every_other_turn() -> None:
    player = _player(_artifact(extra_draw=1, extra_draw_every=2))
    state, _ = start_combat(player.deck, _enemy(), random.Random(1), player.artifacts)
    state.hand.clear()

    end_turn(state, player, random.Random(2))  # draws for turn 2
    assert len(state.hand) == CARDS_PER_TURN + 1
    state.hand.clear()
    end_turn(state, player, random.Random(2))  # draws for turn 3
    assert len(state.hand) == CARDS_PER_TURN


def test_hand_limit_bonus() -> None:
    player = _player(_artifact(max_hand=2))
    state, _ = start_combat(player.deck, _enemy(), random.Random(1), player.artifacts)
    assert max_hand_size(state) == MAX_HAND_SIZE + 2


@pytest.mark.parametrize(
    ("bonus", "expected_hp"),
    [({}, 30 - 10), ({"armor": 3}, 30 - 7), ({"enemy_attack": 2}, 30 - 12)],
)
def test_enemy_attack_modifiers(bonus: dict, expected_hp: int, monkeypatch) -> None:
    player = _player(_artifact(**bonus))
    state, _ = start_combat(player.deck, _enemy(attack=9), random.Random(1), player.artifacts)
    state.enemy_intent = state.enemy_intent.ATTACK
    rng = random.Random(2)
    monkeypatch.setattr(rng, "randint", lambda a, b: 1)

    end_turn(state, player, rng)

    assert player.hp == expected_hp


def test_thorns_hit_the_attacking_enemy() -> None:
    player = _player(_artifact(thorns=4))
    state, _ = start_combat(
        player.deck, _enemy(hp=50, attack=1), random.Random(1), player.artifacts
    )
    state.enemy_intent = state.enemy_intent.ATTACK

    end_turn(state, player, random.Random(2))

    assert state.enemy_hp == 46


def test_turn_block_every_other_turn() -> None:
    player = _player(_artifact(turn_block=5, turn_block_every=2))
    state, _ = start_combat(player.deck, _enemy(), random.Random(1), player.artifacts)

    log1 = end_turn(state, player, random.Random(2))
    log2 = end_turn(state, player, random.Random(2))

    assert not any("artifacts raise" in line for line in log1)
    assert any("artifacts raise 5 block" in line for line in log2)


def test_card_bonuses_and_lifesteal() -> None:
    player = _player(_artifact(block_bonus=2, heal_bonus=3, lifesteal=1))
    state, _ = start_combat(player.deck, _enemy(), random.Random(1), player.artifacts)
    state.hand = [DEFEND, MEND, STRIKE]

    play_card(state, 0, 0, player, random.Random(2))
    assert state.player_block == 5 + 2
    play_card(state, 0, 0, player, random.Random(2))
    assert player.hp == 30 + 4 + 3
    play_card(state, 0, 0, player, random.Random(2))
    assert player.hp == 30 + 4 + 3 + 1


def test_run_offers_an_artifact_at_the_start_and_every_few_steps() -> None:
    run = new_run(1)
    assert run.artifact_offer is not None and len(run.artifact_offer) == ARTIFACT_CHOICES

    choose_artifact(run, 0)
    assert len(run.player.artifacts) == 1 and run.artifact_offer is None

    for step in range(1, ARTIFACT_EVERY_STEPS + 1):
        move_to(run, available_choices(run)[0])
        assert (run.artifact_offer is not None) == (step == ARTIFACT_EVERY_STEPS)
    assert not {a.id for a in run.artifact_offer} & {a.id for a in run.player.artifacts}


def test_api_blocks_the_room_until_an_artifact_is_picked() -> None:
    run = client.post("/runs", json={"seed": 1}).json()
    run_id = run["run_id"]
    assert len(run["artifact_offer"]) == ARTIFACT_CHOICES

    assert client.post(f"/runs/{run_id}/resolve").status_code == 409
    assert client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 5}).status_code == 400

    picked = run["artifact_offer"][2]
    run = client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 2}).json()
    assert run["artifact_offer"] is None
    assert run["player"]["artifacts"][0]["id"] == picked["id"]
    assert client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 0}).status_code == 409
    client.post(f"/runs/{run_id}/card-reward", json={"card_index": None})  # starting pick
    assert client.post(f"/runs/{run_id}/resolve").status_code == 200
