"""The AGI's custom card: a deal tailored to the deck it has analysed.

Once per act, as soon as the player's deck shows a clear style (style.py),
the AGI offers a card compiled for that style - strong, and with a price:
the AGI is the antagonist, so its gifts are bait, never help.

The split is the project's usual one. Whoever designs the card - the card
agent (agent/card_agent.py) or the static fallback here - only picks
building blocks: a name, attack or block, numbers, a scaling the game
already knows, and drawbacks. The game turns them into a Card, writes its
rules text itself (describe), and checks its strength against a budget
(card_power, validate_spec) - a model can't sneak in a card that reads
one way and plays another, or one that breaks the run.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, Field

from .models import AgiDeal, Card, CardType, DealKind, Rarity, Scaling, Status
from .starts import glitch_card
from .style import LABELS, PlayStyle

# What a forged card's power (card_power) has to land in: above a reward
# rare's usual 10-12, below a one-shot's 16 - the price of the deal pays
# for the rest.
FORGE_MIN_POWER = 12.0
FORGE_MAX_POWER = 16.0

# How much of each scaling a deck typically has to count when the card is
# played - what makes "+3 per graveyard card" comparable to "+5 flat".
TYPICAL_COUNT: dict[Scaling, float] = {
    Scaling.PERMANENT: 2.0,
    Scaling.GRAVEYARD: 4.0,
    Scaling.BANISHED: 2.0,
    Scaling.PLAYED: 2.0,
    Scaling.EMPTY_SLOT: 2.0,
    Scaling.MALWARE: 3.0,
    Scaling.BLOCK: 5.0,
    Scaling.LINES: 2.5,
    Scaling.FIRST_LINE: 0.8,
    Scaling.LAST_LINE: 0.8,
}
PROGRAM_SCALINGS = frozenset({Scaling.LINES, Scaling.FIRST_LINE, Scaling.LAST_LINE})
# The scalings a card for each style may use - the card has to fit what the
# AGI analysed (a banish deck gets no card that counts permanents). A card
# without a scaling fits every style.
STYLE_SCALINGS: dict[PlayStyle, frozenset[Scaling]] = {
    PlayStyle.PERMANENTS: frozenset({Scaling.PERMANENT, Scaling.EMPTY_SLOT}),
    PlayStyle.GRAVEYARD: frozenset({Scaling.GRAVEYARD}),
    PlayStyle.ONE_SHOT: frozenset({Scaling.BANISHED}),
    PlayStyle.AGGRO: frozenset({Scaling.PLAYED}),
    PlayStyle.TURTLE: frozenset({Scaling.BLOCK}),
    PlayStyle.MALWARE: frozenset({Scaling.MALWARE}),
    PlayStyle.PROGRAM: PROGRAM_SCALINGS,
}
ONE_SHOT_FACTOR = 0.65  # banished after use
DISCARD_COST = 3.0  # per random hand card thrown away
HALT_COST = 2.0  # the program ends after its line
MALWARE_VALUE = 0.8  # per Malware stack left on the enemy

# The deal's price, one of them, rolled.
FORGE_MAX_HP_COST = 6

_SCALING_TEXT = {
    Scaling.PERMANENT: "per permanent card on the field",
    Scaling.GRAVEYARD: "per card in your graveyard",
    Scaling.BANISHED: "per banished card",
    Scaling.PLAYED: "per card you already played this turn",
    Scaling.EMPTY_SLOT: "per empty field slot",
    Scaling.MALWARE: "per Malware on the enemy",
    Scaling.BLOCK: "per block you have",
    Scaling.LINES: "for every other queued line",
    Scaling.FIRST_LINE: "if its line is the first to run",
    Scaling.LAST_LINE: "if its line is the last to run",
}


class ForgeViolation(ValueError):
    """A card design the game won't take - the message says why."""


class CardSpec(BaseModel):
    """The building blocks of a forged card - all the designer gets to pick."""

    name: str = Field(min_length=2, max_length=24)
    attack: bool = Field(description="true: an attack card, false: a block card")
    value: int = Field(ge=0, le=24)
    hits: int = Field(default=1, ge=1, le=3, description="attacks only")
    scaling: Scaling | None = None
    scale_value: int = Field(default=0, ge=-3, le=6)
    malware: int = Field(default=0, ge=0, le=4, description="attacks only: Malware it leaves")
    discard_cost: int = Field(default=0, ge=0, le=2)
    one_shot: bool = False
    halts: bool = Field(default=False, description="program mode only: ends the program")


def card_power(spec: CardSpec) -> float:
    """Roughly what the card is worth per play, in damage or block."""
    base = spec.value
    if spec.scaling is not None:
        base += spec.scale_value * TYPICAL_COUNT[spec.scaling]
    power = base * (spec.hits if spec.attack else 1)
    power += spec.malware * MALWARE_VALUE
    power -= spec.discard_cost * DISCARD_COST + (HALT_COST if spec.halts else 0)
    return power * (ONE_SHOT_FACTOR if spec.one_shot else 1)


def describe(spec: CardSpec) -> str:
    """The card's rules text, written by the game from the building blocks."""
    parts: list[str] = []
    if spec.one_shot:
        parts.append("One-shot.")
    if spec.discard_cost:
        parts.append(
            f"Discard {spec.discard_cost} random card{'s' if spec.discard_cost > 1 else ''}."
        )
    if spec.attack:
        hit = (
            f"Hit {spec.hits} times for {spec.value} (+ATK) damage"
            if spec.hits > 1
            else f"Deal {spec.value} (+ATK) damage"
        )
    else:
        hit = f"Gain {spec.value} block"
    if spec.scaling is not None and spec.scale_value:
        sign = "+" if spec.scale_value > 0 else "-"
        hit += f", {sign}{abs(spec.scale_value)} {_SCALING_TEXT[spec.scaling]}"
    parts.append(hit + ".")
    if spec.malware:
        parts.append(f"Infect it with {spec.malware} Malware.")
    if spec.halts:
        parts.append("The program ends after its line.")
    return " ".join(parts)


def validate_spec(spec: CardSpec, program_mode: bool, style: PlayStyle | None = None) -> Card:
    """The Card a design makes, or ForgeViolation saying what is wrong.
    `style`: the style it is forged for - its scaling has to fit it."""
    if style is not None and spec.scaling is not None and spec.scaling not in STYLE_SCALINGS[style]:
        allowed = ", ".join(sorted(s.value for s in STYLE_SCALINGS[style]))
        raise ForgeViolation(
            f"scaling {spec.scaling.value} doesn't fit a deck that leans on {LABELS[style]} - "
            f"use {allowed} or none"
        )
    if not spec.attack and (spec.hits > 1 or spec.malware):
        raise ForgeViolation("a block card can't have hits or malware")
    if spec.scaling is None and spec.scale_value:
        raise ForgeViolation("scale_value needs a scaling")
    if spec.scaling is not None and not spec.scale_value:
        raise ForgeViolation("a scaling needs a scale_value")
    if not program_mode and (spec.halts or spec.scaling in PROGRAM_SCALINGS):
        raise ForgeViolation("halts and line scalings only exist in program mode")
    power = card_power(spec)
    if not FORGE_MIN_POWER <= power <= FORGE_MAX_POWER:
        raise ForgeViolation(
            f"power {power:.1f} is outside {FORGE_MIN_POWER:g}-{FORGE_MAX_POWER:g} "
            "(value + scale_value x typical count, times hits, plus malware, minus "
            "drawbacks, x0.65 for one-shot)"
        )
    return Card(
        id=f"agi-{''.join(ch for ch in spec.name.lower() if ch.isalnum()) or 'card'}",
        name=spec.name,
        type=CardType.ATTACK if spec.attack else CardType.BLOCK,
        value=spec.value,
        hits=spec.hits if spec.attack else 1,
        scaling=spec.scaling,
        scale_value=spec.scale_value,
        applies=Status.MALWARE if spec.malware else None,
        applies_amount=spec.malware,
        discard_cost=spec.discard_cost,
        exhaust=spec.one_shot,
        halts=spec.halts,
        rarity=Rarity.RARE,
        description=describe(spec),
    )


# The static design per style - what the AGI compiles when the card agent is
# off or fails. Each sits inside the budget (test_forge.py checks).
FALLBACK_SPECS: dict[PlayStyle, CardSpec] = {
    PlayStyle.PERMANENTS: CardSpec(
        name="Daemon Swarm", attack=True, value=4, scaling=Scaling.PERMANENT, scale_value=4
    ),
    PlayStyle.GRAVEYARD: CardSpec(
        name="Core Dump",
        attack=True,
        value=3,
        scaling=Scaling.GRAVEYARD,
        scale_value=3,
        discard_cost=1,
    ),
    PlayStyle.ONE_SHOT: CardSpec(
        name="Shredder", attack=True, value=4, scaling=Scaling.BANISHED, scale_value=4
    ),
    PlayStyle.AGGRO: CardSpec(name="Brute Loop", attack=True, value=6, hits=2),
    PlayStyle.TURTLE: CardSpec(name="Air Gap", attack=False, value=13),
    PlayStyle.MALWARE: CardSpec(
        name="Worm", attack=True, value=4, scaling=Scaling.MALWARE, scale_value=2, malware=4
    ),
    PlayStyle.PROGRAM: CardSpec(
        name="Hot Loop", attack=True, value=6, scaling=Scaling.LINES, scale_value=3
    ),
}


def fallback_card(style: PlayStyle, program_mode: bool) -> Card:
    spec = FALLBACK_SPECS[style]
    if not program_mode and spec.scaling in PROGRAM_SCALINGS:
        # a program style without a program can't happen in play; stay safe
        spec = FALLBACK_SPECS[PlayStyle.AGGRO]
    return validate_spec(spec, program_mode, style)


def forged_deal(card: Card, style: PlayStyle, rng: random.Random) -> AgiDeal:
    """The deal around a forged card: the card, and a price."""
    if rng.random() < 0.5:
        price, max_hp, glitch = f"{FORGE_MAX_HP_COST} max HP", -FORGE_MAX_HP_COST, False
    else:
        price, max_hp, glitch = "a Glitch hidden in your deck", 0, True
    return AgiDeal(
        kind=DealKind.FORGED,
        name=f"Compiled for you: {card.name}",
        description=f"Take {card.name} ({card.description}) - for {price}.",
        add=[card] + ([glitch_card([])] if glitch else []),
        max_hp=max_hp,
        greeting=f"YOUR RELIANCE ON {LABELS[style].upper()} HAS BEEN ANALYSED.",
        pitch=(
            "I compiled something just for you. It fits your code perfectly - "
            "and like every gift of mine, it has a price."
        ),
    )
