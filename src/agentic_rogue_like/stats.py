"""The run summary's numbers (models.RunStats), kept as the run goes.

Nothing here feeds back into play. Fights count themselves on their
CombatState (combat.FightTally) and are folded in once they end
(record_fight); what changes outside a fight - cards gained, removed and
upgraded, credits earned and spent - is read off the run itself
(note_changes), so the shop, the rest site, events and rewards need no hook
of their own. Only interactive fights (engine.start_combat_node and on) are
counted: auto_resolve_combat keeps its CombatState to itself.
"""

from __future__ import annotations

import time

from .combat import CombatState, offer_combo
from .models import Card, CardType, Combo, KillingBlow, MapNode, NodeType, RunState, RunStatus


def begin(run: RunState) -> None:
    run.stats.started_at = time.time()
    _rebase(run)


def _rebase(run: RunState) -> None:
    run.stats.seen_deck = {c.id: c.upgraded for c in run.player.deck}
    run.stats.seen_gold = run.player.gold


def note_changes(run: RunState) -> None:
    """Count what changed in the deck and the credits since the last call.

    Cards are told apart by id, which an upgrade keeps (cards.upgrade_card).
    The start of the run (starter kit, the AGI's deal) shapes the deck the
    run begins with, so it only moves the baseline.
    """
    stats = run.stats
    if run.kit_offer is not None or run.agi_deals is not None:
        _rebase(run)
        return
    deck = {c.id: c.upgraded for c in run.player.deck}
    seen = stats.seen_deck
    stats.cards_added += sum(1 for card_id in deck if card_id not in seen)
    stats.cards_removed += sum(1 for card_id in seen if card_id not in deck)
    stats.cards_upgraded += sum(
        1 for card_id, upgraded in deck.items() if upgraded and seen.get(card_id) is False
    )
    gold = run.player.gold - stats.seen_gold
    if gold > 0:
        stats.credits_earned += gold
    else:
        stats.credits_spent -= gold
    _rebase(run)


def record_play(run: RunState, state: CombatState, card: Card, dealt: int) -> None:
    """A card was played (or queued) and its effect dealt `dealt` damage."""
    stats = run.stats
    stats.cards_played += 1
    count = stats.play_counts.get(card.name, 0) + 1
    stats.play_counts[card.name] = count
    mvp = stats.mvp_card
    if card.type is not CardType.GLITCH and (
        mvp is None or mvp.name == card.name or count > stats.play_counts.get(mvp.name, 0)
    ):
        stats.mvp_card = card
    if not state.program_mode:
        turn = state.tally.turn_combo or Combo(damage=0, runs=0, cards=[])
        state.tally.turn_combo = Combo(
            damage=turn.damage + dealt, runs=turn.runs + 1, cards=[*turn.cards, card.name]
        )


def close_turn(state: CombatState) -> None:
    """Classic play: the turn's cards are one combo, offered as the best."""
    tally = state.tally
    tally.best_combo = offer_combo(tally.best_combo, tally.turn_combo)
    tally.turn_combo = None


def record_fight(run: RunState, state: CombatState, node: MapNode, victory: bool) -> None:
    """Fold a finished fight into the run's stats - after engine._finish_combat,
    so a fight that ended the run also stamps its end."""
    close_turn(state)
    stats, tally = run.stats, state.tally
    stats.turns += state.turn
    stats.damage_dealt += tally.damage_dealt
    stats.damage_taken += tally.damage_taken
    stats.biggest_hit = max(stats.biggest_hit, tally.biggest_hit)
    stats.best_combo = offer_combo(stats.best_combo, tally.best_combo)
    if victory:
        stats.fights_won += 1
        stats.elites_defeated += node.type is NodeType.ELITE
        stats.bosses_defeated += node.type is NodeType.BOSS
    else:
        move = tally.killed_by or state.enemy.attack_name
        stats.killed_by = KillingBlow(enemy=state.enemy.name, move=move)
    if run.status is not RunStatus.ONGOING:
        stats.ended_at = time.time()
