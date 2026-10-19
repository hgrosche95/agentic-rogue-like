"""Events: a room with a choice, built from fixed effect building blocks.

An event is a description and 2-3 options; every option is a list of
effects (gain or lose gold, HP, max HP, a card, an upgrade) - or a gamble
between two such lists. Being data instead of code, an event can come from
the hand-written EVENT_POOL below or from the event agent
(agent/event_agent.py), and the same rules hold either way.

Those rules are what make an event a real choice (validate_event): every
option but a plain "walk away" has a price, and none is worth more than
EVENT_MAX_VALUE. Worth is measured in gold - option_value() prices every
effect at roughly what the black market charges for it - so "60 gold for
8 HP" and "a rare card for 5 max HP" can be weighed against each other.
"""

from __future__ import annotations

import random
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from .cards import can_upgrade, reward_card, upgrade_card
from .models import Card, PlayerState, Rarity


class EffectKind(StrEnum):
    GOLD = "gold"  # amount: + gain / - pay (never below 0 gold)
    HP = "hp"  # amount: + heal / - hurt (never below 1 HP - events don't kill)
    MAX_HP = "max_hp"  # amount: + / - max HP (HP follows a gain, is capped by a loss)
    ADD_CARD = "add_card"  # a random reward card of `rarity`
    LOSE_CARD = "lose_card"  # a random card leaves the deck
    UPGRADE_CARD = "upgrade_card"  # a random upgradable card is upgraded


# What one unit of each effect is worth, in gold - anchored on what the
# black market charges (shop.py: cards 25/45/70, a removal 50). HP was first
# priced off the rest site (15 HP ~ an upgrade, so 3 gold), but in
# balance-sim bots that took the best-valued option then did worse than bots
# that always walked away: HP is worth more than that. At 5 (max HP 8),
# taking the best option pays off again for both characters.
GOLD_PER_HP = 5
GOLD_PER_MAX_HP = 8
CARD_VALUE = {Rarity.COMMON: 25, Rarity.UNCOMMON: 45, Rarity.RARE: 70}
LOSE_CARD_VALUE = -20  # a random card: usually a starter, sometimes a good one
UPGRADE_VALUE = 40

# An option worth more than this (in gold) is a gift, not a choice.
EVENT_MAX_VALUE = 40
# ...and one worth less than this is a trap nobody should take.
EVENT_MIN_VALUE = -10
# Bounds for a single effect - an agent's "+500 gold" never gets that far.
AMOUNT_BOUNDS = {
    EffectKind.GOLD: (-60, 100),
    EffectKind.HP: (-20, 20),
    EffectKind.MAX_HP: (-8, 8),
}
MIN_DECK_SIZE_AFTER_EVENT = 5


class EventEffect(BaseModel):
    kind: EffectKind
    amount: int = 0  # GOLD, HP, MAX_HP
    rarity: Rarity | None = None  # ADD_CARD

    @model_validator(mode="after")
    def _fits_its_kind(self) -> EventEffect:
        if self.kind in AMOUNT_BOUNDS:
            low, high = AMOUNT_BOUNDS[self.kind]
            if self.amount == 0 or not low <= self.amount <= high:
                raise ValueError(f"{self.kind.value} amount must be in [{low}, {high}], not 0")
        elif self.amount:
            raise ValueError(f"{self.kind.value} takes no amount")
        if (self.kind is EffectKind.ADD_CARD) != (self.rarity is not None):
            raise ValueError("add_card, and only add_card, needs a rarity")
        if self.rarity is Rarity.STARTER:
            raise ValueError("add_card can't add a starter card")
        return self


class EventOption(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    effects: list[EventEffect] = Field(default_factory=list, max_length=3)
    # A gamble: `effects` with this chance, `fail_effects` otherwise.
    chance: float | None = Field(default=None, gt=0, lt=1)
    fail_effects: list[EventEffect] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def _gamble_or_not(self) -> EventOption:
        if self.fail_effects and self.chance is None:
            raise ValueError("fail_effects need a chance")
        if self.chance is not None and not self.effects:
            raise ValueError("a gamble needs effects to win")
        return self


class GameEvent(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    options: list[EventOption] = Field(min_length=2, max_length=3)


class EventViolation(Exception):
    """An event that breaks the rules of a real choice (see validate_event)."""


def _effects_value(effects: list[EventEffect]) -> float:
    value = 0.0
    for e in effects:
        if e.kind is EffectKind.GOLD:
            value += e.amount
        elif e.kind is EffectKind.HP:
            value += e.amount * GOLD_PER_HP
        elif e.kind is EffectKind.MAX_HP:
            value += e.amount * GOLD_PER_MAX_HP
        elif e.kind is EffectKind.ADD_CARD:
            value += CARD_VALUE[e.rarity]
        elif e.kind is EffectKind.LOSE_CARD:
            value += LOSE_CARD_VALUE
        elif e.kind is EffectKind.UPGRADE_CARD:
            value += UPGRADE_VALUE
    return value


def option_value(option: EventOption) -> float:
    """What the option is worth on average, in gold."""
    if option.chance is None:
        return _effects_value(option.effects)
    return option.chance * _effects_value(option.effects) + (1 - option.chance) * _effects_value(
        option.fail_effects
    )


def _has_cost(effects: list[EventEffect]) -> bool:
    return any(e.amount < 0 or e.kind is EffectKind.LOSE_CARD for e in effects)


def is_leave(option: EventOption) -> bool:
    return not option.effects and option.chance is None


def validate_event(event: GameEvent) -> None:
    """Raise EventViolation unless every option is a real choice: at most
    one walk-away option, and every other one has a price (a cost, or a
    gamble that can go wrong) and is worth between EVENT_MIN_VALUE and
    EVENT_MAX_VALUE gold. The message is written for the agent's retry."""
    leaves = [o for o in event.options if is_leave(o)]
    if len(leaves) > 1:
        raise EventViolation("at most one option may do nothing")
    if len(leaves) == len(event.options):
        raise EventViolation("an event needs at least one option that does something")
    for option in event.options:
        if is_leave(option):
            continue
        gamble_can_fail = option.chance is not None and _has_cost(option.fail_effects)
        if not (_has_cost(option.effects) or gamble_can_fail):
            raise EventViolation(
                f"option {option.label!r} has no price - give it a cost "
                f"(negative gold/hp/max_hp or lose_card) or make it a gamble whose "
                f"fail_effects cost something"
            )
        value = option_value(option)
        if value > EVENT_MAX_VALUE:
            raise EventViolation(
                f"option {option.label!r} is worth {value:.0f} gold, more than the "
                f"{EVENT_MAX_VALUE} allowed - raise its cost or lower its reward"
            )
        if value < EVENT_MIN_VALUE:
            raise EventViolation(
                f"option {option.label!r} is worth {value:.0f} gold, less than the "
                f"{EVENT_MIN_VALUE} allowed - nobody would pick it"
            )


# ---------------------------------------------------------------- describing


def _describe(effects: list[EventEffect]) -> str:
    parts = []
    for e in effects:
        if e.kind is EffectKind.GOLD:
            parts.append(f"{e.amount:+d} gold")
        elif e.kind is EffectKind.HP:
            parts.append(f"{e.amount:+d} HP")
        elif e.kind is EffectKind.MAX_HP:
            parts.append(f"{e.amount:+d} max HP")
        elif e.kind is EffectKind.ADD_CARD:
            article = "an" if e.rarity is Rarity.UNCOMMON else "a"
            parts.append(f"{article} {e.rarity.value} card")
        elif e.kind is EffectKind.LOSE_CARD:
            parts.append("lose a random card")
        elif e.kind is EffectKind.UPGRADE_CARD:
            parts.append("upgrade a random card")
    return ", ".join(parts) or "nothing"


def describe_option(option: EventOption) -> str:
    """What picking the option does, in game terms - shown next to its label."""
    if is_leave(option):
        return "Nothing happens."
    if option.chance is None:
        return _describe(option.effects)
    return (
        f"{round(option.chance * 100)}%: {_describe(option.effects)} - "
        f"otherwise: {_describe(option.fail_effects)}"
    )


# ---------------------------------------------------------------- applying


def apply_option(
    option: EventOption, player: PlayerState, reward_pool: list[Card], rng: random.Random
) -> str:
    """Resolve the option on `player` and say what happened."""
    if is_leave(option):
        return "You walk on."
    effects = option.effects
    lead = ""
    if option.chance is not None:
        won = rng.random() < option.chance
        effects = option.effects if won else option.fail_effects
        lead = "It pays off. " if won else "It goes wrong. "
    lines = [_apply(e, player, reward_pool, rng) for e in effects]
    return lead + " ".join(line for line in lines if line) if lines else lead + "Nothing else."


def _apply(effect: EventEffect, player: PlayerState, pool: list[Card], rng: random.Random) -> str:
    kind, amount = effect.kind, effect.amount
    if kind is EffectKind.GOLD:
        paid = max(amount, -player.gold)
        player.gold += paid
        return f"You {'gain' if paid >= 0 else 'pay'} {abs(paid)} gold."
    if kind is EffectKind.HP:
        before = player.hp
        player.hp = max(1, min(player.max_hp, player.hp + amount))
        change = player.hp - before
        return f"You {'recover' if change >= 0 else 'lose'} {abs(change)} HP."
    if kind is EffectKind.MAX_HP:
        player.max_hp = max(1, player.max_hp + amount)
        player.hp = min(player.max_hp, player.hp + max(amount, 0))
        return f"Your max HP {'rises' if amount > 0 else 'drops'} by {abs(amount)}."
    if kind is EffectKind.ADD_CARD:
        options = [c for c in pool if c.rarity is effect.rarity]
        card = reward_card(rng.choice(options), player.deck)
        player.deck.append(card)
        return f"{card.name} joins your deck."
    if kind is EffectKind.LOSE_CARD:
        if len(player.deck) <= MIN_DECK_SIZE_AFTER_EVENT:
            return "Your deck is too thin to lose anything."
        card = player.deck.pop(rng.randrange(len(player.deck)))
        return f"{card.name} is gone from your deck."
    # UPGRADE_CARD
    upgradable = [i for i, c in enumerate(player.deck) if can_upgrade(c)]
    if not upgradable:
        return "Nothing in your deck can be upgraded."
    index = rng.choice(upgradable)
    before = player.deck[index]
    player.deck[index] = upgrade_card(before)
    return f"{before.name} becomes {player.deck[index].name}."


# ---------------------------------------------------------------- the static pool


def _e(kind: EffectKind, amount: int = 0, rarity: Rarity | None = None) -> EventEffect:
    return EventEffect(kind=kind, amount=amount, rarity=rarity)


_GOLD, _HP, _MAX_HP = EffectKind.GOLD, EffectKind.HP, EffectKind.MAX_HP
_ADD, _LOSE, _UPGRADE = EffectKind.ADD_CARD, EffectKind.LOSE_CARD, EffectKind.UPGRADE_CARD

# Hand-written, held to the same rules as an agent's (a test checks), and
# themed per setting by the narrator. What every room falls back to when the
# event agent is off or fails.
EVENT_POOL: list[GameEvent] = [
    GameEvent(
        description="A dusty chest sits half-buried in rubble.",
        options=[
            EventOption(
                label="Pry it open",
                effects=[_e(_GOLD, 60)],
                chance=0.7,
                fail_effects=[_e(_HP, -10)],
            ),
            EventOption(label="Leave it - could be trapped"),
        ],
    ),
    GameEvent(
        description="A narrow shortcut splits off from the main path.",
        options=[
            EventOption(label="Take the shortcut", effects=[_e(_UPGRADE), _e(_HP, -5)]),
            EventOption(label="Stick to the main path"),
        ],
    ),
    GameEvent(
        description="A wounded traveler clutches a heavy pack.",
        options=[
            EventOption(
                label="Tend their wounds", effects=[_e(_ADD, rarity=Rarity.RARE), _e(_HP, -8)]
            ),
            EventOption(label="Take the pack", effects=[_e(_GOLD, 50), _e(_HP, -4)]),
            EventOption(label="Walk on"),
        ],
    ),
    GameEvent(
        description="A blood-red altar hums with a low, hungry power.",
        options=[
            EventOption(
                label="Offer your blood", effects=[_e(_ADD, rarity=Rarity.RARE), _e(_MAX_HP, -5)]
            ),
            EventOption(
                label="Pray",
                effects=[_e(_MAX_HP, 6)],
                chance=0.5,
                fail_effects=[_e(_HP, -6)],
            ),
            EventOption(label="Leave it be"),
        ],
    ),
    GameEvent(
        description="A merchant's cart lies overturned across the path.",
        options=[
            EventOption(label="Salvage what you can", effects=[_e(_GOLD, 45), _e(_HP, -3)]),
            EventOption(
                label="Help right the cart",
                effects=[_e(_ADD, rarity=Rarity.UNCOMMON), _e(_GOLD, -15)],
            ),
        ],
    ),
    GameEvent(
        description="A grizzled hermit offers to sharpen your skills - for a price.",
        options=[
            EventOption(label="Pay the hermit", effects=[_e(_UPGRADE), _e(_GOLD, -35)]),
            EventOption(label="Train until you drop", effects=[_e(_UPGRADE), _e(_HP, -6)]),
            EventOption(label="Decline"),
        ],
    ),
    GameEvent(
        description="A cracked mirror shows a stranger, stronger you.",
        options=[
            EventOption(
                label="Step through", effects=[_e(_LOSE), _e(_ADD, rarity=Rarity.UNCOMMON)]
            ),
            EventOption(
                label="Smash it",
                effects=[_e(_GOLD, 45)],
                chance=0.5,
                fail_effects=[_e(_HP, -4)],
            ),
            EventOption(label="Look away"),
        ],
    ),
    GameEvent(
        description="A quiet clearing offers a moment to catch your breath.",
        options=[
            EventOption(label="Rest here", effects=[_e(_HP, 8), _e(_MAX_HP, -1)]),
            EventOption(label="Press on"),
        ],
    ),
]


def random_event(rng: random.Random) -> GameEvent:
    return rng.choice(EVENT_POOL)
