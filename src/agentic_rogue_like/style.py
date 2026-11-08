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
    CONTROL_FLOW_TYPES,
    PERMANENT_CARD_TYPES,
    PROGRAM_ONLY_MOVES,
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
    PROGRAM = "program"  # control flow (program mode)


# A style needs this many chosen cards, and more than any other style, to count.
MIN_STYLE_CARDS = 3
# How much likelier an answering enemy or affix is than any other.
COUNTER_WEIGHT = 3
# Most enemies brace now and then; only a guard at least this strong (power,
# in percent of attack) answers a burst or attack-heavy deck.
STRONG_GUARD = 120

LABELS = {
    PlayStyle.PERMANENTS: "permanent cards",
    PlayStyle.GRAVEYARD: "your Graveyard",
    PlayStyle.ONE_SHOT: "one-shot cards",
    PlayStyle.AGGRO: "raw attacks",
    PlayStyle.TURTLE: "blocking",
    PlayStyle.MALWARE: "malware",
    PlayStyle.PROGRAM: "control flow",
}

# What answers each style: moves that hit where it hurts, and an elite affix.
COUNTER_MOVES: dict[PlayStyle, frozenset[MoveKind]] = {
    PlayStyle.PERMANENTS: frozenset({MoveKind.PURGE, MoveKind.LOCK}),
    PlayStyle.GRAVEYARD: frozenset({MoveKind.CORRUPT}),
    PlayStyle.ONE_SHOT: frozenset({MoveKind.DEFEND}),  # a strong guard soaks the burst
    PlayStyle.AGGRO: frozenset({MoveKind.DEFEND}),  # ...or the attack pile
    PlayStyle.TURTLE: frozenset({MoveKind.INFECT}),  # Malware ignores block
    PlayStyle.MALWARE: frozenset(),
    # The game's own program moves answer a program (see answers) - no move
    # the pool or the agent could give.
    PlayStyle.PROGRAM: frozenset(),
}
COUNTER_AFFIX: dict[PlayStyle, Affix | None] = {
    PlayStyle.PERMANENTS: None,
    PlayStyle.GRAVEYARD: None,
    PlayStyle.ONE_SHOT: Affix.ARMORED,
    PlayStyle.AGGRO: Affix.THORNY,
    PlayStyle.TURTLE: Affix.ENRAGED,  # punishes a long, stalled fight
    PlayStyle.MALWARE: Affix.REGENERATING,  # heals off what Malware takes
    PlayStyle.PROGRAM: None,
}


def card_styles(card: Card) -> set[PlayStyle]:
    """Every style a card feeds - one card can feed several specific ones,
    and only a card with none of those counts as aggro or turtle (unless it
    is a bridge that names them)."""
    styles: set[PlayStyle] = set()
    if card.type in PERMANENT_CARD_TYPES or card.scaling in (Scaling.PERMANENT, Scaling.EMPTY_SLOT):
        styles.add(PlayStyle.PERMANENTS)
    if card.discard_cost or card.scaling is Scaling.GRAVEYARD or card.type is CardType.RETRIEVE:
        styles.add(PlayStyle.GRAVEYARD)
    if card.exhaust or card.banish or card.scaling is Scaling.BANISHED:
        styles.add(PlayStyle.ONE_SHOT)
    if card.applies is not None or card.scaling is Scaling.MALWARE:
        styles.add(PlayStyle.MALWARE)
    if card.type in CONTROL_FLOW_TYPES:
        styles.add(PlayStyle.PROGRAM)
    # the cards that care where their line stands only make sense in a program
    if card.halts or card.scaling in (Scaling.LINES, Scaling.FIRST_LINE, Scaling.LAST_LINE):
        styles.add(PlayStyle.PROGRAM)
    # The bridges (cards.py) feed both styles they join.
    if card.banish_damage or card.type is CardType.RECYCLE:
        styles.add(PlayStyle.ONE_SHOT)
    if card.type is CardType.RECYCLE:
        styles.add(PlayStyle.GRAVEYARD)
    if card.type is CardType.QUARANTINE:
        styles |= {PlayStyle.MALWARE, PlayStyle.TURTLE}
    if card.scaling is Scaling.BLOCK:
        styles |= {PlayStyle.AGGRO, PlayStyle.TURTLE}
    if card.type is CardType.GUARD:
        styles.add(PlayStyle.TURTLE)
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
    if style is PlayStyle.PROGRAM:
        # program runs give every regular enemy a program move, the one
        # that hurts this deck most and more often against this style
        # (enemies.with_program_move)
        return any(m.kind in PROGRAM_ONLY_MOVES for m in enemy.moves)
    if enemy.affix is not None and enemy.affix is COUNTER_AFFIX[style]:
        return True
    return any(
        m.kind in COUNTER_MOVES[style]
        and (m.kind is not MoveKind.DEFEND or m.power >= STRONG_GUARD)
        for m in enemy.moves
    )


# What program runs give regular enemies (enemies.with_program_move).
PROGRAM_MOVES: tuple[MoveKind, ...] = (
    MoveKind.INTERRUPT,
    MoveKind.COLLECT,
    MoveKind.RACE,
    MoveKind.LEAK,
)


def program_counter(deck: list[Card]) -> MoveKind:
    """The program move that hurts this deck most, read from the cards the
    player chose: a garbage collector against a long program or one that
    saves its best for last, a memory leak against a strong first line, a
    race condition against control flow that steers the line after it, an
    interrupt against everything else that builds a long chain."""
    scores = dict.fromkeys(PROGRAM_MOVES, 0)
    for card in deck:
        if card.rarity is Rarity.STARTER:
            continue
        if card.scaling in (Scaling.LINES, Scaling.LAST_LINE) or card.halts:
            scores[MoveKind.COLLECT] += 1
        elif card.scaling is Scaling.FIRST_LINE:
            scores[MoveKind.LEAK] += 1
        elif card.type in (CardType.FORK, CardType.IF_WOUNDED, CardType.PIPE):
            scores[MoveKind.RACE] += 1
        elif card.type in CONTROL_FLOW_TYPES:
            scores[MoveKind.INTERRUPT] += 1
    # ties go to the first in PROGRAM_MOVES - the interrupt
    return max(PROGRAM_MOVES, key=lambda kind: scores[kind])


# How the encounter agent should picture an enemy the game arms with each
# program move - it can't give program moves itself, but it can name and
# describe the enemy for the job.
_PROGRAM_ROLES = {
    MoveKind.INTERRUPT: "an interrupter that cuts running code short",
    MoveKind.COLLECT: "a garbage collector that sweeps away the end of a long program",
    MoveKind.RACE: "a race condition that scrambles the order things run in",
    MoveKind.LEAK: "a memory leak that clogs up the first line it touches",
}

# The AGI's line for an enemy armed against the player's program.
_PROGRAM_TAUNTS = {
    MoveKind.INTERRUPT: "Your control flow has been analysed. Interrupt handler installed.",
    MoveKind.COLLECT: "Your programs run long. Garbage collection scheduled.",
    MoveKind.RACE: "Your Forks depend on order. Let us see how they handle a race.",
    MoveKind.LEAK: "You always open strong. That first line will leak.",
}


def key_cards(deck: list[Card], style: PlayStyle, limit: int = 3) -> list[str]:
    """The chosen cards that feed `style` most, by how many copies - what the
    encounter agent hears the player leans on."""
    counts: dict[str, int] = {}
    for card in deck:
        if card.rarity is not Rarity.STARTER and style in card_styles(card):
            name = card.name.rstrip("+")
            counts[name] = counts.get(name, 0) + 1
    return [name for name, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:limit]]


def agent_hint(style: PlayStyle | None, deck: list[Card] | None = None) -> str | None:
    """A sentence for the encounter agent's prompt, or None without a style.
    A program style gets no move set to ask for - the game arms the enemy
    itself (enemies.with_program_move) - but the agent hears which program
    move, so it can name and describe the enemy for that role. With the
    deck, it also hears the cards the style rests on."""
    if style is None:
        return None
    cards = key_cards(deck, style) if deck else []
    named = f" Their key cards: {', '.join(cards)}." if cards else ""
    if style is PlayStyle.PROGRAM:
        role = _PROGRAM_ROLES[program_counter(deck or [])]
        return (
            f"The player's deck leans on {LABELS[style]}.{named} The game arms this enemy "
            f"against their program as {role}: make its name and description fit that "
            f"role, but give it only the usual moves."
        )
    kinds = sorted(k.value for k in COUNTER_MOVES[style])
    if kinds == ["defend"]:
        kinds = [f"defend (power {STRONG_GUARD}+)"]
    moves = f" - for example with {' or '.join(kinds)} moves" if kinds else ""
    return (
        f"The player's deck leans on {LABELS[style]}; give this enemy a move set that "
        f"pressures that{moves}.{named}"
    )


def taunt(style: PlayStyle, enemy: Enemy | None = None) -> str:
    """The AGI's line when an enemy it picked answers the player's style -
    against a program, the one for the program move it armed the enemy with."""
    if style is PlayStyle.PROGRAM and enemy is not None:
        for move in enemy.moves:
            if move.kind in _PROGRAM_TAUNTS:
                return f'AGI: "{_PROGRAM_TAUNTS[move.kind]}"'
    return f'AGI: "Your reliance on {LABELS[style]} has been analysed. Adapting."'
