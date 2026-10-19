"""How the player plays, read from their deck - and how the AGI answers it.

The AGI in the story learns from Dr. Chronos; in the game it reads the cards
the player chose to add (rewards, shop, events - never the starter deck) and,
once one style clearly dominates, prefers enemies, moves and elite affixes
that pressure it. Prefers, never forces: an answer is only weighted up
(COUNTER_WEIGHT) among enemies of the same tier, and every enemy keeps its
threat (threat.py), so adapting changes what a fight asks of the player,
not how hard it is.
"""

from __future__ import annotations

from enum import StrEnum

from .models import (
    PERMANENT_CARD_TYPES,
    Affix,
    Card,
    CardType,
    Enemy,
    MoveKind,
    Rarity,
    Scaling,
)


class PlayStyle(StrEnum):
    PERMANENTS = "permanents"  # builds the field up
    GRAVEYARD = "graveyard"  # discards and digs through the graveyard
    ONE_SHOT = "one_shot"  # big one-shot cards, banished after use
    AGGRO = "aggro"  # piles on attacks
    TURTLE = "turtle"  # blocks, armor and heals
    MALWARE = "malware"  # statuses, above all Malware


# A style needs this many chosen cards, and more than any other style, to count.
MIN_STYLE_CARDS = 3
# How much likelier an answering enemy or affix is than any other.
COUNTER_WEIGHT = 3
# Most enemies brace now and then; only a guard at least this strong (power,
# in percent of attack) answers a burst or attack-heavy deck.
STRONG_GUARD = 120

LABELS = {
    PlayStyle.PERMANENTS: "permanent cards",
    PlayStyle.GRAVEYARD: "your graveyard",
    PlayStyle.ONE_SHOT: "one-shot cards",
    PlayStyle.AGGRO: "raw attacks",
    PlayStyle.TURTLE: "blocking",
    PlayStyle.MALWARE: "malware",
}

# What answers each style: moves that hit where it hurts, and an elite affix.
COUNTER_MOVES: dict[PlayStyle, frozenset[MoveKind]] = {
    PlayStyle.PERMANENTS: frozenset({MoveKind.PURGE, MoveKind.LOCK}),
    PlayStyle.GRAVEYARD: frozenset({MoveKind.CORRUPT}),
    PlayStyle.ONE_SHOT: frozenset({MoveKind.DEFEND}),  # a strong guard soaks the burst
    PlayStyle.AGGRO: frozenset({MoveKind.DEFEND}),  # ...or the attack pile
    PlayStyle.TURTLE: frozenset({MoveKind.INFECT}),  # Malware ignores block
    PlayStyle.MALWARE: frozenset(),
}
COUNTER_AFFIX: dict[PlayStyle, Affix | None] = {
    PlayStyle.PERMANENTS: None,
    PlayStyle.GRAVEYARD: None,
    PlayStyle.ONE_SHOT: Affix.ARMORED,
    PlayStyle.AGGRO: Affix.THORNY,
    PlayStyle.TURTLE: Affix.ENRAGED,  # punishes a long, stalled fight
    PlayStyle.MALWARE: Affix.REGENERATING,  # heals off what Malware takes
}


def card_styles(card: Card) -> set[PlayStyle]:
    """Every style a card feeds - one card can feed several specific ones,
    and only a card with none of those counts as aggro or turtle."""
    styles: set[PlayStyle] = set()
    if card.type in PERMANENT_CARD_TYPES or card.scaling in (Scaling.PERMANENT, Scaling.EMPTY_SLOT):
        styles.add(PlayStyle.PERMANENTS)
    if card.discard_cost or card.scaling is Scaling.GRAVEYARD or card.type is CardType.RETRIEVE:
        styles.add(PlayStyle.GRAVEYARD)
    if card.exhaust or card.scaling is Scaling.BANISHED:
        styles.add(PlayStyle.ONE_SHOT)
    if card.applies is not None or card.scaling is Scaling.MALWARE:
        styles.add(PlayStyle.MALWARE)
    # Plain attacks and plain defence only - a Trojan is a malware card that
    # happens to hit, not an aggro one, or every specific style would tie.
    if not styles and card.type is CardType.ATTACK:
        styles.add(PlayStyle.AGGRO)
    if not styles and card.type in (CardType.BLOCK, CardType.HEAL, CardType.ARMOR):
        styles.add(PlayStyle.TURTLE)
    return styles


def style_counts(deck: list[Card]) -> dict[PlayStyle, int]:
    """How many of the cards the player chose (not the starter deck) feed each style."""
    counts = dict.fromkeys(PlayStyle, 0)
    for card in deck:
        if card.rarity is not Rarity.STARTER:
            for style in card_styles(card):
                counts[style] += 1
    return counts


def play_style(deck: list[Card]) -> PlayStyle | None:
    """The style the deck clearly leans on, or None while it doesn't yet."""
    ranked = sorted(style_counts(deck).items(), key=lambda kv: kv[1], reverse=True)
    (top, top_count), (_, runner_up) = ranked[0], ranked[1]
    if top_count < MIN_STYLE_CARDS or top_count == runner_up:
        return None
    return top


def answers(enemy: Enemy, style: PlayStyle | None) -> bool:
    """Whether the enemy's moves or affix pressure `style`."""
    if style is None:
        return False
    if enemy.affix is not None and enemy.affix is COUNTER_AFFIX[style]:
        return True
    return any(
        m.kind in COUNTER_MOVES[style]
        and (m.kind is not MoveKind.DEFEND or m.power >= STRONG_GUARD)
        for m in enemy.moves
    )


def agent_hint(style: PlayStyle | None) -> str | None:
    """A sentence for the encounter agent's prompt, or None without a style."""
    if style is None:
        return None
    kinds = sorted(k.value for k in COUNTER_MOVES[style])
    if kinds == ["defend"]:
        kinds = [f"defend (power {STRONG_GUARD}+)"]
    moves = f" - for example with {' or '.join(kinds)} moves" if kinds else ""
    return (
        f"The player's deck leans on {LABELS[style]}; give this enemy a move set that "
        f"pressures that{moves}."
    )


def taunt(style: PlayStyle) -> str:
    """The AGI's line when an enemy it picked answers the player's style."""
    return f'AGI: "Your reliance on {LABELS[style]} has been analysed. Adapting."'
