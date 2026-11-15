"""The content library (agent/library.py) in a temporary directory, no network."""

from __future__ import annotations

import json
import random

import pytest

from agentic_rogue_like.agent import act_pack, library, usage
from agentic_rogue_like.agent.budgets import tier_budget
from agentic_rogue_like.agent.encounter_schema import MoveProposal, MovesetProposal
from agentic_rogue_like.models import Enemy, EnemyMove, MoveKind

_MOVES = [
    EnemyMove(kind=MoveKind.ATTACK, name="Data Spike", weight=3, power=100),
    EnemyMove(kind=MoveKind.DEFEND, name="Firewall", weight=2, power=100),
]


def _enemy(name: str) -> Enemy:
    return Enemy(
        id="x",
        name=name,
        description="A rogue process.",
        hp=40,
        attack=9,
        attack_name="Data Spike",
        moves=_MOVES,
    )


@pytest.fixture
def library_file(tmp_path, monkeypatch):
    path = tmp_path / "content" / "library.json"
    monkeypatch.setenv(library.PATH_ENV, str(path))
    return path


def _stock(setting: str, per_tier: int, tiers=("early", "mid", "elite")) -> None:
    library.store(setting, {t: [_enemy(f"{t} {i}") for i in range(per_tier)] for t in tiers})


class _Roll(random.Random):
    """A Random whose random() always returns `value` - sample() stays real."""

    def __init__(self, value: float) -> None:
        super().__init__(3)
        self.value = value

    def random(self) -> float:
        return self.value

    # Overriding getrandbits too keeps sample() on its getrandbits path: with
    # only random() overridden it would draw through the constant above and
    # pick the same index forever.
    def getrandbits(self, k: int) -> int:
        return super().getrandbits(k)


class _NoModel:
    def with_structured_output(self, schema, include_raw: bool = False):
        raise AssertionError("the pack should have come from the library")


def _pack_answer() -> act_pack.ActPackProposal:
    def entry(tier: str, i: int) -> MovesetProposal:
        budget = tier_budget(tier)
        return MovesetProposal(
            name=f"Fresh {tier} {i}",
            description="Straight from the model.",
            hp=(budget.min_hp + budget.max_hp) // 2,
            attack=(budget.min_attack + budget.max_attack) // 2,
            attack_name="Data Spike",
            moves=[
                MoveProposal(kind=MoveKind.ATTACK, name="Data Spike", weight=3, power=100),
                MoveProposal(kind=MoveKind.DEFEND, name="Firewall", weight=2, power=100),
            ],
        )

    return act_pack.ActPackProposal(
        **{t: [entry(t, i) for i in range(n)] for t, n in act_pack.TIER_COUNTS.items()}
    )


class _Model:
    def __init__(self) -> None:
        self.calls = 0

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, prompt):
        self.calls += 1
        return {"raw": None, "parsed": _pack_answer(), "parsing_error": None}


@pytest.fixture(autouse=True)
def _fresh_usage(monkeypatch):
    monkeypatch.setattr(usage, "_totals", {})


def test_stored_enemies_read_back_under_the_normalized_setting(library_file) -> None:
    library.store("  CyberPunk ", {"mid": [_enemy("Grid Rat"), _enemy("Neon Wasp")]})

    shelves = library.entries("cyberpunk")
    assert [e.name for e in shelves["mid"]] == ["Grid Rat", "Neon Wasp"]
    assert shelves["mid"][0].moves == _MOVES
    assert library.entries("Cyberpunk") == shelves
    assert library.entries("steampunk") == {}
    # The file on disk: English keys, one shelf per setting and tier.
    raw = json.loads(library_file.read_text(encoding="utf-8"))
    assert list(raw["settings"]) == ["cyberpunk"]
    assert raw["settings"]["cyberpunk"]["mid"][0]["name"] == "Grid Rat"
    assert not list(library_file.parent.glob("*.tmp"))  # no temp file left behind


def test_a_shelf_keeps_the_newest_sixty(library_file) -> None:
    library.store("cyberpunk", {"early": [_enemy(f"Old {i}") for i in range(50)]})
    library.store("cyberpunk", {"early": [_enemy(f"New {i}") for i in range(20)]})

    names = [e.name for e in library.entries("cyberpunk")["early"]]
    assert len(names) == library.MAX_PER_TIER == 60
    assert names[0] == "Old 10"  # the ten oldest fell out
    assert names[-1] == "New 19"


def test_a_stocked_library_serves_a_pack_without_a_model_call(library_file, monkeypatch) -> None:
    _stock("cyberpunk", act_pack.LIBRARY_MINIMUM)
    monkeypatch.setattr(act_pack, "_model", lambda: _NoModel())

    pack = act_pack.generate_act_pack("Cyberpunk", 1, rng=_Roll(0.1))

    assert [len(pack.early), len(pack.mid), len(pack.elite)] == [4, 4, 3]
    assert all(e.name.startswith("early ") for e in pack.early)
    assert len({e.name for e in pack.mid}) == 4  # distinct, not one enemy four times
    assert len({e.id for e in pack.early + pack.mid + pack.elite}) == 11
    assert usage.totals() == {}  # no call counted


def test_the_other_half_of_the_time_the_model_is_asked(library_file, monkeypatch) -> None:
    _stock("cyberpunk", act_pack.LIBRARY_MINIMUM)
    model = _Model()
    monkeypatch.setattr(act_pack, "_model", lambda: model)

    pack = act_pack.generate_act_pack("cyberpunk", 1, rng=_Roll(0.7))

    assert model.calls == 1
    assert pack.mid[0].name == "Fresh mid 0"
    # ...and its enemies join the library.
    assert library.entries("cyberpunk")["mid"][-1].name == "Fresh mid 3"


def test_a_thin_library_never_replaces_the_model(library_file, monkeypatch) -> None:
    # Act 1 needs early too: plenty of mid and elite doesn't do.
    _stock("cyberpunk", 30, tiers=("mid", "elite"))
    model = _Model()
    monkeypatch.setattr(act_pack, "_model", lambda: model)

    act_pack.generate_act_pack("cyberpunk", 1, rng=_Roll(0.0))
    assert model.calls == 1

    # Act 2 has no early tier - the same library serves it.
    monkeypatch.setattr(act_pack, "_model", lambda: _NoModel())
    pack = act_pack.generate_act_pack("cyberpunk", 2, rng=_Roll(0.0))
    assert pack.early == [] and len(pack.mid) == 4 and len(pack.elite) == 3


def test_a_broken_file_is_an_empty_library(library_file) -> None:
    library_file.parent.mkdir(parents=True)
    for broken in ("{not json", '{"settings": [1, 2]}', '{"settings": {"x": {"mid": [{}]}}}'):
        library_file.write_text(broken, encoding="utf-8")
        assert library.entries("x") == {}
        assert library.draw("x", {"mid": 1}, 1, random.Random(0)) is None

    # The next write replaces it.
    library.store("x", {"mid": [_enemy("Fresh Start")]})
    assert [e.name for e in library.entries("x")["mid"]] == ["Fresh Start"]


def test_without_the_variable_the_library_is_off(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(library.PATH_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    library.store("cyberpunk", {"mid": [_enemy("Grid Rat")]})

    assert library.entries("cyberpunk") == {}
    assert list(tmp_path.iterdir()) == []
