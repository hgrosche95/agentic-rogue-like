"""Deck-based combat: draw a hand, play cards onto a 5-slot field, end the turn.

No energy resource - the field itself is the constraint. Action cards
(Strike, Defend, ...) need an empty slot to be played into, resolve
immediately, and go to the discard pile; permanent cards occupy the slot
they were played in for the rest of the fight instead, passively affecting
play based on where they sit (see PERMANENT_CARD_TYPES in models.py and
_field_modifiers below). A field full of permanents means no empty slot
left for anything else - Final Strike existing as an action card is the
game's own answer to that self-inflicted dead end, not a bug: destroy every
permanent at once, cash them in for damage, get the field back.

Two ways to drive this engine:
- step by step (start_combat / play_card / end_turn) - what the web API
  calls, one HTTP request per action, for real interactive play;
- auto_resolve_combat() - plays a full fight in one call with a simple
  bot (dump the hand into empty slots, then end the turn) so cli.py and the
  test suite stay playable end-to-end without their own card-picking UI.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, Field

from .models import PERMANENT_CARD_TYPES, Card, CardType, Enemy, PlayerState

HAND_SIZE = 5
FIELD_SIZE = 5
MAX_AUTO_TURNS = 50


class CombatState(BaseModel):
    enemy: Enemy
    enemy_hp: int
    draw_pile: list[Card]
    hand: list[Card]
    discard_pile: list[Card]
    field: list[Card | None] = Field(default_factory=lambda: [None] * FIELD_SIZE)
    player_block: int = 0


def _draw(state: CombatState, count: int, rng: random.Random) -> None:
    for _ in range(count):
        if not state.draw_pile:
            if not state.discard_pile:
                return  # deck fully exhausted - nothing left to draw
            state.draw_pile, state.discard_pile = state.discard_pile, []
            rng.shuffle(state.draw_pile)
        state.hand.append(state.draw_pile.pop())


def _target_hand_size(state: CombatState) -> int:
    draw_bonus = sum(c.value for c in state.field if c and c.type is CardType.DRAW_BONUS)
    return HAND_SIZE + draw_bonus


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

    if card.type in PERMANENT_CARD_TYPES:
        state.field[slot_index] = card
        return f"You play {card.name} in slot {slot_index + 1} - it stays on the field."

    # Action card: multiplier/recycling are read from the field *before* the
    # effect runs, so e.g. Final Strike destroying the very Amplifier/
    # Recycling permanent it benefited from still counts that benefit.
    multiplier = _amplifier_multiplier(state, slot_index)
    recycles = _recycles(state, slot_index)
    line = _apply_action_effect(state, card, multiplier, player)

    if recycles:
        state.draw_pile.append(card)
        rng.shuffle(state.draw_pile)
        line += " It's recycled straight back into the deck."
    else:
        state.discard_pile.append(card)

    return line


def _apply_action_effect(
    state: CombatState, card: Card, multiplier: float, player: PlayerState
) -> str:
    if card.type is CardType.ATTACK:
        damage = round((card.value + player.attack) * multiplier)
        state.enemy_hp = max(state.enemy_hp - damage, 0)
        return (
            f"You play {card.name}, dealing {damage} damage. "
            f"{state.enemy.name} at {state.enemy_hp} HP."
        )

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
    destroyed = sum(1 for c in state.field if c is not None)
    state.field = [None] * FIELD_SIZE
    damage = round(card.value * destroyed * multiplier)
    state.enemy_hp = max(state.enemy_hp - damage, 0)
    return (
        f"You play {card.name}, destroying {destroyed} permanent card(s) for "
        f"{damage} damage. {state.enemy.name} at {state.enemy_hp} HP."
    )


def end_turn(state: CombatState, player: PlayerState, rng: random.Random) -> list[str]:
    log: list[str] = []

    armor = sum(1 for c in state.field if c is not None and c.type is CardType.ARMOR)
    reduction = state.player_block + armor
    raw_damage = state.enemy.attack + rng.randint(1, 6)
    blocked = min(raw_damage, reduction)
    taken = raw_damage - blocked
    player.hp = max(player.hp - taken, 0)

    if blocked > 0:
        armor_note = f" (includes {armor} armor)" if armor else ""
        log.append(
            f"{state.enemy.name} uses {state.enemy.attack_name}. "
            f"You block {blocked}{armor_note} and take {taken} damage. You are at {player.hp} HP."
        )
    else:
        log.append(
            f"{state.enemy.name} uses {state.enemy.attack_name} for {taken} damage. "
            f"You are at {player.hp} HP."
        )

    state.player_block = 0
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
        while state.hand:
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
