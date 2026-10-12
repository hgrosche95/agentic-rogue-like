import random
from unittest.mock import patch

import pytest
from langchain_groq import ChatGroq

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.encounter_schema import BudgetViolation, EnemyBudget, EnemyProposal
from agentic_rogue_like.agent.ollama_model import DEFAULT_MODEL_NAME, OllamaChatModel


class _AlwaysOverpowered:
    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return EnemyProposal(
            name="Overpowered Thing",
            description="Too strong.",
            hp=999,
            attack=999,
            attack_name="Overkill",
        )


class _ApiIsDown:
    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        raise ConnectionError("groq unreachable")


def test_retry_loop_gives_up_after_max_attempts() -> None:
    with patch.object(encounter_agent, "_model", return_value=_AlwaysOverpowered()):
        budget = EnemyBudget(min_hp=15, max_hp=25, min_attack=2, max_attack=4)
        app = encounter_agent.build_graph()
        result = app.invoke({"budget": budget, "attempt": 0, "last_error": None, "proposal": None})

    assert result["attempt"] == encounter_agent.MAX_ATTEMPTS
    assert result["last_error"] is not None


def test_generate_balanced_enemy_raises_after_exhausting_retries() -> None:
    with patch.object(encounter_agent, "_model", return_value=_AlwaysOverpowered()):
        with pytest.raises(BudgetViolation):
            encounter_agent.generate_balanced_enemy(
                enemy_id="agent-test", floor=0, num_floors=8, elite=False, boss=False
            )


class _WellBehaved:
    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return EnemyProposal(
            name="Crystal Wisp",
            description="Glows faintly.",
            hp=36,
            attack=9,
            attack_name="Prism Flare",
        )


def _enemy_for_node(model_stub: object) -> object:
    with patch.object(encounter_agent, "_model", return_value=model_stub):
        return encounter_agent.enemy_for_node(
            enemy_id="agent-test",
            floor=0,
            num_floors=8,
            elite=False,
            boss=False,
            rng=random.Random(1),
        )


def test_enemy_for_node_uses_static_pool_when_agent_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_ENABLED", raising=False)

    def _fail_if_called() -> None:
        raise AssertionError("model should never be built when the agent is disabled")

    with patch.object(encounter_agent, "_model", side_effect=_fail_if_called):
        enemy = encounter_agent.enemy_for_node(
            enemy_id="agent-test",
            floor=0,
            num_floors=8,
            elite=False,
            boss=False,
            rng=random.Random(1),
        )

    assert enemy.name in ("Rat Swarm", "Cave Slime")


def test_enemy_for_node_uses_agent_when_enabled_and_it_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    enemy = _enemy_for_node(_WellBehaved())

    assert enemy.name == "Crystal Wisp"


def test_enemy_for_node_falls_back_when_the_api_is_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    enemy = _enemy_for_node(_ApiIsDown())

    assert enemy.name in ("Rat Swarm", "Cave Slime")


def test_enemy_for_node_falls_back_when_the_agent_never_meets_its_budget(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    enemy = _enemy_for_node(_AlwaysOverpowered())

    assert enemy.hp != 999


def test_model_defaults_to_groq(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    # ChatGroq() needs a key to construct (not to actually call) - pytest
    # deliberately never loads .env, see README.md.
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    assert isinstance(encounter_agent._model(), ChatGroq)


def test_model_source_ollama_uses_the_default_model_name(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_MODEL_SOURCE", "ollama")
    monkeypatch.delenv("ENCOUNTER_AGENT_OLLAMA_MODEL", raising=False)

    model = encounter_agent._model()

    assert isinstance(model, OllamaChatModel)
    assert model._model_name == DEFAULT_MODEL_NAME


def test_model_source_ollama_respects_model_override(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_MODEL_SOURCE", "ollama")
    monkeypatch.setenv("ENCOUNTER_AGENT_OLLAMA_MODEL", "some-other-tag")

    model = encounter_agent._model()

    assert isinstance(model, OllamaChatModel)
    assert model._model_name == "some-other-tag"


def test_model_source_ollama_constrains_output(monkeypatch) -> None:
    """The default model is only schema-valid with constrained decoding, and
    it costs nothing for models that don't need it - so it stays on."""
    monkeypatch.setenv("ENCOUNTER_AGENT_MODEL_SOURCE", "ollama")
    monkeypatch.setenv("ENCOUNTER_AGENT_OLLAMA_MODEL", "some-other-tag")

    assert encounter_agent._model()._constrain_output is True


# --------------------------------------------------------------- move sets

from agentic_rogue_like.agent.encounter_schema import MoveProposal, MovesetProposal  # noqa: E402
from agentic_rogue_like.models import MoveKind  # noqa: E402


class _Recording:
    """Answers with `proposals` in turn and records the schemas and prompts it got."""

    def __init__(self, *proposals):
        self.proposals = list(proposals)
        self.schemas, self.prompts = [], []

    def with_structured_output(self, schema):
        self.schemas.append(schema)
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.proposals.pop(0)


def _boar(hp: int) -> MovesetProposal:
    return MovesetProposal(
        name="Chrome Boar",
        description="A cybernetic boar with hydraulic tusks.",
        hp=hp,
        attack=8,
        attack_name="Hydraulic Gore",
        moves=[
            MoveProposal(kind=MoveKind.ATTACK, name="Hydraulic Gore", weight=3, power=100),
            MoveProposal(kind=MoveKind.BARRAGE, name="Rivet Spray", weight=2, power=35, hits=3),
        ],
    )


def test_agent_asks_groq_for_a_move_set_and_the_enemy_gets_it(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    model = _Recording(_boar(hp=30))
    with patch.object(encounter_agent, "_model", return_value=model):
        enemy = encounter_agent.generate_balanced_enemy(
            enemy_id="e", floor=0, num_floors=8, elite=False, boss=False, setting="cyberpunk"
        )

    assert model.schemas == [MovesetProposal]
    assert "2 to 4 moves" in model.prompts[0]
    assert [m.name for m in enemy.moves] == ["Hydraulic Gore", "Rivet Spray"]
    assert enemy.moves[1].hits == 3
    assert enemy.description.startswith("A cybernetic boar")


def test_threat_violation_is_fed_back_with_a_fitting_hp(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    model = _Recording(_boar(hp=55), _boar(hp=30))
    with patch.object(encounter_agent, "_model", return_value=model):
        enemy = encounter_agent.generate_balanced_enemy(
            enemy_id="e", floor=0, num_floors=8, elite=False, boss=False
        )

    assert "previous attempt was rejected: threat" in model.prompts[1]
    assert "Change hp to about" in model.prompts[1]
    assert enemy.hp == 30


def test_bosses_and_the_fine_tuned_model_keep_the_plain_schema(monkeypatch) -> None:
    plain = EnemyProposal(
        name="Overseer", description="d", hp=95, attack=13, attack_name="Null Decree"
    )
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    boss_model = _Recording(plain)
    with patch.object(encounter_agent, "_model", return_value=boss_model):
        boss = encounter_agent.generate_balanced_enemy(
            enemy_id="b", floor=7, num_floors=8, elite=False, boss=True
        )
    assert boss_model.schemas == [EnemyProposal]
    assert "moves" not in boss_model.prompts[0]
    assert len(boss.moves) == 2  # the default set - bosses roll their own anyway

    monkeypatch.setenv("ENCOUNTER_AGENT_MODEL_SOURCE", "ollama")
    tuned = _Recording(plain.model_copy(update={"hp": 36, "attack": 9}))
    with patch.object(encounter_agent, "_model", return_value=tuned):
        encounter_agent.generate_balanced_enemy(
            enemy_id="e", floor=0, num_floors=8, elite=False, boss=False
        )
    assert tuned.schemas == [EnemyProposal]


def test_training_can_pin_the_plain_prompt(monkeypatch) -> None:
    from agentic_rogue_like.agent.budgets import _BUDGETS

    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    state = {
        "budget": _BUDGETS["mid"],
        "setting": "dungeon",
        "attempt": 0,
        "last_error": None,
        "proposal": None,
    }
    assert "moves" in encounter_agent._build_prompt(state)
    plain = encounter_agent._build_prompt({**state, "with_moves": False})
    assert plain.startswith("Invent an enemy for a dungeon-themed roguelike encounter.")
    assert "It must have hp between 48 and 60" in plain
