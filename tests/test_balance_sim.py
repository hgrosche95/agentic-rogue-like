import json
from pathlib import Path

import pytest

from agentic_rogue_like.balance_sim import (
    TIERS,
    SimConfig,
    build_report,
    load_variant,
    naive_bot,
    smart_bot,
)


def test_report_covers_every_tier_and_is_deterministic() -> None:
    first = build_report(SimConfig(), smart_bot, fights=20, runs=20, seed=7)
    second = build_report(SimConfig(), smart_bot, fights=20, runs=20, seed=7)
    assert first == second
    assert all(first.fresh[t] is not None for t in TIERS)
    assert 0.0 <= first.run_win_rate <= 1.0


# Recorded on the code before the run statistics were added (naive bot, seed 1234).
REFERENCE_FRESH = {"early": 1.0, "mid": 0.7, "elite": 0.6, "boss": 0.0}
REFERENCE_IN_RUN = {"early": 0.84, "mid": 0.14285714285714285, "elite": 1.0, "boss": 1.0}
REFERENCE_RUN_WIN_RATE = 0.0


def test_win_rates_match_reference() -> None:
    report = build_report(SimConfig(), naive_bot, fights=10, runs=10, seed=1234, bot_name="naive")
    for tier in TIERS:
        assert report.fresh[tier].win_rate == pytest.approx(REFERENCE_FRESH[tier], abs=1e-9)
        assert report.in_run[tier].win_rate == pytest.approx(REFERENCE_IN_RUN[tier], abs=1e-9)
    assert report.run_win_rate == pytest.approx(REFERENCE_RUN_WIN_RATE, abs=1e-9)


def test_naive_bot_runs_too() -> None:
    report = build_report(SimConfig(), naive_bot, fights=10, runs=10, seed=3)
    assert report.fresh["early"].win_rate > 0


def test_variant_overrides_budgets_player_and_cards(tmp_path: Path) -> None:
    path = tmp_path / "v.json"
    path.write_text(
        json.dumps(
            {
                "budgets": {"boss": {"min_hp": 10, "max_hp": 10}},
                "player": {"hp": 80},
                "cards": {"Exploit": {"value": 9}},
                "extra_cards": [{"name": "Rootkit", "type": "attack", "value": 12}],
                "remove_cards": ["Prefetch"],
            }
        )
    )
    cfg = load_variant(path)
    assert cfg.budgets["boss"].max_hp == 10
    assert cfg.budgets["early"] == SimConfig().budgets["early"]
    player = cfg.new_player()
    assert player.hp == player.max_hp == 80
    names = [c.name for c in player.deck]
    assert "Rootkit" in names and "Prefetch" not in names
    assert all(c.value == 9 for c in player.deck if c.name == "Exploit")


def test_shipped_example_variants_load() -> None:
    for path in Path(__file__).parent.parent.joinpath("balance").glob("*.json"):
        load_variant(path).new_player()
