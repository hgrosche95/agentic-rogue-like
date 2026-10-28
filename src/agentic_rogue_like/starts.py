"""The start of a run: a starter kit, then the AGI's opening deal.

Every run used to open with the same eleven cards, so the first fights all
played alike. Now, right after the first artifact, the player picks one of
three kits - two cards of one strategy that replace basic cards (see
_KIT_REPLACES) - and so commits to a way of playing from the first room on.
Then the AGI makes an offer: one of three deals, or none. The deals are
worked out down to the card when they are rolled, so the player sees exactly
what they trade.

Both are rolled from their own seeded rngs (like the artifact offers in
engine.new_run), so they don't shift the run rng's sequence.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .artifacts import gain_artifact, roll_artifact_offer
from .cards import can_upgrade, reward_card, upgrade_card
from .models import (
    AgiDeal,
    Artifact,
    Card,
    CardType,
    Character,
    DealKind,
    PlayerState,
    Rarity,
    StarterKit,
)
from .style import PlayStyle, card_styles

KIT_CHOICES = 3
DEAL_CHOICES = 3
FORBIDDEN_MAX_HP = 5
BRIBE_GOLD = 90


@dataclass(frozen=True)
class _KitSpec:
    id: str
    name: str
    blurb: str
    cards: tuple[str, str]


# A kit is offered only if both its cards are in the run's reward pool - so
# the Vibe-Coder's and program mode's kits only show up where they belong.
KITS = (
    _KitSpec(
        "daemons",
        "Daemon farm",
        "Permanents that keep working: a Daemon hits every turn, a Botnet per permanent.",
        ("Daemon", "Botnet"),
    ),
    _KitSpec(
        "graveyard",
        "Graveyard",
        "Throw cards away on purpose, then bring the best ones back.",
        ("Brute Force", "Rollback"),
    ),
    _KitSpec(
        "one_shot",
        "One-shot",
        "A Payload that grows with every card used up, and Undelete to bring one back.",
        ("Payload", "Undelete"),
    ),
    _KitSpec(
        "malware",
        "Malware",
        "Infect the enemy, then hit harder the sicker it gets.",
        ("Trojan", "Worm"),
    ),
    _KitSpec(
        "move_fast",
        "Move fast",
        "One reckless deploy, and a Vibe Check that blocks more the emptier the field.",
        ("YOLO Deploy", "Vibe Check"),
    ),
    _KitSpec(
        "rubber_duck",
        "Rubber duck",
        "Hallucinations fizzle, and Copy-Paste brings your last card back.",
        ("Rubber Duck", "Copy-Paste"),
    ),
    _KitSpec(
        "control_flow",
        "Control flow",
        "Steer the program: repeat what ran, double it when the enemy is low.",
        ("Loop", "If Wounded"),
    ),
    _KitSpec(
        "pipeline",
        "Pipeline",
        "Chain the program: early lines pay tokens back, late lines hit harder.",
        ("Batch", "Pipe"),
    ),
)

# What a kit takes out of the starter deck. The Vibe-Coder draws a card for
# every card he plays, so a thinner deck pays off more for him: balance-sim put
# him 5 points above Dr. Chronos with the same swap, and 3 with one basic fewer.
_KIT_REPLACES: dict[Character, tuple[tuple[CardType, int], ...]] = {
    Character.CHRONOS: ((CardType.ATTACK, 2), (CardType.BLOCK, 1)),
    Character.VIBE_CODER: ((CardType.ATTACK, 1), (CardType.BLOCK, 1)),
}


def _basics(deck: list[Card], card_type: CardType) -> list[Card]:
    """The plain starter cards of `card_type` - not the starter deck's
    strategy cards (Ping, ...), which stay to show what else the deck can do."""
    return [
        c
        for c in deck
        if c.rarity is Rarity.STARTER
        and c.type is card_type
        and card_styles(c) <= {PlayStyle.AGGRO, PlayStyle.TURTLE}
    ]


def roll_kits(rng: random.Random, pool: list[Card]) -> list[StarterKit]:
    by_name = {c.name: c for c in pool}
    eligible = [k for k in KITS if all(name in by_name for name in k.cards)]
    picked = rng.sample(eligible, min(KIT_CHOICES, len(eligible)))
    return [
        StarterKit(id=k.id, name=k.name, blurb=k.blurb, cards=[by_name[n] for n in k.cards])
        for k in picked
    ]


def apply_kit(player: PlayerState, kit: StarterKit) -> list[Card]:
    """Swap the basics out for the kit's cards; returns the cards removed."""
    removed: list[Card] = []
    for card_type, count in _KIT_REPLACES[player.character]:
        removed += _basics(player.deck, card_type)[-count:]
    for card in removed:
        player.deck.remove(card)
    for template in kit.cards:
        player.deck.append(reward_card(template, player.deck))
    return removed


def _glitch(deck: list[Card]) -> Card:
    """A dead card for good: it does nothing and is used up for the fight
    when played, but comes back every fight. STARTER, so the AGI's style
    reading (style.py) never counts it as a choice."""
    template = Card(
        id="deal-glitch",
        name="Glitch",
        type=CardType.GLITCH,
        value=0,
        exhaust=True,
        token_cost=0,
        description="Does nothing. Play it to flush it out for this fight.",
    )
    return reward_card(template, deck)


def _names(cards: list[Card]) -> str:
    return " and ".join(c.name for c in cards)


def roll_deals(
    rng: random.Random,
    player: PlayerState,
    pool: list[Card],
    artifact_pool: list[Artifact],
) -> list[AgiDeal]:
    deck = player.deck
    attacks = _basics(deck, CardType.ATTACK)
    blocks = _basics(deck, CardType.BLOCK)
    commons = [c for c in pool if c.rarity is Rarity.COMMON]
    rares = [c for c in pool if c.rarity is Rarity.RARE]
    upgradable = [c for c in attacks + blocks if can_upgrade(c)]
    artifacts = roll_artifact_offer(rng, player.artifacts, count=1, pool=artifact_pool)

    deals: list[AgiDeal] = []
    if attacks and blocks:
        gone = [attacks[-1], blocks[-1]]
        deals.append(
            AgiDeal(
                kind=DealKind.STRIP,
                name="Delete legacy code",
                description=f"Remove {_names(gone)} from your deck.",
                remove=[c.id for c in gone],
            )
        )
    if len(attacks + blocks) >= 2 and len(commons) >= 2:
        gone = rng.sample(attacks + blocks, 2)
        new = rng.sample(commons, 2)
        deals.append(
            AgiDeal(
                kind=DealKind.MUTATE,
                name="Mutation",
                description=f"{_names(gone)} turn into {_names(new)}.",
                remove=[c.id for c in gone],
                add=new,
            )
        )
    if rares:
        rare = rng.choice(rares)
        deals.append(
            AgiDeal(
                kind=DealKind.FORBIDDEN,
                name="Forbidden patch",
                description=(
                    f"Take {rare.name} ({rare.description}) - for {FORBIDDEN_MAX_HP} max HP."
                ),
                add=[rare],
                max_hp=-FORBIDDEN_MAX_HP,
            )
        )
    if artifacts:
        artifact = artifacts[0]
        deals.append(
            AgiDeal(
                kind=DealKind.TROJAN,
                name="Trojan gift",
                description=f"Install {artifact.name} ({artifact.description}) - "
                "but a Glitch hides in your deck.",
                artifact=artifact,
                add=[_glitch(deck)],
            )
        )
    if len(upgradable) >= 2:
        patched = rng.sample(upgradable, 2)
        deals.append(
            AgiDeal(
                kind=DealKind.HOTFIX,
                name="Hotfix",
                description=f"Upgrade {_names(patched)}.",
                upgrade=[c.id for c in patched],
            )
        )
    deals.append(
        AgiDeal(
            kind=DealKind.BRIBE,
            name="Bribe",
            description=f"Take {BRIBE_GOLD} credits - but a Glitch hides in your deck.",
            gold=BRIBE_GOLD,
            add=[_glitch(deck)],
        )
    )
    return rng.sample(deals, min(DEAL_CHOICES, len(deals)))


def apply_deal(player: PlayerState, deal: AgiDeal) -> None:
    player.deck = [c for c in player.deck if c.id not in deal.remove]
    player.deck = [upgrade_card(c) if c.id in deal.upgrade else c for c in player.deck]
    for template in deal.add:
        player.deck.append(reward_card(template, player.deck))
    if deal.artifact is not None:
        gain_artifact(player, deal.artifact)
    if deal.max_hp:
        player.max_hp += deal.max_hp
        player.hp = min(player.hp, player.max_hp)
    player.gold += deal.gold
