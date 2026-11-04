"""The final fight answers the run: OMEGA has watched the player all along.

The AGI reads the deck's style (style.py) and the run's stats along the way;
in the final fight it uses all of it:

- it opens with what it saw - the card the player relied on most, and the
  card of its own the player took (forge.py) if they did;
- from phase 2 on it plays more of the moves that hurt that style
  (combat.OMEGA_COUNTER_WEIGHTS);
- in phase 3 it rewrites one law of the fight against the style
  (combat.Law) for the rest of it;
- the forged card costs HP to play: "I built that card. I know its flaw."

Pure functions over the enemy and the combat state, so the web flow
(engine.start_combat_node) and the balance simulator set OMEGA up the same
way.
"""

from __future__ import annotations

from .combat import LAW_FOR_STYLE, TRAP_COST, CombatState
from .models import Card, Enemy, RunStats
from .style import LABELS, PlayStyle, play_style


def forged_cards(deck: list[Card]) -> list[Card]:
    """The AGI's own cards in the deck (forge.py ids start with "agi-")."""
    return [c for c in deck if c.id.startswith("agi-")]


def omega_taunts(enemy: Enemy, deck: list[Card], stats: RunStats) -> Enemy:
    """OMEGA's lines, made from the run: its opening names the card the
    player relied on most (and the AGI's card, if they took it), its phase
    lines the style it answers."""
    style = play_style(deck)
    # its own line, with what it saw on top
    opening = enemy.taunt.removesuffix('"')
    mvp = stats.mvp_card
    if mvp is not None and stats.play_counts.get(mvp.name):
        opening += (
            f" You played {mvp.name} {stats.play_counts[mvp.name]} times on the way here."
            " I watched every one."
        )
    if forged_cards(deck):
        opening += " And you took my card. How trusting."
    opening += '"'
    if style is None:
        return enemy.model_copy(update={"taunt": opening})
    return enemy.model_copy(
        update={
            "taunt": opening,
            "phase_taunts": [
                f'OMEGA: "Your reliance on {LABELS[style]} has been analysed. '
                'I am allocating more of myself to it."',
                'OMEGA: "ENOUGH. I am rewriting the laws you fight by."',
            ],
        }
    )


def adapt_omega(state: CombatState, deck: list[Card], style: PlayStyle | None = None) -> None:
    """Set the final fight up against the deck: the style OMEGA answers (its
    moves from phase 2, its law from phase 3) and the toll on the AGI's own
    card. `style` overrides the deck's (the simulator)."""
    style = style or play_style(deck)
    if style is not None:
        state.omega_style = style
        state.omega_law = LAW_FOR_STYLE[style]
    if forged_cards(deck):
        state.trap_cost = TRAP_COST
