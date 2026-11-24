import json
import random
from pathlib import Path

import pytest

from agentic_rogue_like.balance_sim import (
    TIERS,
    FightResult,
    SimConfig,
    TierStats,
    build_report,
    fight,
    load_variant,
    main,
    naive_bot,
    playable,
    smart_bot,
)
from agentic_rogue_like.combat import free_slots as combat_free_slots
from agentic_rogue_like.combat import play_card
from agentic_rogue_like.models import Enemy


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


def test_difficulty_lowers_win_rate() -> None:
    base = build_report(SimConfig(), naive_bot, fights=10, runs=10, seed=1234, bot_name="naive")
    hard = build_report(
        SimConfig(difficulty=5), naive_bot, fights=10, runs=10, seed=1234, bot_name="naive"
    )
    base_rate = sum(base.fresh[t].win_rate for t in TIERS)
    hard_rate = sum(hard.fresh[t].win_rate for t in TIERS)
    assert hard_rate <= base_rate


def test_main_accepts_difficulty() -> None:
    main(["--difficulty", "2", "--fights", "2", "--runs", "2", "--seed", "1234"])


# --------------------------------------------------------------- decisions (E1)


def _dummy() -> Enemy:
    # never dies within the fight cap and barely hurts: every turn counts
    return Enemy(id="dummy", name="Dummy", hp=5000, attack=1, attack_name="Hit")


def _play_first(state, player, rng, limit: int | None) -> None:
    played = 0
    while limit is None or played < limit:
        idx = next((i for i, c in enumerate(state.hand) if playable(state, c)), None)
        if idx is None:
            return
        play_card(state, idx, combat_free_slots(state, state.hand[idx])[0], player, rng)
        played += 1


def test_a_card_left_in_hand_counts_as_a_turn_with_leftover() -> None:
    # The bot can only lay one card a turn, though it starts with more.
    result = fight(
        SimConfig().new_player(),
        _dummy(),
        "early",
        lambda s, p, r: _play_first(s, p, r, limit=1),
        random.Random(3),
    )
    assert result.turns_with_leftover > 0
    assert result.turns_all_played == 0


def test_playing_every_playable_card_counts_as_all_played() -> None:
    result = fight(
        SimConfig().new_player(),
        _dummy(),
        "early",
        lambda s, p, r: _play_first(s, p, r, limit=None),
        random.Random(3),
    )
    # once the field fills up, a card that is still in hand is no longer
    # playable - but it was at the start of the turn, so it counts as left
    assert result.turns_all_played > 0
    assert result.turns_all_played + result.turns_with_leftover <= result.turns


def test_tier_stats_share_the_counted_turns() -> None:
    stats = TierStats.of(
        [
            FightResult("mid", True, 4, 3, turns_all_played=1, turns_with_leftover=3),
            FightResult("mid", False, 2, 9, turns_all_played=0, turns_with_leftover=0),
        ]
    )
    assert stats.all_played == pytest.approx(0.25)
    assert stats.leftover == pytest.approx(0.75)
    assert TierStats.of([FightResult("mid", True, 1, 0)]).all_played is None


# Recorded on the code before the decision metric was added (smart bot,
# seed 4242): measuring it must not draw a random number or change a fight.
REFERENCE_SMART_FRESH = {
    "early": (1.0, 3.066666666666667, 10.4),
    "mid": (1.0, 6.133333333333334, 19.4),
    "elite": (0.8666666666666667, 5.733333333333333, 32.8),
    "boss": (0.26666666666666666, 7.666666666666667, 43.733333333333334),
}
REFERENCE_SMART_IN_RUN = {"early": 0.9444444444444444, "mid": 0.5, "elite": 0.75, "boss": 0.0}


def test_decision_metric_leaves_the_smart_bot_results_unchanged() -> None:
    report = build_report(SimConfig(), smart_bot, fights=15, runs=8, seed=4242)
    for tier in TIERS:
        fresh = report.fresh[tier]
        assert (fresh.win_rate, fresh.turns, fresh.hp_lost) == pytest.approx(
            REFERENCE_SMART_FRESH[tier]
        )
        assert report.in_run[tier].win_rate == pytest.approx(REFERENCE_SMART_IN_RUN[tier])
        assert fresh.all_played is not None
        assert fresh.all_played + fresh.leftover == pytest.approx(1)
    assert report.run_win_rate == 0.0
