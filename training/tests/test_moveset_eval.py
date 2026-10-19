"""The move set eval end to end - graph, harness, metrics, report - against a
scripted model instead of Groq, so it runs without a key or network."""

import json

import pytest
from agentic_rogue_like.agent.encounter_schema import (
    EnemyProposal,
    MoveProposal,
    MovesetProposal,
)
from agentic_rogue_like.models import MoveKind

from eval import report as report_module
from eval.harness import measure_cost_samples, run_harness, violation_kind
from eval.metrics import compute_report
from eval.testset import build_test_contexts


def _boar(hp: int, attack: int = 10, kinds=(MoveKind.ATTACK, MoveKind.BARRAGE)) -> MovesetProposal:
    moves = [
        MoveProposal(
            kind=kind,
            name=f"{kind.value.title()} Move",
            weight=2,
            power=35 if kind is MoveKind.BARRAGE else 100,
            hits=3 if kind is MoveKind.BARRAGE else None,
        )
        for kind in kinds
    ]
    return MovesetProposal(
        name="Chrome Boar", description="d", hp=hp, attack=attack, attack_name="Gore", moves=moves
    )


class _Scripted:
    """Answers each call from `answer(schema, prompt, call_index)`."""

    def __init__(self, answer):
        self.answer, self.calls, self.schemas = answer, 0, []

    def __call__(self):  # the harness takes a model *factory*
        return self

    def with_structured_output(self, schema, include_raw=False):
        self.schemas.append(schema)
        self.include_raw = include_raw
        return self

    def invoke(self, prompt):
        self.calls += 1
        proposal = self.answer(self.schemas[-1], prompt, self.calls)
        if self.include_raw:
            return {"parsed": proposal, "raw": _Usage()}
        return proposal


class _Usage:
    usage_metadata = {"input_tokens": 500, "output_tokens": 200}


def _plain_for(prompt: str) -> EnemyProposal:
    # Bosses: the plain prompt names its hp and attack ranges.
    hp = int(prompt.split("hp between ")[1].split(" ")[0])
    attack = int(prompt.split("attack between ")[1].split(" ")[0])
    return EnemyProposal(name="Boss", description="d", hp=hp, attack=attack, attack_name="a")


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("threat 23.8 outside budget [8.7, 17.5] - too dangerous", "threat"),
        ("invalid move set: a move set needs an attack or a barrage", "invalid_moves"),
        ("hp 200 outside the allowed range [24, 90]", "hp"),
        ("hp 999 outside budget [48, 60]", "hp"),
        ("attack 99 outside budget [9, 12]", "attack"),
        (None, None),
    ],
)
def test_violation_kinds(message, kind) -> None:
    assert violation_kind(message) == kind


def test_moves_flag_reaches_contexts_but_never_bosses() -> None:
    contexts = build_test_contexts(repeats=1, settings=("dungeon",), with_moves=True)
    assert {c.tier: c.with_moves for c in contexts} == {
        "early": True,
        "mid": True,
        "elite": True,
        "boss": False,
    }
    assert not any(c.with_moves for c in build_test_contexts(repeats=1, settings=("dungeon",)))


def test_move_set_run_end_to_end(tmp_path, monkeypatch) -> None:
    def answer(schema, prompt, call):
        if schema is EnemyProposal:
            return _plain_for(prompt)
        attack = int(prompt.split("must be between ")[1].split(" ")[0])
        plain_low = int(prompt.split("hp between ")[1].split(" ")[0])
        # Like a model that learns from feedback: take the suggested hp,
        # after any other rejection fall back to the plain range, and start
        # every other enemy with an absurd hp.
        if "Change hp to about" in prompt:
            return _boar(hp=int(prompt.split("hp to about ")[1].split(",")[0]), attack=attack)
        if "rejected" in prompt or call % 2 == 0:
            return _boar(hp=plain_low, attack=attack)
        return _boar(hp=500, attack=attack)

    model = _Scripted(answer)
    contexts = build_test_contexts(repeats=2, settings=("cyberpunk",), with_moves=True)
    results = run_harness(contexts, model_factory=model)
    report = compute_report(
        "test-moves", "scripted", results, measure_cost_samples(contexts, model)
    )

    assert all(r.status == "ok" for r in results)
    moved = [t for t in report.by_tier if t.tier != "boss"]
    boss = next(t for t in report.by_tier if t.tier == "boss")
    for tier in moved:
        assert tier.avg_moves == 2
        assert tier.uses_barrage == 1 and tier.uses_purge == 0
        assert tier.unique_move_set_ratio == 0.5  # 2 identical move sets
        assert 0 <= tier.threat_position_mean <= 1
    assert boss.avg_moves is None  # plain schema, no move columns
    # The first-try breakdown sees the rejections the retries then fixed.
    assert report.overall.budget_compliance_first_attempt < 1
    assert report.overall.first_violation_hp + report.overall.first_violation_threat > 0
    assert report.overall.retry_fix_rate == 1

    # Report round trip: the markdown gets its move set table, the raw JSON
    # loads back into move set proposals.
    monkeypatch.setattr(report_module, "REPORTS_DIR", tmp_path)
    path = report_module.save_report(report, results)
    assert "## Move sets" in path.read_text()
    reloaded = report_module.load_previous_results("test-moves")
    assert [type(r.proposal) for r in reloaded] == [type(r.proposal) for r in results]
    assert reloaded[0].first_violation_kind == results[0].first_violation_kind
    assert json.loads((tmp_path / "test-moves.json").read_text())[0]["context"]["with_moves"]


def test_plain_run_keeps_the_plain_schema_and_report() -> None:
    model = _Scripted(lambda schema, prompt, call: _plain_for(prompt))
    contexts = build_test_contexts(repeats=1, settings=("dungeon",))
    results = run_harness(contexts, model_factory=model)
    report = compute_report("plain", "scripted", results, [])

    assert set(model.schemas) == {EnemyProposal}
    assert report.overall.avg_moves is None
    assert "## Move sets" not in report_module.render_markdown(report)


def test_reports_from_before_move_sets_still_load(tmp_path, monkeypatch) -> None:
    old = {
        "context": {
            "tier": "mid",
            "floor": 5,
            "num_floors": 8,
            "elite": False,
            "boss": False,
            "setting": "dungeon",
            "budget": {"min_hp": 48, "max_hp": 60, "min_attack": 9, "max_attack": 12},
        },
        "status": "ok",
        "attempts_used": 1,
        "first_attempt_violation": False,
        "latency_seconds": 1.0,
        "proposal": {"name": "B", "description": "d", "hp": 50, "attack": 10, "attack_name": "a"},
        "error_message": None,
    }
    monkeypatch.setattr(report_module, "REPORTS_DIR", tmp_path)
    (tmp_path / "old.json").write_text(json.dumps([old]))

    [result] = report_module.load_previous_results("old")

    assert type(result.proposal) is EnemyProposal
    assert result.context.with_moves is False
