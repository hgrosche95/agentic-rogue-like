"""The run summary's numbers (models.RunStats), kept as the run goes.

Nothing here feeds back into play. Fights count themselves on their
CombatState (combat.FightTally) and are folded in once they end:
interactively (record_fight), or in one go, where the caller hands
auto_resolve_combat the tally to count into and folds it itself
(fold_tally, engine.resolve_node). What changes outside a fight - cards
gained, removed and upgraded, credits earned and spent - is read off the run
itself (note_changes), so the shop, the rest site, events and rewards need no
hook of their own.

TIERS and tier_for - which enemy tier a room is scaled for - live here too,
so the run's stats and `balance-sim` (balance_sim.py) read one definition.
"""

from __future__ import annotations

import time

from .combat import CombatState, FightTally, offer_combo
from .enemies import FINAL_BOSS_ID, tier_floor
from .map_gen import NUM_FLOORS
from .models import (
    Card,
    CardType,
    Combo,
    DefeatedEnemy,
    Enemy,
    KillingBlow,
    MapNode,
    NodeType,
    RunState,
    RunStatus,
)
from .nemesis import spec_from_enemy

# The tiers a fight is scaled for - the same names the balance simulator's
# enemy budgets use (agent/budgets.py).
TIERS = ("early", "mid", "elite", "boss")


def tier_for(floor: int, node_type: NodeType, act: int = 1) -> str:
    """The tier an enemy in this room is scaled for (see enemies.escalate)."""
    if node_type is NodeType.BOSS:
        return "boss"
    if node_type is NodeType.ELITE:
        return "elite"
    return "early" if tier_floor(floor, NUM_FLOORS, act) < NUM_FLOORS // 2 else "mid"


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


def close_turn(tally: FightTally) -> None:
    """Classic play: the turn's cards are one combo, offered as the best."""
    tally.best_combo = offer_combo(tally.best_combo, tally.turn_combo)
    tally.turn_combo = None


def fold_tally(
    run: RunState, tally: FightTally, node: MapNode, enemy: Enemy, victory: bool
) -> None:
    """Fold a finished fight's tally into the run's stats.

    A won fight names its enemy in `defeated` - with the tier the room was
    scaled for and the act it was fought in; a lost one names its killer in
    `killed_by` instead. Never both.

    Only the auto path counts its plays per card on the tally (interactive
    play goes through record_play), so its card_plays join play_counts.

    The run's end stamp is not set here - see stamp_end."""
    close_turn(tally)
    stats = run.stats
    stats.turns += tally.turns
    stats.damage_dealt += tally.damage_dealt
    stats.damage_taken += tally.damage_taken
    stats.biggest_hit = max(stats.biggest_hit, tally.biggest_hit)
    stats.best_combo = offer_combo(stats.best_combo, tally.best_combo)
    for name, count in tally.card_plays.items():
        stats.play_counts[name] = stats.play_counts.get(name, 0) + count
    if victory:
        stats.fights_won += 1
        stats.elites_defeated += node.type is NodeType.ELITE
        stats.bosses_defeated += node.type is NodeType.BOSS
        stats.defeated.append(
            DefeatedEnemy(
                name=enemy.name,
                tier=tier_for(node.floor, node.type, run.act),
                act=run.act,
            )
        )
    else:
        move = tally.killed_by or enemy.attack_name
        final_boss = enemy.id == FINAL_BOSS_ID
        stats.killed_by = KillingBlow(
            enemy=enemy.name,
            move=move,
            enemy_max_hp=enemy.hp,
            enemy_attack=enemy.attack,
            final_boss=final_boss,
            nemesis=spec_from_enemy(enemy, final_boss),
        )


def stamp_end(run: RunState) -> None:
    """Stamp the run's end time - once the status left ONGOING, first call wins.

    Run it after the transition (engine._finish_combat), not from fold_tally:
    the auto path folds while the run is still ONGOING."""
    if run.status is not RunStatus.ONGOING and run.stats.ended_at is None:
        run.stats.ended_at = time.time()


def record_fight(run: RunState, state: CombatState, node: MapNode, victory: bool) -> None:
    """Fold a finished interactive fight into the run's stats.

    Called after engine._finish_combat: the fight's turn count is the state's
    own, and stamp_end marks a run this fight ended."""
    state.tally.turns = state.turn
    fold_tally(run, state.tally, node, state.enemy, victory)
    stamp_end(run)
