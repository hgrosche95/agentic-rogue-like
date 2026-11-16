"""What an enemy looks like: body_shape and feature, from fixed lists."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.encounter_schema import EnemyProposal, MoveProposal, MovesetProposal
from agentic_rogue_like.api import app
from agentic_rogue_like.combat import start_combat
from agentic_rogue_like.enemies import ENEMY_POOL
from agentic_rogue_like.models import BodyShape, Enemy, Feature, MoveKind
from agentic_rogue_like.sessions import get_session

_MOVES = [
    MoveProposal(kind=MoveKind.ATTACK, name="Stone Claw", weight=3, power=100),
    MoveProposal(kind=MoveKind.DEFEND, name="Stone Skin", weight=2, power=100),
]


def _proposal(**looks) -> MovesetProposal:
    return MovesetProposal(
        name="Gargoyle",
        description="A winged statue that was never quite as still as it looked.",
        hp=54,
        attack=10,
        attack_name="Stone Claw",
        moves=_MOVES,
        **looks,
    )


class _Model:
    def __init__(self, proposal) -> None:
        self.proposal = proposal
        self.prompts: list[str] = []

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return {"raw": SimpleNamespace(), "parsed": self.proposal, "parsing_error": None}


def test_a_proposal_with_valid_looks_lands_in_the_enemy(monkeypatch) -> None:
    model = _Model(_proposal(body_shape="brute", feature="horns"))
    monkeypatch.setattr(encounter_agent, "_model", lambda: model)
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)

    enemy = encounter_agent.generate_balanced_enemy(
        "e1", floor=4, num_floors=8, elite=False, boss=False
    )

    assert enemy.body_shape is BodyShape.BRUTE
    assert enemy.feature is Feature.HORNS
    # the prompt asks for both, to fit the name
    assert "body_shape" in model.prompts[0] and "feature" in model.prompts[0]


@pytest.mark.parametrize("looks", [{"body_shape": "dragon"}, {"feature": "wings"}])
def test_an_unknown_value_fails_the_schema(looks) -> None:
    with pytest.raises(ValidationError):
        _proposal(**looks)


def test_looks_are_optional() -> None:
    proposal = _proposal()
    assert proposal.body_shape is None and proposal.feature is None
    assert Enemy(id="x", name="x", hp=1, attack=1, attack_name="x").body_shape is None


def test_the_plain_schema_has_no_looks() -> None:
    # bosses and the fine-tuned Ollama model keep the schema they had
    assert "body_shape" not in EnemyProposal.model_fields
    assert "feature" not in EnemyProposal.model_fields
    assert "body_shape" not in encounter_agent._plain_prompt(
        {"budget": encounter_agent.budget_for(4, 8, False, False), "setting": "dungeon"}
    )


@pytest.mark.parametrize(
    "enemy", [e for pool in ENEMY_POOL.values() for e in pool], ids=lambda e: e.name
)
def test_every_pool_enemy_has_both(enemy: Enemy) -> None:
    assert isinstance(enemy.body_shape, BodyShape)
    assert isinstance(enemy.feature, Feature)


def test_the_api_reports_the_looks() -> None:
    client = TestClient(app)
    run = client.post("/runs", json={"seed": 7}).json()
    run_id = run["run_id"]
    for _ in range(40):
        run = client.get(f"/runs/{run_id}").json()
        if run["artifact_offer"] is not None:
            client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 0})
        if run["kit_offer"] is not None:
            client.post(f"/runs/{run_id}/kit", json={"kit_index": 0})
            client.post(f"/runs/{run_id}/agi-deal", json={"deal_index": None})
        run = client.post(f"/runs/{run_id}/resolve").json()
        if run["pending_combat"] is not None:
            break
        if run["pending_event"] is not None:
            client.post(f"/runs/{run_id}/event-choice", json={"option_index": 0})
        run = client.get(f"/runs/{run_id}").json()
        client.post(
            f"/runs/{run_id}/choose-node", json={"node_id": run["available_choices"][0]["id"]}
        )
    combat = run["pending_combat"]

    pool = {e.name: e for p in ENEMY_POOL.values() for e in p}
    expected = pool[combat["enemy_name"]]
    assert combat["enemy_body_shape"] == expected.body_shape.value
    assert combat["enemy_feature"] == expected.feature.value


def test_without_looks_the_api_sends_none() -> None:
    client = TestClient(app)
    run = client.post("/runs", json={"seed": 7}).json()
    session = get_session(run["run_id"])
    # a fight against an enemy nobody gave looks (as from the plain schema)
    plain = Enemy(id="p", name="Plain Thing", hp=30, attack=5, attack_name="Bonk")
    session.combat, _ = start_combat(session.run.player.deck, plain, random.Random(1))

    combat = client.get(f"/runs/{run['run_id']}").json()["pending_combat"]

    assert combat["enemy_body_shape"] is None
    assert combat["enemy_feature"] is None


@pytest.mark.parametrize(
    "given,shape,feature",
    [
        ("Serpent", "serpent", "fins"),
        ("brutes", "brute", "horns"),
        (" GHOSTS ", "ghost", "circuits"),
    ],
)
def test_spelling_variants_land_on_their_value(given, shape, feature) -> None:
    singular = {"fins": "fin", "horns": "Horn", "circuits": "circuit"}[feature]
    proposal = _proposal(body_shape=given, feature=singular)

    assert proposal.body_shape is BodyShape(shape)
    assert proposal.feature is Feature(feature)


def test_the_tool_schema_lets_the_variants_through() -> None:
    # Groq checks a tool call against this before our validators run
    from langchain_core.utils.function_calling import convert_to_openai_tool

    props = convert_to_openai_tool(MovesetProposal)["function"]["parameters"]["properties"]
    features = props["feature"]["anyOf"][0]["enum"]
    assert {"circuit", "circuits", "horn", "horns"} <= set(features)
    assert "wings" not in features


class _ToolUseFailed(Exception):
    """What groq.BadRequestError carries for a tool call off its schema."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.body = {
            "error": {
                "code": "tool_use_failed",
                "message": message,
                "type": "invalid_request_error",
            }
        }


class _RejectsFirst:
    """Turns down the first tool call like Groq does, then answers."""

    def __init__(self, proposal) -> None:
        self.proposal = proposal
        self.prompts: list[str] = []

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            raise _ToolUseFailed(
                "parameters for tool MovesetProposal did not match schema: /feature"
            )
        return {"raw": SimpleNamespace(), "parsed": self.proposal, "parsing_error": None}


def test_a_rejected_tool_call_is_retried_like_a_violation(monkeypatch) -> None:
    model = _RejectsFirst(_proposal(body_shape="brute", feature="horns"))
    monkeypatch.setattr(encounter_agent, "_model", lambda: model)
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)

    enemy = encounter_agent.generate_balanced_enemy(
        "e1", floor=4, num_floors=8, elite=False, boss=False
    )

    assert enemy.name == "Gargoyle"
    assert len(model.prompts) == 2
    assert "rejected" in model.prompts[1] and "/feature" in model.prompts[1]


def test_other_errors_still_raise(monkeypatch) -> None:
    class _Down:
        def with_structured_output(self, schema, include_raw: bool = False):
            return self

        def invoke(self, prompt):
            raise ConnectionError("groq unreachable")

    monkeypatch.setattr(encounter_agent, "_model", lambda: _Down())
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)

    with pytest.raises(ConnectionError):
        encounter_agent.generate_balanced_enemy(
            "e1", floor=4, num_floors=8, elite=False, boss=False
        )


@pytest.mark.parametrize(
    "code,retried",
    [("tool_use_failed", True), ("output_parse_failed", True), ("rate_limit_exceeded", False)],
)
def test_only_model_mistakes_count_as_rejections(code, retried) -> None:
    exc = Exception("groq says no")
    exc.body = {"error": {"code": code, "message": "groq says no"}}

    assert (encounter_agent.rejected_tool_call(exc) is not None) is retried
