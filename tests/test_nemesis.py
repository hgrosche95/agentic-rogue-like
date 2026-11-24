"""The nemesis (nemesis.py): last run's killer returns as act 1's first elite."""

import random

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like.agent.budgets import tier_budget
from agentic_rogue_like.api import app
from agentic_rogue_like.engine import new_run, start_combat_node
from agentic_rogue_like.models import EnemyMove, MoveKind, NemesisSpec, NodeType
from agentic_rogue_like.nemesis import nemesis_enemy, nemesis_line
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.threat import threat

client = TestClient(app)

SLIME = {
    "name": "Cave Slime",
    "description": "A quivering green blob.",
    "attack_name": "Acid Splash",
    "moves": [
        {"kind": "attack", "name": "Acid Splash", "weight": 3},
        {"kind": "defend", "name": "Gelatinous Wall", "weight": 1},
    ],
}


def _spec(**overrides) -> NemesisSpec:
    return NemesisSpec.model_validate({**SLIME, **overrides})


def _elite_seed() -> int:
    return next(
        s for s in range(50) if any(n.type is NodeType.ELITE for n in new_run(s).nodes.values())
    )


def _enter(run, node_type: NodeType, skip: int = 0) -> None:
    run.artifact_offer = run.kit_offer = None
    nodes = sorted((n for n in run.nodes.values() if n.type is node_type), key=lambda n: n.id)
    run.current_node_id = nodes[skip].id


@pytest.mark.parametrize(
    "moves",
    [
        SLIME["moves"],
        [{"kind": "barrage", "hits": 3}, {"kind": "defend"}],
        [{"kind": "attack"}, {"kind": "infect", "stacks": 4}, {"kind": "purge"}],
        [{"kind": "attack", "power": 300}],
    ],
)
def test_the_nemesis_is_an_elite_in_the_middle_of_its_threat_range(moves) -> None:
    budget = tier_budget("elite")
    low, high = budget.threat_range()

    enemy = nemesis_enemy(_spec(moves=moves))

    assert enemy is not None
    assert low <= threat(enemy) <= high
    assert abs(threat(enemy) - (low + high) / 2) < (high - low) / 4
    assert enemy.attack == budget.max_attack
    assert enemy.affix is None
    assert enemy.name == "Returned Cave Slime"
    assert enemy.taunt == nemesis_line("Cave Slime")


def test_the_nemesis_returns_once_as_the_first_elite_of_act_one() -> None:
    seed = _elite_seed()
    run = new_run(seed, nemesis=_spec())

    _enter(run, NodeType.COMBAT)
    assert not start_combat_node(run, random.Random(1)).enemy.name.startswith("Returned")
    assert not run.nemesis_met

    _enter(run, NodeType.ELITE)
    state = start_combat_node(run, random.Random(1))
    assert state.enemy.name == "Returned Cave Slime"
    assert state.enemy.affix is None
    assert nemesis_line("Cave Slime") in run.history
    assert run.nemesis_met

    # a second elite room is an ordinary elite again
    _enter(run, NodeType.ELITE)
    assert not start_combat_node(run, random.Random(1)).enemy.name.startswith("Returned")


def test_the_nemesis_never_returns_after_act_one() -> None:
    run = new_run(_elite_seed(), nemesis=_spec())
    run.act = 2
    _enter(run, NodeType.ELITE)
    assert not start_combat_node(run, random.Random(1)).enemy.name.startswith("Returned")


def test_a_move_set_without_an_attack_is_dropped() -> None:
    with pytest.raises(ValueError):
        _spec(moves=[{"kind": "defend"}, {"kind": "infect"}])
    assert new_run(1, nemesis=None).nemesis is None


def test_the_api_takes_a_valid_nemesis() -> None:
    response = client.post("/runs", json={"seed": 1, "nemesis": SLIME})
    assert response.status_code == 200
    run = get_session(response.json()["run_id"]).run
    assert run.nemesis is not None and run.nemesis.name == "Cave Slime"


@pytest.mark.parametrize(
    "nemesis",
    [
        {**SLIME, "moves": [{"kind": "defend"}, {"kind": "lock"}]},  # no attack
        {**SLIME, "name": "x" * 41},  # too long
        {**SLIME, "name": "   "},  # empty once trimmed
        {**SLIME, "moves": [{"kind": "interrupt"}, {"kind": "attack"}]},  # program-only move
        {**SLIME, "moves": []},
        "Cave Slime",
        42,
    ],
)
def test_an_invalid_nemesis_is_ignored_and_the_run_starts_normally(nemesis) -> None:
    response = client.post("/runs", json={"seed": 1, "nemesis": nemesis})
    assert response.status_code == 200
    assert get_session(response.json()["run_id"]).run.nemesis is None


def test_a_nemesis_move_keeps_its_own_values() -> None:
    enemy = nemesis_enemy(_spec(moves=[{"kind": "barrage", "hits": 4, "power": 30}]))
    assert enemy is not None
    assert enemy.moves == [EnemyMove(kind=MoveKind.BARRAGE, hits=4, power=30)]
