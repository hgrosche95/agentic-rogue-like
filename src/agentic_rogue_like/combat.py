"""Deck-based combat: draw a hand, play cards onto a 5-slot field, end the turn.

A fight opens with HAND_SIZE cards; every turn end draws CARDS_PER_TURN more
(plus Prefetch bonuses) on top of whatever is still in hand, after the hand
has been discarded down to MAX_HAND_SIZE.

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

Bosses fight with a bigger move set (see _roll_boss_intent): a three-hit
barrage, a charge-up that telegraphs a crushing overload blow on the
following turn, and - once they drop to half HP and enter phase 2, gaining
strength and block - a purge that destroys the rightmost permanent on the
field.

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

from .artifacts import every_nth_turn, heal, total
from .models import PERMANENT_CARD_TYPES, Artifact, Card, CardType, Enemy, PlayerState, Scaling

HAND_SIZE = 5  # opening hand
CARDS_PER_TURN = 3  # drawn at the end of every turn, on top of what's left
MAX_HAND_SIZE = 8  # discard down to this at the end of the turn
FIELD_SIZE = 5
MAX_AUTO_TURNS = 50
# Bots stop playing after this many cards in one turn - a backstop so a
# card combo nobody foresaw can never hang the simulator or the tests.
MAX_AUTO_PLAYS_PER_TURN = 30
ENEMY_DEFEND_CHANCE = 0.3

# Boss moves, all scaled off its attack stat (plus phase-2 strength).
BARRAGE_HITS = 3
BARRAGE_FACTOR = 0.25  # damage per barrage hit, before its d3
OVERLOAD_FACTOR = 1.4  # the charged blow, before its d6
CHARGE_BLOCK_FACTOR = 0.25  # block raised while charging
PURGE_FACTOR = 0.5  # the purge's hit, before its d6
PHASE_TWO_HP_PERCENT = 50
PHASE_TWO_STRENGTH_FACTOR = 0.15
PHASE_TWO_BLOCK_FACTOR = 0.25


class EnemyIntentType(StrEnum):
    ATTACK = "attack"
    DEFEND = "defend"
    # boss-only
    BARRAGE = "barrage"  # BARRAGE_HITS smaller hits
    CHARGE = "charge"  # raises block; the next intent is always OVERLOAD
    OVERLOAD = "overload"  # one crushing hit
    PURGE = "purge"  # phase 2: destroys the rightmost permanent, then hits


# Intents that hit the player - everything else deals no damage.
ATTACKING_INTENTS = frozenset(
    {
        EnemyIntentType.ATTACK,
        EnemyIntentType.BARRAGE,
        EnemyIntentType.OVERLOAD,
        EnemyIntentType.PURGE,
    }
)


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
    # The player's artifacts, copied in at the start so every hook below can
    # read them without being handed the PlayerState.
    artifacts: list[Artifact] = Field(default_factory=list)
    turn: int = 1
    # Boss fights only: the phase it is in, and the attack it has gained.
    boss: bool = False
    phase: int = 1
    enemy_strength: int = 0


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


def cards_per_turn(state: CombatState) -> int:
    """Cards drawn for turn `state.turn`."""
    draw_bonus = sum(c.value for c in state.field if c and c.type is CardType.DRAW_BONUS)
    artifact_bonus = every_nth_turn(state.artifacts, "extra_draw", "extra_draw_every", state.turn)
    return max(0, CARDS_PER_TURN + draw_bonus + artifact_bonus)


def max_hand_size(state: CombatState) -> int:
    return MAX_HAND_SIZE + total(state.artifacts, "max_hand")


def enemy_attack(state: CombatState) -> int:
    """The enemy's attack stat after artifacts - before the d6 roll and block."""
    return max(
        0, state.enemy.attack + state.enemy_strength + total(state.artifacts, "enemy_attack")
    )


def enemy_block_gain(state: CombatState) -> int:
    """Block the enemy raises with its current intent (0 if it isn't raising any)."""
    if state.enemy_intent is EnemyIntentType.DEFEND:
        return state.enemy.attack + state.enemy_strength
    if state.enemy_intent is EnemyIntentType.CHARGE:
        return round((state.enemy.attack + state.enemy_strength) * CHARGE_BLOCK_FACTOR)
    return 0


def intent_hits(state: CombatState) -> list[tuple[int, int]]:
    """(lowest, highest) raw damage of each hit the telegraphed intent deals -
    before block and armor. Empty for intents that don't attack.
    """
    base = enemy_attack(state)
    intent = state.enemy_intent
    if intent is EnemyIntentType.ATTACK:
        return [(base + 1, base + 6)]
    if intent is EnemyIntentType.BARRAGE:
        hit = round(base * BARRAGE_FACTOR)
        return [(hit + 1, hit + 3)] * BARRAGE_HITS
    if intent is EnemyIntentType.OVERLOAD:
        hit = round(base * OVERLOAD_FACTOR)
        return [(hit + 1, hit + 6)]
    if intent is EnemyIntentType.PURGE:
        hit = round(base * PURGE_FACTOR)
        return [(hit + 1, hit + 6)]
    return []


def _damage_taken(hits: list[int], block: int, armor: int) -> int:
    """HP lost to `hits`: armor shaves every hit, block soaks up what's left
    until it runs out."""
    taken = 0
    for raw in hits:
        through = max(0, raw - armor)
        soaked = min(through, block)
        block -= soaked
        taken += through - soaked
    return taken


def player_armor(state: CombatState) -> int:
    """Flat reduction of the enemy's hit: armor cards on the field plus artifacts."""
    armor = sum(1 for c in state.field if c is not None and c.type is CardType.ARMOR)
    return armor + total(state.artifacts, "armor")


def fortify_block(state: CombatState) -> int:
    """Block the Mainframes raise at the end of the turn, before the enemy acts."""
    fortify = sum(c.value for c in state.field if c and c.type is CardType.FORTIFY)
    return fortify * permanent_count(state)


def turn_block(state: CombatState) -> int:
    """Block the artifacts raise at the end of this turn, before the enemy acts."""
    return every_nth_turn(state.artifacts, "turn_block", "turn_block_every", state.turn)


def incoming_damage(state: CombatState) -> tuple[int, int]:
    """(lowest, highest) damage the telegraphed attack would do if the turn
    ended now - the roll on top of the attack stat, after the block the
    player has and is about to raise, and after armor. (0, 0) while the enemy
    isn't attacking.
    """
    hits = intent_hits(state)
    if not hits:
        return 0, 0
    block = state.player_block + fortify_block(state) + turn_block(state)
    armor = player_armor(state)
    return (
        _damage_taken([low for low, _ in hits], block, armor),
        _damage_taken([high for _, high in hits], block, armor),
    )


def excess_hand_cards(state: CombatState) -> int:
    """How many cards have to be discarded before the turn can end."""
    return max(0, len(state.hand) - max_hand_size(state))


def _discard_excess(state: CombatState, discard: list[int] | None) -> str:
    """Discard the hand down to the hand limit (max_hand_size).

    `discard` names the hand indices to throw away and has to match the excess
    exactly; None lets the bots skip the choice and drops the most recently
    drawn cards. Raises ValueError before touching the hand if it doesn't fit.
    """
    excess = excess_hand_cards(state)
    if discard is None:
        discard = list(range(len(state.hand) - excess, len(state.hand)))
    if len(set(discard)) != len(discard) or len(discard) != excess:
        raise ValueError(f"discard exactly {excess} card(s) to end the turn")
    if any(not 0 <= i < len(state.hand) for i in discard):
        raise ValueError("discard index is out of range")
    if not discard:
        return ""
    discarded = [state.hand[i] for i in sorted(discard)]
    for i in sorted(discard, reverse=True):
        state.discard_pile.append(state.hand.pop(i))
    return f"Your hand is too full - you discard {_names(discarded)}."


def _roll_enemy_intent(rng: random.Random) -> EnemyIntentType:
    return EnemyIntentType.DEFEND if rng.random() < ENEMY_DEFEND_CHANCE else EnemyIntentType.ATTACK


def _roll_boss_intent(state: CombatState, rng: random.Random) -> EnemyIntentType:
    """A boss's next move: a charge is always followed by its overload, an
    overload never straight by another charge, and purges only come in
    phase 2 while there is a permanent on the field to destroy."""
    previous = state.enemy_intent
    if previous is EnemyIntentType.CHARGE:
        return EnemyIntentType.OVERLOAD
    weights = {
        EnemyIntentType.ATTACK: 4,
        EnemyIntentType.BARRAGE: 2,
        EnemyIntentType.CHARGE: 2,
        EnemyIntentType.DEFEND: 3,
    }
    if state.phase >= 2:
        weights[EnemyIntentType.DEFEND] = 2
        if permanent_count(state):
            weights[EnemyIntentType.PURGE] = 2
    if previous is EnemyIntentType.OVERLOAD:
        del weights[EnemyIntentType.CHARGE]
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _next_intent(state: CombatState, rng: random.Random) -> EnemyIntentType:
    return _roll_boss_intent(state, rng) if state.boss else _roll_enemy_intent(rng)


def _check_boss_phase(state: CombatState) -> str:
    """Move a boss into phase 2 the first time it drops to half HP or below."""
    if (
        not state.boss
        or state.phase >= 2
        or state.enemy_hp <= 0
        or state.enemy_hp * 100 > state.enemy.hp * PHASE_TWO_HP_PERCENT
    ):
        return ""
    state.phase = 2
    strength = max(1, round(state.enemy.attack * PHASE_TWO_STRENGTH_FACTOR))
    state.enemy_strength += strength
    block = round(state.enemy.attack * PHASE_TWO_BLOCK_FACTOR)
    state.enemy_block += block
    return f" {state.enemy.name} overclocks into phase 2: +{strength} attack and {block} block!"


def _damage_enemy(state: CombatState, damage: int) -> tuple[int, int]:
    """Apply damage to the enemy's block first, then its HP. Returns (absorbed, dealt)."""
    absorbed = min(damage, state.enemy_block)
    state.enemy_block -= absorbed
    dealt = damage - absorbed
    state.enemy_hp = max(state.enemy_hp - dealt, 0)
    return absorbed, dealt


def start_combat(
    deck: list[Card],
    enemy: Enemy,
    rng: random.Random,
    artifacts: list[Artifact] | None = None,
    boss: bool = False,
) -> tuple[CombatState, list[str]]:
    """Shuffle a *copy* of `deck` into the draw pile and draw an opening hand.

    `deck` (the player's owned cards) is read, never mutated - the piles
    below are the combat-scoped working copy that gets folded back once the
    fight ends. `boss` switches on the boss move set and phases.
    """
    artifacts = list(artifacts or [])
    hp_percent = total(artifacts, "enemy_hp_percent")
    if hp_percent:
        enemy = enemy.model_copy(update={"hp": max(1, round(enemy.hp * (100 + hp_percent) / 100))})
    draw_pile = list(deck)
    rng.shuffle(draw_pile)
    state = CombatState(
        enemy=enemy,
        enemy_hp=enemy.hp,
        draw_pile=draw_pile,
        hand=[],
        discard_pile=[],
        field=[None] * FIELD_SIZE,
        player_block=total(artifacts, "start_block"),
        artifacts=artifacts,
        boss=boss,
    )
    state.enemy_intent = _next_intent(state, rng)
    _draw(state, HAND_SIZE + total(artifacts, "opening_hand"), rng)
    log = [f"A {enemy.name} appears! ({enemy.hp} HP)"]
    if boss:
        log.append(
            f"{enemy.name} is a boss: it barrages, charges up crushing blows, "
            f"and grows stronger at half HP."
        )
    if opening := total(artifacts, "opening_damage"):
        _, dealt = _damage_enemy(state, opening)
        log.append(f"Your artifacts strike first for {dealt} damage.{_check_boss_phase(state)}")
    return state, log


def _amplifier_multiplier(state: CombatState, slot_index: int) -> float:
    boosts = sum(
        1
        for i, c in enumerate(state.field)
        if c is not None and c.type is CardType.AMPLIFIER and i < slot_index
    )
    return 1 + 0.25 * boosts


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

    # Action card: the multiplier is read from the field *before* the effect
    # runs, so e.g. Final Strike destroying the very Amplifier it benefited
    # from still counts that benefit.
    multiplier = _amplifier_multiplier(state, slot_index)
    line = cost_line + _apply_action_effect(state, card, multiplier, player, rng)

    if card.exhaust:
        state.banished_pile.append(card)
        line += " It's used up and banished for the rest of the fight."
    else:
        state.discard_pile.append(card)

    if card.draw:
        drawn = _draw(state, card.draw, rng)
        line += f" You draw {drawn} card(s)."

    return line + _check_boss_phase(state)


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


def action_preview(
    state: CombatState, card: Card, player: PlayerState, slot_index: int
) -> int | None:
    """The number an action card would come out with in `slot_index`: damage
    per hit, block gained or HP healed, after ATK, artifacts and any
    amplifier to its left. None for cards without such a number (permanents,
    card flow) and for occupied slots.

    Reads the same helpers _apply_action_effect uses, so the preview is what
    the play will actually do.
    """
    if state.field[slot_index] is not None:
        return None
    multiplier = _amplifier_multiplier(state, slot_index)
    if card.type is CardType.ATTACK:
        return attack_damage(state, card, player, multiplier)
    if card.type is CardType.BLOCK:
        return round((card.value + total(state.artifacts, "block_bonus")) * multiplier)
    if card.type is CardType.HEAL:
        return round((card.value + total(state.artifacts, "heal_bonus")) * multiplier)
    if card.type is CardType.FINAL_STRIKE:
        return round(card.value * permanent_count(state) * multiplier)
    return None


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
        leech = ""
        if healed := heal(player, total(state.artifacts, "lifesteal")):
            leech = f" You leech {healed} HP."
        if absorbed > 0:
            return (
                f"You play {card.name}, dealing {what} - {state.enemy.name}'s "
                f"block absorbs {absorbed}, {dealt} gets through. {state.enemy.name} at "
                f"{state.enemy_hp} HP.{leech}"
            )
        return (
            f"You play {card.name}, dealing {what}. {state.enemy.name} at "
            f"{state.enemy_hp} HP.{leech}"
        )

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

    if card.type is CardType.REBOOT:
        # Only what was banished *before* this card counts: the permanents it
        # destroys are the price and stay banished. Restore-type cards (and
        # other Reboots) never come back - they could fetch each other forever.
        returning = [
            c for c in state.banished_pile if c.type not in (CardType.RESTORE, CardType.REBOOT)
        ]
        for c in returning:
            state.banished_pile.remove(c)
        destroyed = [c for c in state.field if c is not None]
        state.banished_pile.extend(destroyed)
        state.field = [None] * FIELD_SIZE
        state.hand.extend(returning)
        return (
            f"You play {card.name}, wiping {len(destroyed)} permanent card(s) and "
            f"restoring {_names(returning)} from the banished pile."
        )

    if card.type is CardType.BLOCK:
        amount = round((card.value + total(state.artifacts, "block_bonus")) * multiplier)
        state.player_block += amount
        return f"You play {card.name}, gaining {amount} block."

    if card.type is CardType.HEAL:
        amount = round((card.value + total(state.artifacts, "heal_bonus")) * multiplier)
        healed = heal(player, amount)
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


def end_turn(
    state: CombatState,
    player: PlayerState,
    rng: random.Random,
    discard: list[int] | None = None,
) -> list[str]:
    """`discard`: hand indices to discard down to MAX_HAND_SIZE (see _discard_excess)."""
    log: list[str] = []
    if line := _discard_excess(state, discard):
        log.append(line)

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
    if gained := fortify_block(state):
        state.player_block += gained
        log.append(f"Your mainframe raises {gained} block.")
    if gained := turn_block(state):
        state.player_block += gained
        log.append(f"Your artifacts raise {gained} block.")
    if line := _check_boss_phase(state):
        log.append(line.strip())

    if state.enemy_intent is EnemyIntentType.DEFEND:
        gained = enemy_block_gain(state)
        state.enemy_block += gained
        log.append(f"{state.enemy.name} braces itself, gaining {gained} block.")
    elif state.boss and state.enemy_intent is not EnemyIntentType.ATTACK:
        log.extend(_boss_move(state, player, rng))
        if state.enemy_hp <= 0:
            return log
    else:
        armor = player_armor(state)
        reduction = state.player_block + armor
        raw_damage = enemy_attack(state) + rng.randint(1, 6)
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

        if thorns := total(state.artifacts, "thorns"):
            _, dealt = _damage_enemy(state, thorns)
            log.append(
                f"The attack backfires: {state.enemy.name} takes {dealt} damage. "
                f"{state.enemy.name} at {state.enemy_hp} HP."
            )
            if state.enemy_hp <= 0:
                return log

    state.player_block = 0
    state.enemy_intent = _next_intent(state, rng)
    state.turn += 1
    # Unplayed hand cards carry over to next turn; a fixed number of cards
    # is drawn on top, so holding cards back grows the hand (up to the limit).
    _draw(state, cards_per_turn(state), rng)
    return log


def _boss_move(state: CombatState, player: PlayerState, rng: random.Random) -> list[str]:
    """Resolve a boss-only intent (everything but a plain attack or brace)."""
    name = state.enemy.name
    intent = state.enemy_intent
    if intent is EnemyIntentType.CHARGE:
        gained = enemy_block_gain(state)
        state.enemy_block += gained
        return [f"{name} charges up, gaining {gained} block - an overload is coming!"]

    log: list[str] = []
    if intent is EnemyIntentType.PURGE:
        slot = next((i for i in reversed(range(FIELD_SIZE)) if state.field[i] is not None), None)
        if slot is not None:
            purged = state.field[slot]
            state.field[slot] = None
            state.banished_pile.append(purged)
            log.append(f"{name} purges your {purged.name} from slot {slot + 1}!")

    hits = [rng.randint(low, high) for low, high in intent_hits(state)]
    armor = player_armor(state)
    taken = _damage_taken(hits, state.player_block, armor)
    player.hp = max(player.hp - taken, 0)
    move = {
        EnemyIntentType.BARRAGE: f"unleashes a {len(hits)}-hit barrage",
        EnemyIntentType.OVERLOAD: "releases an overload",
        EnemyIntentType.PURGE: f"strikes with {state.enemy.attack_name}",
    }[intent]
    rolled = " + ".join(str(h) for h in hits)
    log.append(f"{name} {move} ({rolled}). You take {taken} damage. You are at {player.hp} HP.")
    if thorns := total(state.artifacts, "thorns"):
        _, dealt = _damage_enemy(state, thorns)
        log.append(
            f"The attack backfires: {name} takes {dealt} damage. {name} at {state.enemy_hp} HP."
        )
    return log


def auto_resolve_combat(
    deck: list[Card],
    enemy: Enemy,
    player: PlayerState,
    rng: random.Random,
    boss: bool = False,
) -> tuple[bool, list[str]]:
    """Play out a full fight non-interactively: dump the hand into the first
    empty field slot each turn, then end the turn, until someone runs out of HP.
    """
    state, log = start_combat(deck, enemy, rng, player.artifacts, boss=boss)

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
