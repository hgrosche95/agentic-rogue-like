"""One LLM call for all of an act's regular enemies, instead of one per room.

generate_act_pack(setting, act) asks for the whole act at once - 4 early,
4 mid and 3 elite enemies (act 2 has no early tier, see enemies.tier_floor) -
under the same rules and budgets the encounter agent's move set prompt uses
for a single enemy (encounter_agent.MOVESET_*). On top of that the prompt asks
for an act whose enemies belong together and fight differently.

There is no retry loop: every entry is checked on its own with
validate_proposal and repaired through its HP exactly like the encounter
agent's validate_budget does (encounter_agent.fit_to_budget). An entry that
can't be repaired is dropped, never asked for again - one call is the point,
and a pack a few enemies short is still a pack.

Bosses are not part of the pack: their move set is fixed and they keep coming
from the encounter agent / static pool.

With the content library on (agent/library.py), every valid pack's enemies
are stored there, and a setting whose library holds at least LIBRARY_MINIMUM
enemies in every tier the act needs is served from it LIBRARY_CHANCE of the
time - no model call at all.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from pydantic import BaseModel, Field

from ..models import DEFAULT_SETTING, Enemy
from . import library, usage
from .budgets import tier_budget
from .encounter_agent import (
    MOVESET_MOVE_RULES,
    MOVESET_NAME_RULES,
    fit_to_budget,
    moveset_budget_rules,
)
from .encounter_schema import BudgetViolation, MovesetProposal, proposal_moves

logger = logging.getLogger(__name__)

# How many enemies the pack asks for per tier.
TIER_COUNTS: dict[str, int] = {"early": 4, "mid": 4, "elite": 3}

# One call writes eleven enemies, so it gets more time than a single
# encounter call (encounter_agent.REQUEST_TIMEOUT_SECONDS).
REQUEST_TIMEOUT_SECONDS = 60.0

# When a pack may come from the content library instead of the model: every
# tier the act needs holds at least this many enemies there, and then only
# this share of the time - the library grows only from fresh packs.
LIBRARY_MINIMUM = 12
LIBRARY_CHANCE = 0.5


class ActPackProposal(BaseModel):
    """What the LLM's tool call must produce: every tier's enemies.

    The counts are asked for in the prompt, not enforced here: Groq rejects a
    tool call outside the schema before any of it can be used, and a pack with
    one enemy too few is better than none. Extra entries are cut off in
    generate_act_pack.
    """

    early: list[MovesetProposal] = Field(
        default_factory=list,
        description="The early-floor enemies (4). Leave empty in act 2.",
    )
    mid: list[MovesetProposal] = Field(
        default_factory=list, description="The mid-floor enemies (4)."
    )
    elite: list[MovesetProposal] = Field(default_factory=list, description="The elites (3).")


class ActPack(BaseModel):
    """An act's finished enemies per tier, ready for combat."""

    act: int
    setting: str
    early: list[Enemy] = Field(default_factory=list)
    mid: list[Enemy] = Field(default_factory=list)
    elite: list[Enemy] = Field(default_factory=list)


def tiers_for(act: int) -> list[str]:
    """The tiers an act's pack holds: act 2 on has no early tier - its fights
    pick up where act 1's second half left off (enemies.tier_floor)."""
    if act < 1:
        raise ValueError(f"act must be >= 1, got {act}")
    return ["early", "mid", "elite"] if act == 1 else ["mid", "elite"]


def _model() -> Any:
    # Groq only: the fine-tuned Ollama model (ENCOUNTER_AGENT_MODEL_SOURCE)
    # was trained on the plain single-enemy schema and has never seen a move
    # set, let alone a whole act. Imported lazily like encounter_agent._model.
    from langchain_groq import ChatGroq

    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.9,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def build_prompt(setting: str, act: int) -> str:
    tiers = tiers_for(act)
    counts = ", ".join(f"{TIER_COUNTS[tier]} {tier}" for tier in tiers)
    prompt = (
        f"Invent all regular enemies of act {act} of a {setting}-themed roguelike: "
        f"{counts}. Their names, descriptions, attack_names and move names must fit the "
        f"{setting} setting instead of generic dungeon fantasy. "
        f"The enemies of this act belong together - one place, one faction or one threat "
        f"they all share - but each fights clearly differently from the others in its tier. "
        f"In every tier, at least one enemy relies on a strong defend, at least one has a "
        f"purge or a lock, and at least one has an infect. "
        f"Each enemy follows these rules. " + MOVESET_MOVE_RULES + MOVESET_NAME_RULES
    )
    for tier in tiers:
        prompt += f" For the {tier} enemies: " + moveset_budget_rules(tier_budget(tier)).rstrip()
    if act > 1:
        prompt += " Leave early empty: this act has no early tier."
    return prompt


def _enemy(proposal: MovesetProposal, enemy_id: str) -> Enemy:
    return Enemy(
        id=enemy_id,
        name=proposal.name,
        description=proposal.description,
        hp=proposal.hp,
        attack=proposal.attack,
        attack_name=proposal.attack_name,
        moves=proposal_moves(proposal),
        body_shape=proposal.body_shape,
        feature=proposal.feature,
    )


def generate_act_pack(
    setting: str = DEFAULT_SETTING, act: int = 1, rng: random.Random | None = None
) -> ActPack:
    """All of an act's regular enemies from one model call, each inside its
    tier's budget - repaired through its HP where it missed only on threat,
    dropped where it can't be. Errors of the call itself (network, an
    unparsable answer) are raised, for the caller to fall back on.

    Or, with the content library on and well stocked, drawn from it at random
    (see LIBRARY_MINIMUM / LIBRARY_CHANCE); `rng` decides both."""
    setting = setting or DEFAULT_SETTING
    rng = rng if rng is not None else random.Random()
    if (pack := _from_library(setting, act, rng)) is not None:
        return pack

    proposal: ActPackProposal = usage.invoke_structured(
        _model(), ActPackProposal, build_prompt(setting, act), "act_pack"
    )

    pack = ActPack(act=act, setting=setting)
    for tier in tiers_for(act):
        budget = tier_budget(tier)
        entries = getattr(proposal, tier)
        if len(entries) > TIER_COUNTS[tier]:
            logger.info(
                "act pack: %d %s entries, keeping %d", len(entries), tier, TIER_COUNTS[tier]
            )
        enemies = getattr(pack, tier)
        for entry in entries[: TIER_COUNTS[tier]]:
            try:
                fitted = fit_to_budget(entry, budget)
            except BudgetViolation as exc:
                logger.info("act pack: dropping %s %r: %s", tier, entry.name, exc)
                continue
            # A placeholder id, unique within the pack; the caller swaps in
            # its own like enemy_for_node does for a prefetched enemy.
            enemies.append(_enemy(fitted, f"act{act}-{tier}-{len(enemies)}"))
    library.store(setting, {tier: getattr(pack, tier) for tier in tiers_for(act)})
    return pack


def _from_library(setting: str, act: int, rng: random.Random) -> ActPack | None:
    """A pack drawn from the content library - None if it is off, any tier is
    short of LIBRARY_MINIMUM, or the LIBRARY_CHANCE roll says ask the model."""
    shelves = library.entries(setting)
    tiers = tiers_for(act)
    if any(len(shelves.get(tier, [])) < LIBRARY_MINIMUM for tier in tiers):
        return None
    if rng.random() >= LIBRARY_CHANCE:
        return None
    drawn = library.draw(setting, {tier: TIER_COUNTS[tier] for tier in tiers}, LIBRARY_MINIMUM, rng)
    if drawn is None:
        return None
    logger.info("act pack: act %d of %r drawn from the content library", act, setting)
    return ActPack(
        act=act,
        setting=setting,
        **{
            tier: [
                enemy.model_copy(update={"id": f"act{act}-{tier}-{index}"})
                for index, enemy in enumerate(enemies)
            ]
            for tier, enemies in drawn.items()
        },
    )
