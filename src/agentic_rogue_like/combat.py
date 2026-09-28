"""Deck-based combat: draw a hand, play cards onto a 5-slot field, end the turn.

No energy resource - the field itself is the constraint. Action cards
(Strike, Defend, ...) need an empty slot to be played into, resolve
immediately, and go to the discard pile; permanent cards occupy the slot
they were played in for the rest of the fight instead, passively affecting
play based on where they sit (see PERMANENT_CARD_TYPES in models.py and
_field_modifiers below). A field full of permanents means no empty slot
left for anything else - Final Strike existing as an action card is the
game's own answer to that self-inflicted dead end, not a bug: destroy every
permanent at once, cash them in for damage, get the field back. Destroyed
permanents go to the banished pile - gone for the rest of the fight, unlike
discarded action cards which can be reshuffled back in.

The enemy telegraphs its next move a turn ahead (an "intent": either attack
for its attack stat, or brace for the same amount of block) so playing a
card is an informed choice, not a guess.

Two ways to drive this engine:
- step by step (start_combat / play_card / end_turn) - what the web API
  calls, one HTTP request per action, for real interactive play;
- auto_resolve_combat() - plays a full fight in one call with a simple
  bot (dump the hand into empty slots, then end the turn) so cli.py and the
  test suite stay playable end-to-end without their own card-picking UI.
"""

from __future__ import annotations

import random
from enum import StrEnum

from pydantic import BaseModel, Field

from .models import PERMANENT_CARD_TYPES, Card, CardType, Enemy, PlayerState, Scaling

HAND_SIZE = 5
FIELD_SIZE = 5
MAX_AUTO_TURNS = 50
# Bots stop playing after this many cards in one turn - a backstop so a
# card combo nobody foresaw can never hang the simulator or the tests.
MAX_AUTO_PLAYS_PER_TURN = 30
ENEMY_DEFEND_CHANCE = 0.3


class EnemyIntentType(StrEnum):
    ATTACK = "attack"
    DEFEND = "defend"


class CombatState(BaseModel):
    enemy: Enemy
    enemy_hp: int
    enemy_block: int = 0
    enemy_intent: EnemyIntentType = EnemyIntentType.ATTACK
    draw_pile: list[Card]
    hand: list[Card]
    discard_pile: list[Card]
    banished_pile: list[Card] = Field(default_factory=list)
    field: list[Card | None] = Field(default_factory=lambda: [None] * FIELD_SIZE)
    player_block: int = 0


def _draw(state: CombatState, count: int, rng: random.Random) -> int:
    drawn = 0
    for _ in range(count):
        if not state.draw_pile:
            if not state.discard_pile:
                break  # deck fully exhausted - nothing left to draw
            state.draw_pile, state.discard_pile = state.discard_pile, []
            rng.shuffle(state.draw_pile)
        state.hand.append(state.draw_pile.pop())
        drawn += 1
    return drawn


def _target_hand_size(state: CombatState) -> int:
    draw_bonus = sum(c.value for c in state.field if c and c.type is CardType.DRAW_BONUS)
    return HAND_SIZE + draw_bonus


def _roll_enemy_intent(rng: random.Random) -> EnemyIntentType:
    return EnemyIntentType.DEFEND if rng.random() < ENEMY_DEFEND_CHANCE else EnemyIntentType.ATTACK


def _damage_enemy(state: CombatState, damage: int) -> tuple[int, int]:
    """Apply damage to the enemy's block first, then its HP. Returns (absorbed, dealt)."""
    absorbed = min(damage, state.enemy_block)
    state.enemy_block -= absorbed
    dealt = damage - absorbed
    state.enemy_hp = max(state.enemy_hp - dealt, 0)
    return absorbed, dealt


def start_combat(
    deck: list[Card], enemy: Enemy, rng: random.Random
) -> tuple[CombatState, list[str]]:
    """Shuffle a *copy* of `deck` into the draw pile and draw an opening hand.

    `deck` (the player's owned cards) is read, never mutated - the piles
    below are the combat-scoped working copy that gets folded back once the
    fight ends.
    """
    draw_pile = list(deck)
    rng.shuffle(draw_pile)
    state = CombatState(
        enemy=enemy,
        enemy_hp=enemy.hp,
        enemy_intent=_roll_enemy_intent(rng),
        draw_pile=draw_pile,
        hand=[],
        discard_pile=[],
        field=[None] * FIELD_SIZE,
    )
    _draw(state, HAND_SIZE, rng)
    return state, [f"A {enemy.name} appears! ({enemy.hp} HP)"]


def _amplifier_multiplier(state: CombatState, slot_index: int) -> float:
    boosts = sum(
        1
        for i, c in enumerate(state.field)
        if c is not None and c.type is CardType.AMPLIFIER and i < slot_index
    )
    return 1 + 0.25 * boosts


def _recycles(state: CombatState, slot_index: int) -> bool:
    return any(
        c is not None and c.type is CardType.RECYCLING and i > slot_index
        for i, c in enumerate(state.field)
    )


def play_card(
    state: CombatState, hand_index: int, slot_index: int, player: PlayerState, rng: random.Random
) -> str:
    if not 0 <= hand_index < len(state.hand):
        raise ValueError(f"hand_index {hand_index} is out of range")
    if not 0 <= slot_index < FIELD_SIZE:
        raise ValueError(f"slot_index {slot_index} is out of range")
    if state.field[slot_index] is not None:
        raise ValueError(f"slot {slot_index} is occupied")

    card = state.hand.pop(hand_index)
    # The cost is paid before anything else, so a card like Memory Dump can't
    # throw away the very cards it is about to draw.
    cost_line = _pay_discard_cost(state, card, rng)

    if card.type in PERMANENT_CARD_TYPES:
        state.field[slot_index] = card
        return cost_line + f"You play {card.name} in slot {slot_index + 1} - it stays on the field."

    # Action card: multiplier/recycling are read from the field *before* the
    # effect runs, so e.g. Final Strike destroying the very Amplifier/
    # Recycling permanent it benefited from still counts that benefit.
    multiplier = _amplifier_multiplier(state, slot_index)
    recycles = _recycles(state, slot_index)
    line = cost_line + _apply_action_effect(state, card, multiplier, player, rng)

    if card.exhaust:
        # One-shot beats Recycling - otherwise a Recycling permanent would
        # turn every one-shot card into an infinitely reusable one.
        state.banished_pile.append(card)
        line += " It's used up and banished for the rest of the fight."
    elif recycles:
        state.draw_pile.append(card)
        rng.shuffle(state.draw_pile)
        line += " It's recycled straight back into the deck."
    else:
        state.discard_pile.append(card)

    if card.draw:
        drawn = _draw(state, card.draw, rng)
        line += f" You draw {drawn} card(s)."

    return line


def _pay_discard_cost(state: CombatState, card: Card, rng: random.Random) -> str:
    if card.discard_cost <= 0 or not state.hand:
        return ""
    count = min(card.discard_cost, len(state.hand))
    discarded = rng.sample(state.hand, count)
    for c in discarded:
        state.hand.remove(c)
        state.discard_pile.append(c)
    names = ", ".join(c.name for c in discarded)
    return f"You discard {names}. "


def permanent_count(state: CombatState) -> int:
    return sum(1 for c in state.field if c is not None)


def attack_damage(
    state: CombatState, card: Card, player: PlayerState, multiplier: float = 1.0
) -> int:
    """Damage of one hit of an ATTACK card - also what the UI/bots preview."""
    base = card.value + player.attack
    if card.scaling is Scaling.PERMANENT:
        base += card.scale_value * permanent_count(state)
    elif card.scaling is Scaling.GRAVEYARD:
        base += card.scale_value * len(state.discard_pile)
    elif card.scaling is Scaling.BANISHED:
        base += card.scale_value * len(state.banished_pile)
    boost = sum(c.value for c in state.field if c and c.type is CardType.DAMAGE_BOOST)
    base += boost * permanent_count(state)
    return round(base * multiplier)


def _apply_action_effect(
    state: CombatState, card: Card, multiplier: float, player: PlayerState, rng: random.Random
) -> str:
    if card.type is CardType.ATTACK:
        damage = attack_damage(state, card, player, multiplier)
        hits = max(card.hits, 1)
        absorbed = dealt = 0
        for _ in range(hits):
            a, d = _damage_enemy(state, damage)
            absorbed += a
            dealt += d
        what = f"{hits}x {damage} damage" if hits > 1 else f"{damage} damage"
        if absorbed > 0:
            return (
                f"You play {card.name}, dealing {what} - {state.enemy.name}'s "
                f"block absorbs {absorbed}, {dealt} gets through. {state.enemy.name} at "
                f"{state.enemy_hp} HP."
            )
        return f"You play {card.name}, dealing {what}. {state.enemy.name} at {state.enemy_hp} HP."

    if card.type is CardType.DRAW:
        drawn = _draw(state, card.value, rng)
        return f"You play {card.name}, drawing {drawn} card(s)."

    if card.type is CardType.RETRIEVE:
        returned = _take_recent(state.discard_pile, card.value)
        state.hand.extend(returned)
        return f"You play {card.name}, pulling {_names(returned)} back from the graveyard."

    if card.type is CardType.RESTORE:
        # Restore cards never restore each other - two of them could
        # otherwise fetch one another back forever.
        restorable = [c for c in state.banished_pile if c.type is not CardType.RESTORE]
        returned = _take_recent(restorable, card.value)
        for c in returned:
            state.banished_pile.remove(c)
        state.hand.extend(returned)
        return f"You play {card.name}, restoring {_names(returned)} from the banished pile."

    if card.type is CardType.BLOCK:
        amount = round(card.value * multiplier)
        state.player_block += amount
        return f"You play {card.name}, gaining {amount} block."

    if card.type is CardType.HEAL:
        amount = round(card.value * multiplier)
        healed = min(amount, player.max_hp - player.hp)
        player.hp += healed
        return f"You play {card.name}, healing {healed} HP."

    # FINAL_STRIKE
    destroyed = [c for c in state.field if c is not None]
    state.banished_pile.extend(destroyed)
    state.field = [None] * FIELD_SIZE
    damage = round(card.value * len(destroyed) * multiplier)
    absorbed, dealt = _damage_enemy(state, damage)
    return (
        f"You play {card.name}, destroying {len(destroyed)} permanent card(s) for "
        f"{damage} damage. {state.enemy.name} at {state.enemy_hp} HP."
    )


def _take_recent(pile: list[Card], count: int) -> list[Card]:
    """Pop the `count` most recently added cards - the top of the pile."""
    count = max(0, min(count, len(pile)))
    taken = pile[len(pile) - count :]
    del pile[len(pile) - count :]
    return taken


def _names(cards: list[Card]) -> str:
    return ", ".join(c.name for c in cards) if cards else "nothing"


def end_turn(state: CombatState, player: PlayerState, rng: random.Random) -> list[str]:
    log: list[str] = []

    # Permanents that act on their own resolve before the enemy does, so a
    # Daemon can finish a fight and a Mainframe's block is up in time.
    turret = sum(c.value for c in state.field if c and c.type is CardType.TURRET)
    if turret:
        absorbed, dealt = _damage_enemy(state, turret)
        log.append(
            f"Your daemons hit {state.enemy.name} for {dealt} damage"
            + (f" ({absorbed} blocked)" if absorbed else "")
            + f". {state.enemy.name} at {state.enemy_hp} HP."
        )
        if state.enemy_hp <= 0:
            return log
    fortify = sum(c.value for c in state.field if c and c.type is CardType.FORTIFY)
    if fortify:
        gained = fortify * permanent_count(state)
        state.player_block += gained
        log.append(f"Your mainframe raises {gained} block.")

    if state.enemy_intent is EnemyIntentType.DEFEND:
        state.enemy_block += state.enemy.attack
        log.append(f"{state.enemy.name} braces itself, gaining {state.enemy.attack} block.")
    else:
        armor = sum(1 for c in state.field if c is not None and c.type is CardType.ARMOR)
        reduction = state.player_block + armor
        raw_damage = state.enemy.attack + rng.randint(1, 6)
        blocked = min(raw_damage, reduction)
        taken = raw_damage - blocked
        player.hp = max(player.hp - taken, 0)

        if blocked > 0:
            armor_note = f" (includes {armor} armor)" if armor else ""
            log.append(
                f"{state.enemy.name} uses {state.enemy.attack_name}. You block "
                f"{blocked}{armor_note} and take {taken} damage. You are at {player.hp} HP."
            )
        else:
            log.append(
                f"{state.enemy.name} uses {state.enemy.attack_name} for {taken} damage. "
                f"You are at {player.hp} HP."
            )

    state.player_block = 0
    state.enemy_intent = _roll_enemy_intent(rng)
    # Unplayed hand cards carry over to next turn - only top up to the
    # target hand size instead of discarding and redrawing from scratch.
    _draw(state, max(0, _target_hand_size(state) - len(state.hand)), rng)
    return log


def auto_resolve_combat(
    deck: list[Card], enemy: Enemy, player: PlayerState, rng: random.Random
) -> tuple[bool, list[str]]:
    """Play out a full fight non-interactively: dump the hand into the first
    empty field slot each turn, then end the turn, until someone runs out of HP.
    """
    state, log = start_combat(deck, enemy, rng)

    for _ in range(MAX_AUTO_TURNS):
        if state.enemy_hp <= 0 or player.hp <= 0:
            break
        for _ in range(MAX_AUTO_PLAYS_PER_TURN):
            if not state.hand:
                break
            empty_slot = next((i for i, c in enumerate(state.field) if c is None), None)
            if empty_slot is None:
                break
            log.append(play_card(state, 0, empty_slot, player, rng))
            if state.enemy_hp <= 0:
                break
        if state.enemy_hp <= 0:
            break
        log.extend(end_turn(state, player, rng))

    return state.enemy_hp <= 0, log
