from unittest.mock import patch

import pytest

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.encounter_schema import BudgetViolation, EnemyBudget, EnemyProposal


class _AlwaysOverpowered:
    def with_structured_output(self, schema):
        return self

    def invoke(self, prompt):
        return EnemyProposal(
            name="Overpowered Thing", description="Too strong.", hp=999, attack=999
        )


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
