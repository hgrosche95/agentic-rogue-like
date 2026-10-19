import random

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like.api import app
from agentic_rogue_like.balance_sim import mean_damage_taken, smart_bot
from agentic_rogue_like.cards import starter_deck
from agentic_rogue_like.combat import (
    ARMORED_BLOCK_FACTOR,
    REGEN_FACTOR,
    THORNY_DAMAGE,
    EnemyIntentType,
    end_turn,
    enemy_attack,
    play_card,
    start_combat,
)
from agentic_rogue_like.enemies import ENEMY_POOL, with_affix
from agentic_rogue_like.engine import new_run, start_combat_node
from agentic_rogue_like.models import Affix, CardType, Enemy, NodeType, PlayerState
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.threat import threat

OGRE = ENEMY_POOL["elite"][0]


def _player() -> PlayerState:
    return PlayerState(hp=500, max_hp=500, attack=2, deck=starter_deck())


def _fight(affix: Affix, hp: int = 100):
    enemy = Enemy(id="e", name="Brute", hp=hp, attack=10, attack_name="Hit", affix=affix)
    player = _player()
    state, log = start_combat(player.deck, enemy, random.Random(1))
    return state, player, log


@pytest.mark.parametrize("affix", list(Affix))
def test_with_affix_keeps_the_threat(affix: Affix) -> None:
    for elite in ENEMY_POOL["elite"]:
        armed = with_affix(elite, _always(affix))
        assert armed.affix is affix
        assert armed.hp != elite.hp
        assert threat(armed) == pytest.approx(threat(elite), rel=0.03)


@pytest.mark.parametrize("affix", list(Affix))
def test_an_affixed_elite_hits_about_as_hard_as_its_plain_self(affix: Affix) -> None:
    plain = mean_damage_taken(OGRE, smart_bot, fights=300, seed="plain")
    armed = mean_damage_taken(with_affix(OGRE, _always(affix)), smart_bot, 300, seed=affix)
    assert armed == pytest.approx(plain, rel=0.2)


def _always(affix: Affix) -> random.Random:
    rng = random.Random(0)
    rng.choice = lambda options: affix
    return rng


def test_the_fight_opens_by_naming_the_affix() -> None:
    _, _, log = _fight(Affix.ARMORED)
    assert any("armored" in line for line in log)


def test_armored_raises_block_after_its_turn() -> None:
    state, player, _ = _fight(Affix.ARMORED)
    state.enemy_intent = EnemyIntentType.ATTACK
    end_turn(state, player, random.Random(2))
    assert state.enemy_block == round(10 * ARMORED_BLOCK_FACTOR)


def test_regenerating_heals_after_its_turn_but_never_past_max() -> None:
    state, player, _ = _fight(Affix.REGENERATING)
    state.enemy_intent = EnemyIntentType.ATTACK
    state.enemy_hp = 50
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 50 + round(10 * REGEN_FACTOR)

    state.enemy_hp = 99
    end_turn(state, player, random.Random(2))
    assert state.enemy_hp == 100


def test_enraged_hits_harder_from_half_hp_on() -> None:
    state, _, _ = _fight(Affix.ENRAGED)
    calm = enemy_attack(state)
    state.enemy_hp = 50
    assert enemy_attack(state) == calm + 5


def test_thorny_costs_hp_for_every_attack_card() -> None:
    state, player, _ = _fight(Affix.THORNY)
    exploit = next(i for i, c in enumerate(state.hand) if c.type is CardType.ATTACK)
    before = player.hp

    line = play_card(state, exploit, 0, player, random.Random(2))

    assert player.hp == before - THORNY_DAMAGE
    assert "thorns" in line


def _room(run, node_type: NodeType) -> None:
    run.artifact_offer = run.card_reward = None
    run.current_node_id = next(i for i, n in run.nodes.items() if n.type is node_type)


def test_only_elite_rooms_roll_an_affix_and_the_seed_decides_which() -> None:
    affixes = set()
    for seed in range(8):
        run = new_run(seed)
        if not any(n.type is NodeType.ELITE for n in run.nodes.values()):
            continue
        _room(run, NodeType.ELITE)
        first = start_combat_node(run, random.Random(1)).enemy.affix
        again = new_run(seed)
        _room(again, NodeType.ELITE)
        assert start_combat_node(again, random.Random(99)).enemy.affix is first
        affixes.add(first)

        plain = new_run(seed)
        _room(plain, NodeType.COMBAT)
        assert start_combat_node(plain, random.Random(1)).enemy.affix is None
    assert len(affixes) > 1 and None not in affixes


def test_api_shows_the_affix() -> None:
    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 2}).json()["run_id"]
    run = get_session(run_id).run
    if not any(n.type is NodeType.ELITE for n in run.nodes.values()):
        pytest.skip("seed has no elite room")
    _room(run, NodeType.ELITE)

    combat = client.post(f"/runs/{run_id}/resolve").json()["pending_combat"]

    assert combat["enemy_affix"] in {a.value for a in Affix}
    assert combat["enemy_affix_description"]
    assert combat["enemy_enraged"] is False
