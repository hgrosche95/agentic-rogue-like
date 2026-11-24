"""The black market: a SHOP room sells a random pick of cards and artifacts.

On entering the room the player sees SHOP_CARDS cards from the reward pool
(weighted by rarity, like a card reward) and SHOP_ARTIFACTS artifacts they
don't own yet, each with a price in gold, and SHOP_SCRIPTS scripts from the
fixed pool (consumables.py) at about SCRIPT_BASE_PRICE credits - a script is
only for sale while the bag has a free slot (MAX_CONSUMABLES). They can buy any of them they can
afford, as many as they like, pay to remove one card from their deck (once
per shop, pricier with every removal in the run), and leave whenever they
want - the shop stays open (RunState.shop) until they do.

The stock is rolled from its own rng, seeded by the run seed and the room,
so opening a shop doesn't shift the run rng's sequence (enemies, events,
rewards) compared to a run where the shop is skipped - same idea as the
artifact offers in engine.move_to.
"""

from __future__ import annotations

import random

from .artifacts import gain_artifact, roll_artifact_offer
from .cards import reward_card, roll_card_reward
from .characters import artifact_pool, reward_pool
from .consumables import CONSUMABLE_POOL, SCRIPT_BASE_PRICE, SHOP_SCRIPTS, add_consumable
from .models import MAX_CONSUMABLES, Rarity, RunState, Shop, ShopArtifact, ShopCard, ShopScript

SHOP_CARDS = 4
SHOP_ARTIFACTS = 2

# A fight pays 15-35 gold (engine._finish_combat): a common card costs about
# one fight, an artifact two to three.
CARD_PRICES = {Rarity.COMMON: 25, Rarity.UNCOMMON: 45, Rarity.RARE: 70}
ARTIFACT_PRICE = 75
# Removing a card: the first costs REMOVAL_PRICE, every one after that
# REMOVAL_PRICE_STEP more. The deck never drops below MIN_DECK_SIZE.
REMOVAL_PRICE = 50
REMOVAL_PRICE_STEP = 25
MIN_DECK_SIZE = 5
# prices vary by up to this share either way, rounded to 5 gold
PRICE_SPREAD = 0.15


def _price(base: int, rng: random.Random) -> int:
    return max(5, round(base * rng.uniform(1 - PRICE_SPREAD, 1 + PRICE_SPREAD) / 5) * 5)


def roll_shop(run: RunState) -> Shop:
    rng = random.Random(f"{run.seed}-shop-{run.current_node_id}")
    cards = [
        ShopCard(card=card, price=_price(CARD_PRICES.get(card.rarity, 25), rng))
        for card in roll_card_reward(rng, count=SHOP_CARDS, pool=reward_pool(run))
    ]
    artifacts = [
        ShopArtifact(artifact=artifact, price=_price(ARTIFACT_PRICE, rng))
        for artifact in roll_artifact_offer(
            rng,
            run.player.artifacts,
            SHOP_ARTIFACTS,
            pool=artifact_pool(run),
        )
    ]
    scripts = [
        ShopScript(consumable=consumable, price=_price(SCRIPT_BASE_PRICE, rng))
        for consumable in (rng.choice(CONSUMABLE_POOL) for _ in range(SHOP_SCRIPTS))
    ]
    return Shop(
        cards=cards,
        artifacts=artifacts,
        scripts=scripts,
        removal_price=REMOVAL_PRICE + REMOVAL_PRICE_STEP * run.cards_removed,
    )


def _open_shop(run: RunState) -> Shop:
    if run.shop is None:
        raise ValueError("no shop open")
    return run.shop


def _pay(run: RunState, price: int, what: str) -> None:
    if run.player.gold < price:
        raise ValueError(
            f"not enough credits for {what}: costs {price}, you have {run.player.gold}"
        )
    run.player.gold -= price


def buy_card(run: RunState, index: int) -> None:
    """Buy card `index` into the deck.

    Raises ValueError if no shop is open, the index is out of range, the card
    is already sold or the player can't afford it.
    """
    shop = _open_shop(run)
    if not 0 <= index < len(shop.cards):
        raise ValueError(f"card index {index} is out of range")
    item = shop.cards[index]
    if item.sold:
        raise ValueError(f"{item.card.name} is already sold")
    _pay(run, item.price, item.card.name)
    card = reward_card(item.card, run.player.deck)
    run.player.deck.append(card)
    item.sold = True
    run.history.append(f"You buy {card.name} for {item.price} credits.")


def buy_artifact(run: RunState, index: int) -> None:
    """Buy artifact `index`; raises ValueError like buy_card."""
    shop = _open_shop(run)
    if not 0 <= index < len(shop.artifacts):
        raise ValueError(f"artifact index {index} is out of range")
    item = shop.artifacts[index]
    if item.sold:
        raise ValueError(f"{item.artifact.name} is already sold")
    _pay(run, item.price, item.artifact.name)
    gain_artifact(run.player, item.artifact)
    item.sold = True
    run.history.append(
        f"You buy {item.artifact.name} for {item.price} credits: {item.artifact.description}"
    )


def buy_script(run: RunState, shop: Shop, index: int) -> None:
    """Buy script `index` into the bag.

    Raises ValueError if the index is out of range, the script is already sold,
    the bag is full (len >= MAX_CONSUMABLES - checked before paying, so a
    script that cannot be carried costs nothing) or the player can't afford it.
    """
    if not 0 <= index < len(shop.scripts):
        raise ValueError(f"script index {index} is out of range")
    item = shop.scripts[index]
    if item.sold:
        raise ValueError(f"{item.consumable.name} is already sold")
    if len(run.player.consumables) >= MAX_CONSUMABLES:
        raise ValueError(f"your bag holds no more than {MAX_CONSUMABLES} scripts")
    _pay(run, item.price, item.consumable.name)
    add_consumable(run.player, item.consumable)
    item.sold = True
    run.history.append(
        f"You buy {item.consumable.name} for {item.price} credits: {item.consumable.description}"
    )


def remove_card(run: RunState, deck_index: int) -> None:
    """Pay to remove card `deck_index` from the deck - once per shop.

    Raises ValueError if no shop is open, the removal is already used, the
    index is out of range, the deck is at MIN_DECK_SIZE or the player can't
    afford it.
    """
    shop = _open_shop(run)
    if shop.removal_used:
        raise ValueError("this black market already removed a card")
    deck = run.player.deck
    if not 0 <= deck_index < len(deck):
        raise ValueError(f"deck index {deck_index} is out of range")
    if len(deck) <= MIN_DECK_SIZE:
        raise ValueError(f"your deck can't get smaller than {MIN_DECK_SIZE} cards")
    _pay(run, shop.removal_price, "a card removal")
    card = deck.pop(deck_index)
    shop.removal_used = True
    run.cards_removed += 1
    run.history.append(
        f"You pay {shop.removal_price} credits to delete {card.name} from your deck."
    )


def leave_shop(run: RunState) -> None:
    """Close the shop; raises ValueError if none is open."""
    _open_shop(run)
    run.shop = None
    run.history.append("You leave the black market.")
