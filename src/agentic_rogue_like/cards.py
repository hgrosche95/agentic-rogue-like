"""The starter deck and the reward card pool.

The starter deck is what every run begins with; REWARD_POOL is what the
player can add to it - after every won fight they pick one of three cards
(see rewards.py). The pool is built around a few strategies that each have
their own payoff card, so a run can lean into one of them:

- permanents: Botnet, Load Balancer, Mainframe hit harder the fuller the field;
- graveyard: Memory Dump/Brute Force/Fork Bomb fill it, Stack Overflow and Rollback use it;
- one-shot cards: Zero-Day/Sandbox/Backup are strong but banished after use,
  Payload grows with the banished pile, Undelete brings one card back and
  System Restore all of them - at the price of the whole field.

Every card that puts cards into the hand mid-turn (draw, retrieve, restore)
is one-shot on purpose: there is no energy, so a reusable one would allow an
endless loop (two Undeletes fetching each other back, a System Restore
restoring itself, ...). test_cards.py guards this.
"""

from __future__ import annotations

import random

from .models import Card, CardType, Rarity, Scaling


def starter_deck() -> list[Card]:
    """A fresh set of Card instances - callers must not share these across runs."""
    cards = [
        Card(
            id=f"strike-{i}",
            name="Exploit",
            type=CardType.ATTACK,
            value=5,
            description="Deal 5 (+ATK) damage.",
        )
        for i in range(4)
    ]
    cards += [
        Card(
            id=f"defend-{i}",
            name="Firewall",
            type=CardType.BLOCK,
            value=5,
            description="Gain 5 block until your next turn.",
        )
        for i in range(3)
    ]
    cards.append(
        Card(
            id="amplifier-0",
            name="Overclock",
            type=CardType.AMPLIFIER,
            value=25,
            description="Permanent. Action cards played to its right are 25% more effective.",
        )
    )
    cards.append(
        Card(
            id="armor-0",
            name="Encryption",
            type=CardType.ARMOR,
            value=1,
            description="Permanent. Reduce incoming damage by 1.",
        )
    )
    cards.append(
        Card(
            id="more-0",
            name="Prefetch",
            type=CardType.DRAW_BONUS,
            value=1,
            description="Permanent. Draw 1 extra card each turn.",
        )
    )
    cards.append(
        Card(
            id="final-strike-0",
            name="Kernel Panic",
            type=CardType.FINAL_STRIKE,
            value=5,
            description=(
                "Destroy all permanent cards on the field. Deal 5 damage to "
                "the enemy for each one destroyed."
            ),
        )
    )
    return cards


# Templates - `reward_card()` stamps out a fresh copy with a unique id.
REWARD_POOL: list[Card] = [
    # ---- attacks
    Card(
        id="brute-force",
        name="Brute Force",
        type=CardType.ATTACK,
        value=11,
        discard_cost=1,
        rarity=Rarity.COMMON,
        description="Discard 1 random card. Deal 11 (+ATK) damage.",
    ),
    Card(
        id="ddos",
        name="DDoS",
        type=CardType.ATTACK,
        value=0,
        hits=3,
        rarity=Rarity.UNCOMMON,
        description="Hit 3 times for 0 (+ATK) damage.",
    ),
    Card(
        id="zero-day",
        name="Zero-Day",
        type=CardType.ATTACK,
        value=16,
        exhaust=True,
        rarity=Rarity.UNCOMMON,
        description="One-shot. Deal 16 (+ATK) damage.",
    ),
    Card(
        id="botnet",
        name="Botnet",
        type=CardType.ATTACK,
        value=1,
        scaling=Scaling.PERMANENT,
        scale_value=3,
        rarity=Rarity.UNCOMMON,
        description="Deal 1 (+ATK) damage, +3 per permanent card on the field.",
    ),
    Card(
        id="stack-overflow",
        name="Stack Overflow",
        type=CardType.ATTACK,
        value=1,
        scaling=Scaling.GRAVEYARD,
        scale_value=2,
        rarity=Rarity.UNCOMMON,
        description="Deal 1 (+ATK) damage, +2 per card in your graveyard.",
    ),
    Card(
        id="payload",
        name="Payload",
        type=CardType.ATTACK,
        value=2,
        scaling=Scaling.BANISHED,
        scale_value=4,
        rarity=Rarity.RARE,
        description="Deal 2 (+ATK) damage, +4 per banished card.",
    ),
    # ---- defense / sustain
    Card(
        id="honeypot",
        name="Honeypot",
        type=CardType.BLOCK,
        value=7,
        discard_cost=1,
        rarity=Rarity.COMMON,
        description="Discard 1 random card. Gain 7 block.",
    ),
    Card(
        id="sandbox",
        name="Sandbox",
        type=CardType.BLOCK,
        value=15,
        exhaust=True,
        rarity=Rarity.COMMON,
        description="One-shot. Gain 15 block.",
    ),
    Card(
        id="backup",
        name="Backup",
        type=CardType.HEAL,
        value=10,
        exhaust=True,
        rarity=Rarity.UNCOMMON,
        description="One-shot. Heal 10 HP.",
    ),
    # ---- card flow
    Card(
        id="phishing",
        name="Phishing",
        type=CardType.DRAW,
        value=2,
        exhaust=True,
        rarity=Rarity.COMMON,
        description="One-shot. Draw 2 cards.",
    ),
    Card(
        id="memory-dump",
        name="Memory Dump",
        type=CardType.DRAW,
        value=4,
        discard_cost=99,
        exhaust=True,
        rarity=Rarity.UNCOMMON,
        description="One-shot. Discard your hand, then draw 4 cards.",
    ),
    Card(
        id="rollback",
        name="Rollback",
        type=CardType.RETRIEVE,
        value=2,
        exhaust=True,
        rarity=Rarity.COMMON,
        description="One-shot. Return the last 2 cards from your graveyard to your hand.",
    ),
    Card(
        id="undelete",
        name="Undelete",
        type=CardType.RESTORE,
        value=1,
        exhaust=True,
        rarity=Rarity.RARE,
        description="One-shot. Return the last banished card (not an Undelete) to your hand.",
    ),
    Card(
        id="system-restore",
        name="System Restore",
        type=CardType.REBOOT,
        value=0,
        exhaust=True,
        rarity=Rarity.RARE,
        description=(
            "One-shot. Destroy all permanent cards on the field. Return every "
            "banished card (not a restore card) to your hand."
        ),
    ),
    # ---- permanents
    Card(
        id="load-balancer",
        name="Load Balancer",
        type=CardType.DAMAGE_BOOST,
        value=1,
        rarity=Rarity.RARE,
        description="Permanent. Attacks deal +1 damage per permanent card on the field.",
    ),
    Card(
        id="daemon",
        name="Daemon",
        type=CardType.TURRET,
        value=4,
        rarity=Rarity.UNCOMMON,
        description="Permanent. Deal 4 damage to the enemy at the end of each turn.",
    ),
    Card(
        id="mainframe",
        name="Mainframe",
        type=CardType.FORTIFY,
        value=1,
        rarity=Rarity.UNCOMMON,
        description="Permanent. At the end of each turn gain 1 block per permanent card.",
    ),
    Card(
        id="fork-bomb",
        name="Fork Bomb",
        type=CardType.ATTACK,
        value=3,
        hits=2,
        discard_cost=2,
        rarity=Rarity.COMMON,
        description="Discard 2 random cards. Hit twice for 3 (+ATK) damage.",
    ),
]

_RARITY_WEIGHTS: dict[bool, dict[Rarity, int]] = {
    False: {Rarity.COMMON: 60, Rarity.UNCOMMON: 32, Rarity.RARE: 8},
    True: {Rarity.COMMON: 30, Rarity.UNCOMMON: 45, Rarity.RARE: 25},  # elite
}
# The pick offered at the start of a run (engine.new_run): no commons.
START_CARD_WEIGHTS: dict[Rarity, int] = {Rarity.UNCOMMON: 65, Rarity.RARE: 35}


def reward_card(template: Card, deck: list[Card]) -> Card:
    """A fresh copy of `template` with an id no card in `deck` has yet."""
    taken = {c.id for c in deck}
    n = 0
    while f"{template.id}-{n}" in taken:
        n += 1
    return template.model_copy(update={"id": f"{template.id}-{n}"}, deep=True)


def roll_card_reward(
    rng: random.Random,
    elite: bool = False,
    count: int = 3,
    weights: dict[Rarity, int] | None = None,
) -> list[Card]:
    """`count` distinct reward templates, weighted by rarity - by `weights`
    if given, else the normal or elite reward weights."""
    weights = weights or _RARITY_WEIGHTS[elite]
    offer: list[Card] = []
    while len(offer) < count:
        rarity = rng.choices(list(weights), weights=list(weights.values()))[0]
        options = [c for c in REWARD_POOL if c.rarity is rarity and c not in offer]
        if options:
            offer.append(rng.choice(options))
    return offer


# What a rest site upgrade changes, per card name: the improved fields and
# the description that goes with them. Written out per card instead of a
# formula, so every upgrade reads as a deliberate change - roughly +40% on
# the card's main number, or one more of what it does. Cards without an
# entry can't be upgraded: Prefetch (a second extra draw every turn runs
# away with the draw rule) and System Restore (nothing to scale).
CARD_UPGRADES: dict[str, dict[str, object]] = {
    # ---- starter deck
    "Exploit": {"value": 8, "description": "Deal 8 (+ATK) damage."},
    "Firewall": {"value": 8, "description": "Gain 8 block until your next turn."},
    "Overclock": {
        "value": 40,
        "description": "Permanent. Action cards played to its right are 40% more effective.",
    },
    "Encryption": {"value": 2, "description": "Permanent. Reduce incoming damage by 2."},
    "Kernel Panic": {
        "value": 7,
        "description": (
            "Destroy all permanent cards on the field. Deal 7 damage to "
            "the enemy for each one destroyed."
        ),
    },
    # ---- reward pool
    "Brute Force": {"value": 15, "description": "Discard 1 random card. Deal 15 (+ATK) damage."},
    "DDoS": {"hits": 4, "description": "Hit 4 times for 0 (+ATK) damage."},
    "Zero-Day": {"value": 22, "description": "One-shot. Deal 22 (+ATK) damage."},
    "Botnet": {
        "scale_value": 4,
        "description": "Deal 1 (+ATK) damage, +4 per permanent card on the field.",
    },
    "Stack Overflow": {
        "scale_value": 3,
        "description": "Deal 1 (+ATK) damage, +3 per card in your graveyard.",
    },
    "Payload": {"scale_value": 5, "description": "Deal 2 (+ATK) damage, +5 per banished card."},
    "Honeypot": {"value": 11, "description": "Discard 1 random card. Gain 11 block."},
    "Sandbox": {"value": 21, "description": "One-shot. Gain 21 block."},
    "Backup": {"value": 14, "description": "One-shot. Heal 14 HP."},
    "Phishing": {"value": 3, "description": "One-shot. Draw 3 cards."},
    "Memory Dump": {"value": 5, "description": "One-shot. Discard your hand, then draw 5 cards."},
    "Rollback": {
        "value": 3,
        "description": "One-shot. Return the last 3 cards from your graveyard to your hand.",
    },
    "Undelete": {
        "value": 2,
        "description": "One-shot. Return the last 2 banished cards (not Undeletes) to your hand.",
    },
    "Load Balancer": {
        "value": 2,
        "description": "Permanent. Attacks deal +2 damage per permanent card on the field.",
    },
    "Daemon": {
        "value": 6,
        "description": "Permanent. Deal 6 damage to the enemy at the end of each turn.",
    },
    "Mainframe": {
        "value": 2,
        "description": "Permanent. At the end of each turn gain 2 block per permanent card.",
    },
    "Fork Bomb": {
        "value": 5,
        "description": "Discard 2 random cards. Hit twice for 5 (+ATK) damage.",
    },
}


def can_upgrade(card: Card) -> bool:
    return not card.upgraded and card.name in CARD_UPGRADES


def upgrade_card(card: Card) -> Card:
    """The upgraded copy of `card` - same id, a "+" on its name.

    Raises ValueError for a card that is already upgraded or has no upgrade.
    """
    if not can_upgrade(card):
        raise ValueError(f"{card.name} can't be upgraded")
    return card.model_copy(
        update={**CARD_UPGRADES[card.name], "name": f"{card.name}+", "upgraded": True}
    )
