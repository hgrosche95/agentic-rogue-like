import random

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like.api import app
from agentic_rogue_like.balance_sim import mean_damage_taken, smart_bot
from agentic_rogue_like.cards import REWARD_POOL, can_upgrade, reward_card, starter_deck
from agentic_rogue_like.combat import (
    EXPOSED_FACTOR,
    EnemyIntentType,
    attack_damage,
    end_turn,
    enemy_attack,
    play_card,
    start_combat,
)
from agentic_rogue_like.enemies import ENEMY_POOL
from agentic_rogue_like.models import Enemy, EnemyMove, MoveKind, PlayerState, Status
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.threat import threat


def _card(name: str):
    return reward_card(next(c for c in REWARD_POOL if c.name == name), [])


def _fight(*hand_names: str, moves: list[EnemyMove] | None = None):
    enemy = Enemy(
        id="e",
        name="Foe",
        hp=200,
        attack=10,
        attack_name="Hit",
        **({"moves": moves} if moves else {}),
    )
    player = PlayerState(hp=100, max_hp=100, attack=2, deck=starter_deck())
    state, _ = start_combat(player.deck, enemy, random.Random(1))
    state.hand = [_card(n) for n in hand_names] + state.hand
    return state, player


def _calm_turn(state, player) -> list[str]:
    """End the turn against an enemy that only braces - nothing hits the player."""
    state.enemy_intent = EnemyIntentType.DEFEND
    return end_turn(
        state,
        player,
        random.Random(2),
        discard=list(range(len(state.hand) - 8)) if len(state.hand) > 8 else None,
    )


def test_malware_bites_at_the_end_of_the_turn_and_fades() -> None:
    state, player = _fight("Trojan")
    play_card(state, 0, 0, player, random.Random(2))
    assert state.enemy_status == {Status.MALWARE: 3}
    hp = state.enemy_hp

    log = _calm_turn(state, player)

    assert state.enemy_hp == hp - 3
    assert state.enemy_status == {Status.MALWARE: 2}
    assert any("Malware eats 3" in line for line in log)


def test_malware_can_finish_the_enemy() -> None:
    state, player = _fight()
    state.enemy_hp = 2
    state.enemy_status[Status.MALWARE] = 5
    _calm_turn(state, player)
    assert state.enemy_hp == 0


def test_exposed_makes_attack_cards_hit_harder_until_it_wears_off() -> None:
    state, player = _fight("Port Scan")
    exploit = next(c for c in state.hand if c.name == "Exploit")
    plain = attack_damage(state, exploit, player)

    play_card(state, 0, 0, player, random.Random(2))

    assert attack_damage(state, exploit, player) == round(plain * EXPOSED_FACTOR)
    _calm_turn(state, player)
    _calm_turn(state, player)
    assert Status.EXPOSED not in state.enemy_status
    assert attack_damage(state, exploit, player) == plain


def test_throttled_enemies_hit_softer() -> None:
    state, player = _fight("Packet Loss")
    before = enemy_attack(state)
    play_card(state, 0, 0, player, random.Random(2))
    assert enemy_attack(state) < before
    assert state.player_block >= 5


def test_worm_scales_with_the_enemys_malware() -> None:
    state, player = _fight("Worm")
    worm = state.hand[0]
    plain = attack_damage(state, worm, player)
    state.enemy_status[Status.MALWARE] = 4
    assert attack_damage(state, worm, player) == plain + 4 * worm.scale_value


def test_infect_leaves_malware_on_the_player() -> None:
    infect = EnemyMove(kind=MoveKind.INFECT, name="Miasma", stacks=4)
    state, player = _fight(moves=[EnemyMove(kind=MoveKind.ATTACK), infect])
    state.enemy_move, state.enemy_intent = 1, EnemyIntentType.INFECT
    hp = player.hp

    log = end_turn(state, player, random.Random(2))

    assert any("Malware creeps" in line for line in log)
    assert state.player_status == {Status.MALWARE: 3}  # bit 4 already, one stack faded
    assert hp - player.hp >= 4


def test_every_status_card_has_an_upgrade() -> None:
    for card in REWARD_POOL:
        if card.applies is not None or card.scaling is not None:
            assert can_upgrade(card), card.name


def test_the_pool_infects_and_infect_is_priced_like_its_damage() -> None:
    doctor = next(e for e in ENEMY_POOL["mid"] if any(m.kind is MoveKind.INFECT for m in e.moves))
    plain = Enemy(id="p", name="Plain", hp=60, attack=10, attack_name="Hit")
    # Scaled to the same threat, the infecting enemy deals about what a plain one does.
    plain = plain.model_copy(update={"hp": round(plain.hp * threat(doctor) / threat(plain))})
    assert mean_damage_taken(doctor, smart_bot, 300, "doctor") == pytest.approx(
        mean_damage_taken(plain, smart_bot, 300, "plain"), rel=0.2
    )


def test_api_shows_statuses_on_both_sides() -> None:
    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 3}).json()["run_id"]
    run = get_session(run_id).run
    run.artifact_offer = run.kit_offer = None
    client.post(f"/runs/{run_id}/resolve")
    combat = get_session(run_id).combat
    combat.enemy_status[Status.EXPOSED] = 2
    combat.player_status[Status.MALWARE] = 3

    view = client.get(f"/runs/{run_id}").json()["pending_combat"]

    assert view["enemy_status"] == {"exposed": 2}
    assert view["player_status"] == {"malware": 3}
