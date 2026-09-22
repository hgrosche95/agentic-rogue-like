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
            hp=30,
            attack=7,
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
    monkeypatch.setenv("ENCOUNTER_AGENT_OLLAMA_MODEL", "qwen2.5-enemy-generator")

    model = encounter_agent._model()

    assert isinstance(model, OllamaChatModel)
    assert model._model_name == "qwen2.5-enemy-generator"
