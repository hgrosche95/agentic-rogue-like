"""act_pack: one simulated model answer for a whole act, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentic_rogue_like.agent import act_pack, usage
from agentic_rogue_like.agent.budgets import tier_budget
from agentic_rogue_like.agent.encounter_schema import (
    MoveProposal,
    MovesetProposal,
    ThreatViolation,
    validate_proposal,
)
from agentic_rogue_like.models import Enemy, MoveKind
from agentic_rogue_like.threat import threat


class _Scripted:
    """Answers with one ActPackProposal in the include_raw=True shape
    usage.invoke_structured calls, and records what it was asked."""

    def __init__(self, proposal: act_pack.ActPackProposal) -> None:
        self.proposal = proposal
        self.schemas: list[type] = []
        self.prompts: list[str] = []

    def with_structured_output(self, schema, include_raw: bool = False):
        self.schemas.append(schema)
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return {
            "raw": SimpleNamespace(usage_metadata={"input_tokens": 900, "output_tokens": 4000}),
            "parsed": self.proposal,
            "parsing_error": None,
        }


_STANDARD = [
    MoveProposal(kind=MoveKind.ATTACK, name="Data Spike", weight=3, power=100),
    MoveProposal(kind=MoveKind.DEFEND, name="Firewall", weight=2, power=100),
]


def _entry(name: str, tier: str, moves: list[MoveProposal] | None = None, hp: int | None = None):
    """An entry in the middle of its tier's budget - inside it with the
    standard moves (the tests assert that where it matters)."""
    budget = tier_budget(tier)
    return MovesetProposal(
        name=name,
        description="A rogue process in the city grid.",
        hp=hp if hp is not None else (budget.min_hp + budget.max_hp) // 2,
        attack=(budget.min_attack + budget.max_attack) // 2,
        attack_name="Data Spike",
        moves=moves or _STANDARD,
    )


def _full_act(tiers=("early", "mid", "elite")) -> act_pack.ActPackProposal:
    return act_pack.ActPackProposal(
        **{
            tier: [_entry(f"{tier} {i}", tier) for i in range(act_pack.TIER_COUNTS[tier])]
            for tier in tiers
        }
    )


@pytest.fixture(autouse=True)
def _fresh_usage(monkeypatch):
    monkeypatch.setattr(usage, "_totals", {})


def _run(monkeypatch, proposal, act: int = 1) -> tuple[act_pack.ActPack, _Scripted]:
    model = _Scripted(proposal)
    monkeypatch.setattr(act_pack, "_model", lambda: model)
    return act_pack.generate_act_pack("cyberpunk", act), model


def test_valid_entries_land_in_their_tier_from_one_call(monkeypatch) -> None:
    pack, model = _run(monkeypatch, _full_act())

    assert [e.name for e in pack.early] == [f"early {i}" for i in range(4)]
    assert [e.name for e in pack.mid] == [f"mid {i}" for i in range(4)]
    assert [e.name for e in pack.elite] == [f"elite {i}" for i in range(3)]
    for tier in ("early", "mid", "elite"):
        for enemy in getattr(pack, tier):
            assert isinstance(enemy, Enemy)
            assert [m.name for m in enemy.moves] == ["Data Spike", "Firewall"]
            low, high = tier_budget(tier).threat_range()
            assert low <= threat(enemy) <= high
    assert len({e.id for e in pack.early + pack.mid + pack.elite}) == 11

    # One model call for the whole act, counted under its own purpose.
    assert model.schemas == [act_pack.ActPackProposal]
    assert usage.totals() == {"act_pack": {"calls": 1, "input_tokens": 900, "output_tokens": 4000}}


def test_prompt_carries_every_tier_budget_and_the_variety_rules(monkeypatch) -> None:
    _, model = _run(monkeypatch, _full_act())
    (prompt,) = model.prompts

    for tier in ("early", "mid", "elite"):
        budget = tier_budget(tier)
        assert (
            f"For the {tier} enemies: attack is its base strength and must be between "
            f"{budget.min_attack} and {budget.max_attack}"
        ) in prompt
    assert "4 early, 4 mid, 3 elite" in prompt
    assert "strong defend" in prompt and "purge or a lock" in prompt and "infect" in prompt
    assert "at least one attack or barrage" in prompt


def test_an_entry_over_its_budget_is_repaired_through_its_hp(monkeypatch) -> None:
    budget = tier_budget("mid")
    # Power 160 at the tier's middle HP: too dangerous, but an HP inside
    # hp_bounds prices it right (at 200 none would, and it would be dropped).
    heavy = [MoveProposal(kind=MoveKind.ATTACK, name="Overclocked Ram", weight=3, power=160)]
    heavy.append(MoveProposal(kind=MoveKind.DEFEND, name="Firewall", weight=1, power=100))
    too_dangerous = _entry("Bruiser", "mid", moves=heavy)
    with pytest.raises(ThreatViolation):
        validate_proposal(too_dangerous, budget)

    proposal = _full_act()
    proposal.mid[0] = too_dangerous
    pack, model = _run(monkeypatch, proposal)

    assert len(model.prompts) == 1  # repaired, not asked for again
    bruiser = pack.mid[0]
    assert bruiser.name == "Bruiser"
    assert bruiser.hp < too_dangerous.hp
    low, high = budget.threat_range()
    assert low <= threat(bruiser) <= high
    assert len(pack.mid) == 4


def test_an_entry_without_an_attack_move_is_dropped(monkeypatch) -> None:
    no_attack = [
        MoveProposal(kind=MoveKind.DEFEND, name="Firewall", weight=2, power=100),
        MoveProposal(kind=MoveKind.LOCK, name="Port Lock", weight=2, power=50),
    ]
    proposal = _full_act()
    proposal.elite[1] = _entry("Turtle", "elite", moves=no_attack)
    pack, model = _run(monkeypatch, proposal)

    assert len(model.prompts) == 1  # dropped, not asked for again
    assert [e.name for e in pack.elite] == ["elite 0", "elite 2"]
    assert len(pack.early) == 4 and len(pack.mid) == 4


def test_act_two_has_no_early_tier(monkeypatch) -> None:
    # Early entries the model sends anyway are ignored.
    pack, model = _run(monkeypatch, _full_act(), act=2)

    assert pack.early == []
    assert len(pack.mid) == 4 and len(pack.elite) == 3
    (prompt,) = model.prompts
    assert "act 2" in prompt and "4 mid, 3 elite" in prompt
    assert "For the early enemies" not in prompt


def test_extra_entries_are_cut_to_the_tier_count(monkeypatch) -> None:
    proposal = _full_act()
    proposal.elite.append(_entry("elite 3", "elite"))
    pack, _ = _run(monkeypatch, proposal)

    assert [e.name for e in pack.elite] == ["elite 0", "elite 1", "elite 2"]


def test_act_must_be_positive() -> None:
    with pytest.raises(ValueError):
        act_pack.tiers_for(0)
