"""The run's final boss: the last act's boss is always the AGI itself (OMEGA),
earlier acts keep their own, and no LLM call is ever made for it."""

import random
from unittest.mock import patch

from fastapi.testclient import TestClient

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.budgets import _BUDGETS
from agentic_rogue_like.api import app
from agentic_rogue_like.combat import start_combat
from agentic_rogue_like.enemies import ENEMY_POOL, FINAL_BOSS_ID
from agentic_rogue_like.engine import (
    NUM_ACTS,
    NUM_FLOORS,
    is_final_boss,
    new_run,
    start_combat_node,
)
from agentic_rogue_like.prefetch import Prefetch

BOSS_NODE = f"{NUM_FLOORS - 1}-0"


def _boss_fight(act: int, seed: int = 5):
    run = new_run(seed)
    run.act = act
    run.current_node_id = BOSS_NODE
    return run, start_combat_node(run, random.Random(seed))


def test_the_last_acts_boss_is_the_agi() -> None:
    for seed in range(5):
        run, state = _boss_fight(NUM_ACTS, seed)
        assert is_final_boss(run, run.nodes[BOSS_NODE])
        assert state.boss and state.enemy.id == FINAL_BOSS_ID
        assert state.enemy.name == "OMEGA"
        assert state.boss_phases == 3


def test_earlier_acts_keep_their_own_boss() -> None:
    for seed in range(5):
        run, state = _boss_fight(1, seed)
        assert not is_final_boss(run, run.nodes[BOSS_NODE])
        assert state.enemy.id == "the-warden"


def test_the_final_boss_never_asks_the_encounter_agent(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    def _fail_if_called():
        raise AssertionError("the final boss must not be generated")

    with patch.object(encounter_agent, "_model", side_effect=_fail_if_called):
        _, state = _boss_fight(NUM_ACTS)
        enemy = encounter_agent.enemy_for_node(
            enemy_id="agent-test",
            floor=NUM_FLOORS - 1,
            num_floors=NUM_FLOORS,
            elite=False,
            boss=True,
            rng=random.Random(1),
            act=NUM_ACTS,
            final=True,
            prefetched=_fail_if_called,
        )

    assert state.enemy.id == FINAL_BOSS_ID
    assert enemy.id == FINAL_BOSS_ID


def test_the_final_boss_is_not_prefetched(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    run = new_run(5)
    run.act = NUM_ACTS
    run.current_node_id = BOSS_NODE
    prefetch = Prefetch()
    with patch("agentic_rogue_like.prefetch._executor") as executor:
        prefetch.warm(run)
    assert BOSS_NODE not in prefetch.enemies
    assert executor.submit.call_count == 0 or all(
        call.args[0] is not encounter_agent.generate_balanced_enemy
        for call in executor.submit.call_args_list
    )


def test_the_final_boss_stays_inside_the_boss_budget() -> None:
    budget = _BUDGETS["boss"]
    (omega,) = ENEMY_POOL["final"]
    assert budget.min_hp <= omega.hp <= budget.max_hp
    assert budget.min_attack <= omega.attack <= budget.max_attack
    # As strong as the boss it took over the last act from.
    (architect,) = ENEMY_POOL["boss2"]
    assert (omega.hp, omega.attack) == (architect.hp, architect.attack)
    assert omega.description and omega.taunt and len(omega.phase_taunts) == 2


def test_the_final_boss_taunts_as_it_enters_each_phase() -> None:
    (omega,) = ENEMY_POOL["final"]
    state, log = start_combat([], omega, random.Random(1), boss=True, boss_phases=3)
    assert omega.taunt in log

    from agentic_rogue_like.combat import _check_boss_phase

    state.enemy_hp = omega.hp // 2
    assert omega.phase_taunts[0] in _check_boss_phase(state)
    state.enemy_hp = omega.hp // 4
    line = _check_boss_phase(state)
    assert omega.phase_taunts[1] in line and omega.phase_taunts[0] not in line


def test_combat_view_flags_the_final_boss() -> None:
    from agentic_rogue_like.sessions import get_session

    client = TestClient(app)

    def _resolve(run_id: str) -> dict:
        run = client.get(f"/runs/{run_id}").json()
        if run["artifact_offer"] is not None:
            client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 0})
        if run["kit_offer"] is not None:
            client.post(f"/runs/{run_id}/kit", json={"kit_index": 0})
            client.post(f"/runs/{run_id}/agi-deal", json={"deal_index": None})
        return client.post(f"/runs/{run_id}/resolve").json()

    run_id = client.post("/runs", json={"seed": 5}).json()["run_id"]
    assert _resolve(run_id)["pending_combat"]["final_boss"] is False

    run_id = client.post("/runs", json={"seed": 5}).json()["run_id"]
    session = get_session(run_id)
    session.run.act = NUM_ACTS
    session.run.current_node_id = BOSS_NODE
    combat = _resolve(run_id)["pending_combat"]
    assert combat["final_boss"] is True
    assert combat["enemy_name"] == "OMEGA"
    # the boss intro and the phase banners speak its lines; the turn banner counts
    (omega,) = ENEMY_POOL["final"]
    assert combat["enemy_taunt"] == omega.taunt
    assert combat["enemy_phase_taunts"] == omega.phase_taunts
    assert combat["turn"] == 1
    turned = client.post(f"/runs/{run_id}/combat/end-turn", json={"discard_indices": []}).json()
    assert turned["pending_combat"]["turn"] == 2
