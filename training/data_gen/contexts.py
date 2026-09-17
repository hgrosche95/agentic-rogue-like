"""Contexts to generate training examples from - wider than eval/testset.py's
on purpose: the fine-tuned model has to handle whatever a player types as a
custom setting (models.py caps it at 40 chars, but doesn't limit content),
not just the 5 curated SETTING_PRESETS.

Split at the *setting* level, applied identically across all 4 tiers: every
setting is entirely train, entirely val, or entirely test, so no (tier,
setting) combination straddles a split boundary and leaks near-duplicate
examples across it.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.budgets import budget_for
from agentic_rogue_like.agent.encounter_schema import EnemyBudget
from agentic_rogue_like.models import SETTING_PRESETS

# Hand-picked, not generated - plausible free-text settings a player might
# type, covering genres the 5 presets don't (sci-fi minus cyberpunk, historical,
# whimsical, post-apocalyptic, ...) so the model isn't only ever trained on
# "dungeon"/"cyberpunk"/"alien planet"/"pirate seas"/"haunted carnival".
_CUSTOM_SETTINGS: tuple[str, ...] = (
    "steampunk airship",
    "underwater ruins",
    "frozen tundra",
    "post-apocalyptic city",
    "clockwork kingdom",
    "desert wasteland",
    "space station",
    "feudal Japan",
    "candy kingdom",
    "swamp witch coven",
)

ALL_SETTINGS: tuple[str, ...] = (*SETTING_PRESETS, *_CUSTOM_SETTINGS)

_NUM_FLOORS = 8
_TIERS: tuple[tuple[str, int, bool, bool], ...] = (
    ("early", 1, False, False),
    ("mid", 5, False, False),
    ("elite", 5, True, False),
    ("boss", 7, False, True),
)

# 11 train / 2 val / 2 test settings, applied to every tier. Order is fixed
# (presets first, in declared order) so the split is deterministic and
# reviewable - not a random shuffle that changes on every run.
_SPLIT_SETTINGS: dict[str, tuple[str, ...]] = {
    "train": ALL_SETTINGS[:11],
    "val": ALL_SETTINGS[11:13],
    "test": ALL_SETTINGS[13:15],
}


@dataclass(frozen=True)
class DataContext:
    tier: str
    floor: int
    num_floors: int
    elite: bool
    boss: bool
    setting: str
    budget: EnemyBudget
    split: str
    # Which repeat this is within its (tier, setting) bucket - identifies a
    # context uniquely across resumed runs, so a resumed run can tell "this
    # exact repeat is already in raw_results.jsonl" from "it isn't yet".
    repeat_index: int


def build_data_contexts(repeats: int = 10) -> list[DataContext]:
    contexts = []
    for tier, floor, elite, boss in _TIERS:
        budget = budget_for(floor=floor, num_floors=_NUM_FLOORS, elite=elite, boss=boss)
        for split, settings in _SPLIT_SETTINGS.items():
            for setting in settings:
                for repeat_index in range(repeats):
                    contexts.append(
                        DataContext(
                            tier=tier,
                            floor=floor,
                            num_floors=_NUM_FLOORS,
                            elite=elite,
                            boss=boss,
                            setting=setting,
                            budget=budget,
                            split=split,
                            repeat_index=repeat_index,
                        )
                    )
    return contexts


def to_encounter_state(context: DataContext) -> encounter_agent.EncounterState:
    """The single-attempt, no-prior-error state _build_prompt() expects -
    shared so generate.py and dataset.py build the exact same prompt text."""
    return {
        "budget": context.budget,
        "setting": context.setting,
        "attempt": 0,
        "last_error": None,
        "proposal": None,
    }
