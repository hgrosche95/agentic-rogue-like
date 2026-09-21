"""The held-out set of (floor tier, setting) contexts every model is evaluated on.

Mirrors budget_for()'s own branching (agent/budgets.py) instead of picking
arbitrary floor numbers, so "early"/"mid" here are guaranteed to route through
the same budget the real game would pick - and SETTING_PRESETS instead of
made-up strings, so the diversity metric reflects prompts players actually see.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_rogue_like.agent.budgets import budget_for
from agentic_rogue_like.agent.encounter_schema import EnemyBudget
from agentic_rogue_like.models import SETTING_PRESETS

# num_floors=8 is what the existing encounter-agent tests use; early is
# floor < num_floors // 2 (=4) and mid is floor >= 4, per budget_for().
_NUM_FLOORS = 8
_TIERS: tuple[tuple[str, int, bool, bool], ...] = (
    ("early", 1, False, False),
    ("mid", 5, False, False),
    ("elite", 5, True, False),
    ("boss", 7, False, True),
)


@dataclass(frozen=True)
class EvalContext:
    tier: str
    floor: int
    num_floors: int
    elite: bool
    boss: bool
    setting: str
    budget: EnemyBudget


def build_test_contexts(
    repeats: int = 5,
    settings: tuple[str, ...] = SETTING_PRESETS,
    tiers: tuple[str, ...] | None = None,
) -> list[EvalContext]:
    """One EvalContext per (tier, setting), repeated `repeats` times.

    Repeats matter here in a way a single sample can't cover: budget
    compliance and diversity are rates/distributions, not pass/fail - one
    generation per context would only ever show "compliant" or "not", never
    how often either happens.

    `settings` defaults to the presets (what the Groq baseline was measured
    on). Note those all sit in the fine-tuning *train* split, so a fine-tuned
    model scored on them is scored on prompts it memorized - pass
    data_gen.contexts.TEST_SETTINGS to measure generalization instead.

    `tiers` restricts the run to some budget tiers (default: all four) - used to
    fill a gap in an existing report (results merge by label) without spending
    quota re-measuring tiers that are already covered.
    """
    contexts = []
    for tier, floor, elite, boss in _TIERS:
        if tiers is not None and tier not in tiers:
            continue
        budget = budget_for(floor=floor, num_floors=_NUM_FLOORS, elite=elite, boss=boss)
        for setting in settings:
            for _ in range(repeats):
                contexts.append(
                    EvalContext(
                        tier=tier,
                        floor=floor,
                        num_floors=_NUM_FLOORS,
                        elite=elite,
                        boss=boss,
                        setting=setting,
                        budget=budget,
                    )
                )
    return contexts
