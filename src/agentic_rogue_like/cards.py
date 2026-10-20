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

from .models import Card, CardType, Rarity, Scaling, Status


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


def vibe_coder_starter_deck() -> list[Card]:
    """The Vibe-Coder's starter deck (see characters.py) - weaker single cards
    than starter_deck(), since every card he plays draws him a new one."""
    cards = [
        Card(
            id=f"prompt-{i}",
            name="Prompt",
            type=CardType.ATTACK,
            value=4,
            description="Deal 4 (+ATK) damage.",
        )
        for i in range(4)
    ]
    cards += [
        Card(
            id=f"make-it-safe-{i}",
            name="Make It Safe",
            type=CardType.BLOCK,
            value=4,
            description="Gain 4 block until your next turn.",
        )
        for i in range(3)
    ]
    cards.append(
        Card(
            id="copilot-0",
            name="Copilot",
            type=CardType.CHAIN,
            value=1,
            token_cost=2,
            description=(
                "Permanent. Action cards played to its right get +1 for every "
                "card you already played this turn."
            ),
        )
    )
    cards.append(
        Card(
            id="energy-drink-0",
            name="Energy Drink",
            type=CardType.TOKEN_REGEN,
            value=1,
            description="Permanent. Frees 1 token at the end of each turn.",
        )
    )
    cards.append(
        Card(
            id="compact-0",
            name="/compact",
            type=CardType.COMPACT,
            value=4,
            exhaust=True,
            token_cost=0,
            description="One-shot. Costs no tokens. Frees 4 used tokens.",
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
        token_cost=2,
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
        token_cost=2,
        rarity=Rarity.RARE,
        description="Deal 2 (+ATK) damage, +4 per banished card.",
    ),
    # ---- statuses: Malware, Exposed, Throttled (combat.STATUS_DESCRIPTIONS)
    Card(
        id="trojan",
        name="Trojan",
        type=CardType.ATTACK,
        value=3,
        applies=Status.MALWARE,
        applies_amount=3,
        rarity=Rarity.COMMON,
        description="Deal 3 (+ATK) damage. Infect it with 3 Malware.",
    ),
    Card(
        id="port-scan",
        name="Port Scan",
        type=CardType.ATTACK,
        value=1,
        applies=Status.EXPOSED,
        applies_amount=2,
        rarity=Rarity.COMMON,
        description="Deal 1 (+ATK) damage. Expose it for 2 turns: attacks deal 50% more.",
    ),
    Card(
        id="packet-loss",
        name="Packet Loss",
        type=CardType.BLOCK,
        value=5,
        applies=Status.THROTTLED,
        applies_amount=2,
        rarity=Rarity.COMMON,
        description="Gain 5 block. Throttle it for 2 turns: it deals 25% less.",
    ),
    Card(
        id="worm",
        name="Worm",
        type=CardType.ATTACK,
        value=2,
        scaling=Scaling.MALWARE,
        scale_value=2,
        rarity=Rarity.UNCOMMON,
        description="Deal 2 (+ATK) damage, +2 per Malware on the enemy.",
    ),
    Card(
        id="ransomware",
        name="Ransomware",
        type=CardType.ATTACK,
        value=0,
        exhaust=True,
        applies=Status.MALWARE,
        applies_amount=6,
        rarity=Rarity.RARE,
        description="One-shot. Deal 0 (+ATK) damage. Infect it with 6 Malware.",
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
        token_cost=2,
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
        token_cost=2,
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
        token_cost=2,
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
        token_cost=2,
        rarity=Rarity.RARE,
        description="Permanent. Attacks deal +1 damage per permanent card on the field.",
    ),
    Card(
        id="daemon",
        name="Daemon",
        type=CardType.TURRET,
        value=4,
        token_cost=2,
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

# The Vibe-Coder's own cards (see characters.py), offered to him on top of
# REWARD_POOL and never to anyone else - they play with his context window
# and his draw-after-every-card. Built around two payoffs:
# - long turns: Tab-Tab-Tab, Copy-Paste and Pair Programming stretch a turn
#   with token-free cards, Ship It and Copilot cash in on every card already
#   played in it;
# - gambling past the window: Rubber Duck takes the sting out of
#   hallucinations, YOLO Deploy hits hard for a big slice of it.
# Token-free cards that refill the hand are one-shot like REWARD_POOL's,
# or two Copy-Pastes could fetch each other forever.
VIBE_CODER_REWARD_POOL: list[Card] = [
    Card(
        id="yolo-deploy",
        name="YOLO Deploy",
        type=CardType.ATTACK,
        value=14,
        discard_cost=1,
        token_cost=2,
        rarity=Rarity.COMMON,
        description="Discard 1 random card. Deal 14 (+ATK) damage.",
    ),
    Card(
        id="copy-paste",
        name="Copy-Paste",
        type=CardType.RETRIEVE,
        value=1,
        exhaust=True,
        token_cost=0,
        rarity=Rarity.COMMON,
        description=(
            "One-shot. Costs no tokens. Return the last card from your graveyard to your hand."
        ),
    ),
    Card(
        id="vibe-check",
        name="Vibe Check",
        type=CardType.BLOCK,
        value=1,
        scaling=Scaling.EMPTY_SLOT,
        scale_value=2,
        rarity=Rarity.COMMON,
        description="Gain 1 block, +2 per empty slot on the field.",
    ),
    Card(
        id="tab-tab-tab",
        name="Tab-Tab-Tab",
        type=CardType.FREE_PLAY,
        value=1,
        exhaust=True,
        token_cost=0,
        rarity=Rarity.UNCOMMON,
        description="One-shot. Costs no tokens. The next card you play this turn is free too.",
    ),
    Card(
        id="rubber-duck",
        name="Rubber Duck",
        type=CardType.SAFEGUARD,
        value=0,
        rarity=Rarity.UNCOMMON,
        description="Permanent. Cards that hallucinate fizzle instead of backfiring.",
    ),
    Card(
        id="ship-it",
        name="Ship It",
        type=CardType.ATTACK,
        value=0,
        scaling=Scaling.PLAYED,
        scale_value=5,
        token_cost=3,
        rarity=Rarity.RARE,
        description="Deal 0 (+ATK) damage, +5 per card you already played this turn.",
    ),
    Card(
        id="pair-programming",
        name="Pair Programming",
        type=CardType.OPENER,
        value=1,
        token_cost=2,
        rarity=Rarity.RARE,
        description="Permanent. The first card you play each turn costs no tokens.",
    ),
]

# Control flow, offered only in program-mode runs (RunState.program_mode):
# they do nothing themselves but steer the queued actions to their right
# when the program runs at the end of the turn (combat.run_program) - which
# is what makes the order of a program matter. Reusable: none of them puts
# a card into the hand on its own, so no loop can run away.
PROGRAM_REWARD_POOL: list[Card] = [
    Card(
        id="if-wounded",
        name="If Wounded",
        type=CardType.IF_WOUNDED,
        value=1,
        rarity=Rarity.COMMON,
        description="Control flow. If the enemy is at half HP or less, the next action runs twice.",
    ),
    Card(
        id="loop",
        name="Loop",
        type=CardType.LOOP,
        value=1,
        rarity=Rarity.UNCOMMON,
        description="Control flow. Runs the last action to its left once more.",
    ),
    Card(
        id="fork",
        name="Fork",
        type=CardType.FORK,
        value=1,
        token_cost=2,
        rarity=Rarity.RARE,
        description="Control flow. The next action to its right runs twice.",
    ),
]

# The Vibe-Coder's control flow, on top of PROGRAM_REWARD_POOL in his
# program-mode runs (CharacterProfile.program_reward_pool): they make the
# order of his program count for what he is about - cards already played,
# and tokens. Pipe wants to run late, Batch early.
VIBE_CODER_PROGRAM_POOL: list[Card] = [
    Card(
        id="batch",
        name="Batch",
        type=CardType.BATCH,
        value=1,
        rarity=Rarity.COMMON,
        description="Control flow. When it runs, frees 1 used token for every action still to run.",
    ),
    Card(
        id="pipe",
        name="Pipe",
        type=CardType.PIPE,
        value=2,
        rarity=Rarity.UNCOMMON,
        description="Control flow. The next action gets +2 for every action that already ran.",
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
    pool: list[Card] | None = None,
) -> list[Card]:
    """`count` distinct reward templates from `pool` (REWARD_POOL by default,
    see CharacterProfile.reward_pool), weighted by rarity - by `weights` if
    given, else the normal or elite reward weights."""
    weights = weights or _RARITY_WEIGHTS[elite]
    pool = REWARD_POOL if pool is None else pool
    offer: list[Card] = []
    while len(offer) < count:
        rarity = rng.choices(list(weights), weights=list(weights.values()))[0]
        options = [c for c in pool if c.rarity is rarity and c not in offer]
        if options:
            offer.append(rng.choice(options))
    return offer


# What a rest site upgrade changes, per card name: the improved fields and
# the description that goes with them. Written out per card instead of a
# formula, so every upgrade reads as a deliberate change - roughly +40% on
# the card's main number, one more of what it does, or (Vibe-Coder) a token
# less. Cards without an
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
    "Trojan": {
        "applies_amount": 5,
        "description": "Deal 3 (+ATK) damage. Infect it with 5 Malware.",
    },
    "Port Scan": {
        "applies_amount": 3,
        "description": "Deal 1 (+ATK) damage. Expose it for 3 turns: attacks deal 50% more.",
    },
    "Packet Loss": {
        "value": 8,
        "description": "Gain 8 block. Throttle it for 2 turns: it deals 25% less.",
    },
    "Worm": {
        "scale_value": 3,
        "description": "Deal 2 (+ATK) damage, +3 per Malware on the enemy.",
    },
    "Ransomware": {
        "applies_amount": 9,
        "description": "One-shot. Deal 0 (+ATK) damage. Infect it with 9 Malware.",
    },
    # ---- the Vibe-Coder's cards (characters.py). Where tokens are the
    # bottleneck, an upgrade may make a card cheaper instead of stronger.
    "Prompt": {"value": 7, "description": "Deal 7 (+ATK) damage."},
    "Make It Safe": {"value": 7, "description": "Gain 7 block until your next turn."},
    "Copilot": {
        "value": 2,
        "description": (
            "Permanent. Action cards played to its right get +2 for every card "
            "you already played this turn."
        ),
    },
    "Energy Drink": {
        "value": 2,
        "description": "Permanent. Frees 2 tokens at the end of each turn.",
    },
    "/compact": {"value": 6, "description": "One-shot. Costs no tokens. Frees 6 used tokens."},
    "YOLO Deploy": {"value": 19, "description": "Discard 1 random card. Deal 19 (+ATK) damage."},
    "Copy-Paste": {
        "value": 2,
        "description": (
            "One-shot. Costs no tokens. Return the last 2 cards from your graveyard to your hand."
        ),
    },
    "Vibe Check": {
        "scale_value": 3,
        "description": "Gain 1 block, +3 per empty slot on the field.",
    },
    "Tab-Tab-Tab": {
        "value": 2,
        "description": (
            "One-shot. Costs no tokens. The next 2 cards you play this turn are free too."
        ),
    },
    "Rubber Duck": {
        "token_cost": 0,
        "description": (
            "Permanent. Costs no tokens. Cards that hallucinate fizzle instead of backfiring."
        ),
    },
    "Ship It": {
        "scale_value": 7,
        "description": "Deal 0 (+ATK) damage, +7 per card you already played this turn.",
    },
    "Pair Programming": {
        "token_cost": 1,
        "description": "Permanent. The first card you play each turn costs no tokens.",
    },
    # ---- control flow (program mode)
    "If Wounded": {
        "draw": 1,
        "description": (
            "Control flow. If the enemy is at half HP or less, the next action runs twice. "
            "Draw 1 card."
        ),
    },
    "Loop": {
        "value": 2,
        "description": "Control flow. Runs the last action to its left twice more.",
    },
    "Batch": {
        "token_cost": 0,
        "description": (
            "Control flow. Costs no tokens. When it runs, frees 1 used token for every "
            "action still to run."
        ),
    },
    "Pipe": {
        "value": 3,
        "description": "Control flow. The next action gets +3 for every action that already ran.",
    },
    "Fork": {
        "draw": 1,
        "description": "Control flow. The next action to its right runs twice. Draw 1 card.",
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
