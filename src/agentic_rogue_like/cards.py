"""Static starter deck - placeholder card content, mirrors enemies.py.

Just enough card variety (action cards + the five permanent cards) to make
the field/hand/deck loop in combat.py actually playable end-to-end. A real
card pool (rewards, shop purchases, upgrades) is later work - this module
is where it will grow.
"""

from __future__ import annotations

from .models import Card, CardType


def starter_deck() -> list[Card]:
    """A fresh set of Card instances - callers must not share these across runs."""
    cards = [
        Card(
            id=f"strike-{i}",
            name="Strike",
            type=CardType.ATTACK,
            value=6,
            description="Deal 6 damage (plus your attack stat).",
        )
        for i in range(4)
    ]
    cards += [
        Card(
            id=f"defend-{i}",
            name="Defend",
            type=CardType.BLOCK,
            value=5,
            description="Gain 5 block until your next turn.",
        )
        for i in range(3)
    ]
    cards.append(
        Card(id="mend-0", name="Mend", type=CardType.HEAL, value=4, description="Heal 4 HP.")
    )
    cards.append(
        Card(
            id="amplifier-0",
            name="Amplifier",
            type=CardType.AMPLIFIER,
            value=25,
            description="Permanent. Action cards played to its right are 25% more effective.",
        )
    )
    cards.append(
        Card(
            id="armor-0",
            name="Armor",
            type=CardType.ARMOR,
            value=1,
            description="Permanent. Reduce incoming damage by 1.",
        )
    )
    cards.append(
        Card(
            id="recycling-0",
            name="Recycling",
            type=CardType.RECYCLING,
            value=0,
            description=(
                "Permanent. Action cards played to its left go back to the "
                "deck instead of the discard pile."
            ),
        )
    )
    cards.append(
        Card(
            id="more-0",
            name="More",
            type=CardType.DRAW_BONUS,
            value=1,
            description="Permanent. Draw 1 extra card each turn.",
        )
    )
    cards.append(
        Card(
            id="final-strike-0",
            name="Final Strike",
            type=CardType.FINAL_STRIKE,
            value=5,
            description=(
                "Destroy all permanent cards on the field. Deal 5 damage to "
                "the enemy for each one destroyed."
            ),
        )
    )
    return cards
