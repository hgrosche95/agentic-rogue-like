import random

from fastapi.testclient import TestClient
from test_api import _play_full_run

from agentic_rogue_like.api import app
from agentic_rogue_like.cards import PROGRAM_REWARD_POOL, REWARD_POOL, starter_deck, upgrade_card
from agentic_rogue_like.combat import EnemyIntentType, end_turn, start_combat
from agentic_rogue_like.engine import (
    end_combat_turn,
    finalize_combat,
    new_run,
    play_combat_card,
    start_combat_node,
)
from agentic_rogue_like.models import Enemy, NodeType, RunState, RunStatus, Status
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.stats import note_changes

client = TestClient(app)


def _card(name: str):
    pool = PROGRAM_REWARD_POOL + REWARD_POOL + starter_deck()
    return next(c for c in pool if c.name == name).model_copy(deep=True)


def _started(seed: int = 1, program_mode: bool = False) -> RunState:
    """A run past its start (artifact, kit, deal), standing in a fight room."""
    run = new_run(seed, program_mode=program_mode)
    run.artifact_offer = run.kit_offer = run.agi_deals = None
    note_changes(run)
    run.nodes[run.current_node_id].type = NodeType.COMBAT
    return run


def test_old_runs_load_without_stats() -> None:
    data = new_run(1).model_dump()
    del data["stats"]

    run = RunState.model_validate(data)

    assert run.stats.fights_won == 0 and run.stats.started_at is None


def test_deck_and_credit_changes_are_counted_but_not_the_start() -> None:
    run = new_run(1)
    run.player.deck.pop()  # the starter kit swapping cards ...
    note_changes(run)
    assert run.stats.cards_removed == 0  # ... is not counted

    run.artifact_offer = run.kit_offer = run.agi_deals = None
    run.player.deck.append(_card("Brute Force").model_copy(update={"id": "new-0"}))
    run.player.deck.pop(0)
    run.player.deck[0] = upgrade_card(run.player.deck[0])
    run.player.gold += 40
    note_changes(run)
    run.player.gold -= 15
    note_changes(run)
    note_changes(run)  # nothing new

    stats = run.stats
    assert (stats.cards_added, stats.cards_removed, stats.cards_upgraded) == (1, 1, 1)
    assert (stats.credits_earned, stats.credits_spent) == (40, 15)


def test_a_won_fight_is_counted() -> None:
    run = _started()
    rng = random.Random(1)
    state = start_combat_node(run, rng)
    state.enemy_hp = 7
    state.hand = [_card("Exploit"), _card("Exploit")]
    play_combat_card(run, state, 0, 0, rng)
    play_combat_card(run, state, 0, 1, rng)
    assert state.enemy_hp <= 0
    finalize_combat(run, state, rng)

    stats = run.stats
    assert stats.fights_won == 1 and stats.turns == 1
    assert stats.damage_dealt == 7  # overkill doesn't count
    assert stats.cards_played == 2 and stats.mvp_card.name == "Exploit"
    assert stats.best_combo.runs == 2 and stats.best_combo.cards == ["Exploit", "Exploit"]
    assert stats.killed_by is None


def test_the_killing_blow_is_named() -> None:
    run = _started()
    rng = random.Random(1)
    state = start_combat_node(run, rng)
    state.hand = []
    state.enemy_intent = EnemyIntentType.ATTACK
    state.enemy_move = None
    run.player.hp = 1
    end_combat_turn(run, state, rng, discard=[])
    assert run.player.hp == 0
    finalize_combat(run, state, rng)

    stats = run.stats
    assert run.status is RunStatus.DEFEAT
    assert stats.killed_by.enemy == state.enemy.name
    assert stats.killed_by.move == state.enemy.attack_name
    assert stats.damage_taken == 1
    assert stats.ended_at is not None and stats.ended_at >= stats.started_at


def test_malware_is_named_as_the_killer() -> None:
    enemy = Enemy(id="e", name="Foe", hp=50, attack=1, attack_name="Hit")
    run = _started()
    state, _ = start_combat(run.player.deck, enemy, random.Random(1))
    state.enemy_intent = EnemyIntentType.DEFEND
    state.player_status = {Status.MALWARE: 5}
    run.player.hp = 3
    end_turn(state, run.player, random.Random(1))

    assert state.tally.killed_by == "Malware" and state.tally.damage_taken == 3


def test_the_best_program_run_is_the_combo() -> None:
    enemy = Enemy(id="e", name="Foe", hp=100, attack=1, attack_name="Hit")
    run = _started(program_mode=True)
    state, _ = start_combat(run.player.deck, enemy, random.Random(1), program_mode=True)
    state.enemy_intent = EnemyIntentType.DEFEND
    rng = random.Random(1)
    state.hand = [_card("Fork"), _card("Exploit")]
    play_combat_card(run, state, 0, 0, rng)
    play_combat_card(run, state, 0, 1, rng)
    end_combat_turn(run, state, rng, discard=[])

    combo = state.tally.best_combo
    assert combo.cards == ["Fork", "Exploit"]
    assert combo.runs == 2 and combo.damage == 100 - state.enemy_hp
    assert state.tally.biggest_hit == combo.damage // 2


def test_the_summary_is_only_shown_once_the_run_is_over() -> None:
    run_id = client.post("/runs", json={"seed": 2}).json()["run_id"]
    assert client.get(f"/runs/{run_id}").json()["summary"] is None

    for seed in range(4):
        run = _play_full_run(seed)
        summary = run["summary"]
        stats = get_session(run["run_id"]).run.stats
        assert summary["fights_won"] == stats.fights_won
        assert summary["turns"] >= summary["fights_won"]
        assert summary["cards_played"] > 0 and summary["mvp_card"] is not None
        assert summary["artifacts_collected"] == len(run["player"]["artifacts"])
        assert summary["duration_seconds"] is not None
        assert (summary["killed_by"] is None) == (run["status"] == "victory")
