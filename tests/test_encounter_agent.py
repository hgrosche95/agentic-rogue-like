import random
from unittest.mock import patch

import pytest
from langchain_groq import ChatGroq

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.encounter_schema import BudgetViolation, EnemyBudget, EnemyProposal
from agentic_rogue_like.agent.ollama_model import DEFAULT_MODEL_NAME, OllamaChatModel
from agentic_rogue_like.enemies import ENEMY_POOL


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

    assert enemy.name in {e.name for e in ENEMY_POOL["early"]}


def test_enemy_for_node_uses_agent_when_enabled_and_it_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    enemy = _enemy_for_node(_WellBehaved())

    assert enemy.name == "Crystal Wisp"


def test_enemy_for_node_falls_back_when_the_api_is_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    enemy = _enemy_for_node(_ApiIsDown())

    assert enemy.name in {e.name for e in ENEMY_POOL["early"]}


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

from agentic_rogue_like.agent.budgets import budget_for  # noqa: E402
from agentic_rogue_like.agent.encounter_schema import (  # noqa: E402
    MoveProposal,
    MovesetProposal,
    ThreatViolation,
    proposal_moves,
    validate_proposal,
)
from agentic_rogue_like.models import Enemy, MoveKind  # noqa: E402
from agentic_rogue_like.threat import threat  # noqa: E402


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


def _boar(hp: int, attack: int = 8, moves: list[MoveProposal] | None = None) -> MovesetProposal:
    return MovesetProposal(
        name="Chrome Boar",
        description="A cybernetic boar with hydraulic tusks.",
        hp=hp,
        attack=attack,
        attack_name="Hydraulic Gore",
        moves=moves
        or [
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
    # The auto-correction (see test_too_dangerous_proposal_is_corrected_without_retry)
    # only kicks in when the fitting HP is inside hp_bounds(). Here it is not:
    # attack at the budget's floor and feeble moves make the threat far too
    # weak, so the HP that would center it is way above the bounds - the error
    # goes back to the model for a retry instead of being retuned silently.
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    budget = budget_for(floor=0, num_floors=8, elite=False, boss=False)
    feeble = [
        MoveProposal(kind=MoveKind.ATTACK, name="Nibble", weight=1, power=60),
        MoveProposal(kind=MoveKind.DEFEND, name="Cower", weight=1, power=60),
    ]
    proposal = _boar(hp=40, attack=budget.min_attack, moves=feeble)
    value = threat(
        Enemy(
            id="",
            name="",
            hp=proposal.hp,
            attack=proposal.attack,
            attack_name="",
            moves=proposal_moves(proposal),
        )
    )
    low, high = budget.threat_range()
    fitting_hp = round(proposal.hp * ((low + high) / 2) / value)
    low_hp, high_hp = budget.hp_bounds()

    # Only the threat is off (attack and hp are inside their bounds), the
    # threat is below the range, and no HP inside hp_bounds() could fix it.
    assert low_hp <= proposal.hp <= high_hp
    assert budget.min_attack <= proposal.attack <= budget.max_attack
    assert value < low
    assert fitting_hp > high_hp

    model = _Recording(proposal, _boar(hp=30))
    with patch.object(encounter_agent, "_model", return_value=model):
        enemy = encounter_agent.generate_balanced_enemy(
            enemy_id="e", floor=0, num_floors=8, elite=False, boss=False
        )

    assert len(model.prompts) == 2
    assert "previous attempt was rejected: threat" in model.prompts[1]
    # The retry gets the original violation message, word-for-word what a
    # correctable threat violation says (see validate_proposal): the suggested
    # HP is out of range here, so the part the model can act on is "make the
    # moves stronger".
    assert (
        f"Change hp to about {fitting_hp}, or make the moves stronger" in model.prompts[1]
    )
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


def test_too_dangerous_proposal_is_corrected_without_retry(monkeypatch) -> None:
    # A threat violation with a fitting HP inside hp_bounds() is retuned by
    # validate_budget itself - the model is asked exactly once, and the enemy
    # that comes out balances just like one that was valid all along.
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    budget = budget_for(floor=0, num_floors=8, elite=False, boss=False)
    fake = _Recording(_boar(hp=55))  # threatens 11.7 - over the budget's range
    with patch.object(encounter_agent, "_model", return_value=fake):
        enemy = encounter_agent.generate_balanced_enemy(
            enemy_id="e", floor=0, num_floors=8, elite=False, boss=False
        )

    low_hp, high_hp = budget.hp_bounds()
    low, high = budget.threat_range()
    assert len(fake.prompts) == 1
    assert enemy.hp != 55
    assert low_hp <= enemy.hp <= high_hp
    assert low <= threat(enemy) <= high


# The two HPs depend on DEFAULT_MODEL (threat.py): under the current fit
# 40-55 is fixable, 56-61 rescales inside hp_bounds but misses the floor.
@pytest.mark.parametrize("hp,fixable", [(50, True), (60, False)])
def test_the_rescaled_hp_is_checked_again_once(hp: int, fixable: bool) -> None:
    """An infection prices its Malware by how long the fight lasts, and how long
    it lasts is decided by the enemy's own HP - so an infect move set's threat
    is not exactly proportional to HP, and the HP validate_budget rescales to
    has to clear validate_proposal again before it counts. Checked once, never
    iterated: where the rescaled HP misses (hp=60 - the HP that would center
    this threat leaves it just under the budget's floor), the original error
    goes to the retry and the model's own proposal stands."""
    from agentic_rogue_like.agent.budgets import _BUDGETS

    budget = _BUDGETS["mid"]  # hp 48-60, attack 9-12
    low_hp, high_hp = budget.hp_bounds()
    low, high = budget.threat_range()
    infection = [
        MoveProposal(kind=MoveKind.ATTACK, name="Hydraulic Gore", weight=3, power=100),
        MoveProposal(kind=MoveKind.INFECT, name="Rivet Plague", weight=3, power=50, stacks=6),
    ]
    proposal = _boar(hp=hp, attack=10, moves=infection)

    def score(candidate) -> float:
        return threat(
            Enemy(
                id="",
                name="",
                hp=candidate.hp,
                attack=candidate.attack,
                attack_name="",
                moves=proposal_moves(candidate),
            )
        )

    fitting_hp = round(hp * ((low + high) / 2) / score(proposal))
    # Both cases do reach the correction: only the threat is off, and the HP
    # that would center it is one this budget allows at all.
    assert low_hp <= fitting_hp <= high_hp
    with pytest.raises(ThreatViolation) as exc_info:
        validate_proposal(proposal, budget)
    assert (low <= score(proposal.model_copy(update={"hp": fitting_hp})) <= high) is fixable

    result = encounter_agent.validate_budget(
        {
            "budget": budget,
            "setting": "cyberpunk",
            "attempt": 1,
            "last_error": None,
            "proposal": proposal,
        }
    )

    # Either way validate_budget did not send the proposal back for another try.
    assert result["attempt"] == 1
    if fixable:
        assert result["last_error"] is None
        # The corrected proposal, and nothing else about it changed.
        assert result["proposal"] == proposal.model_copy(update={"hp": fitting_hp})
    else:
        error = str(exc_info.value)
        assert result["last_error"] == error
        assert f"too dangerous for this floor. Change hp to about {fitting_hp}" in error
        assert result["proposal"].hp == hp  # still what the model proposed


def test_attack_over_limit_still_retries(monkeypatch) -> None:
    # An attack outside the hard bound is not fixable by retuning HP - it
    # stays the old retry path, error message and all, and the corrected
    # second proposal is what comes back out.
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    budget = budget_for(floor=0, num_floors=8, elite=False, boss=False)
    fake = _Recording(_boar(hp=30, attack=budget.max_attack + 1), _boar(hp=40))
    with patch.object(encounter_agent, "_model", return_value=fake):
        enemy = encounter_agent.generate_balanced_enemy(
            enemy_id="e", floor=0, num_floors=8, elite=False, boss=False
        )

    assert len(fake.prompts) == 2
    assert f"attack {budget.max_attack + 1} outside budget" in fake.prompts[1]
    assert (enemy.hp, enemy.attack) == (40, 8)
