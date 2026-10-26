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

The enemy telegraphs its next move a turn ahead (an "intent") so playing a
card is an informed choice, not a guess. Which moves it can roll, how often
and how hard they hit comes from its move set (`Enemy.moves`, see
models.EnemyMove): attack, brace for block, a multi-hit barrage, a charge-up
that telegraphs a crushing overload blow on the following turn, or a purge
that destroys the rightmost permanent on the field. Every move's strength is
a percentage of the enemy's attack stat. The default move set is the one
every enemy had before move sets existed: attack, or brace 30% of the time.

Bosses ignore their move set and fight with their own (see
_roll_boss_intent): all of the moves above, the purge only once they drop to
half HP and enter phase 2, gaining strength and block. Later acts' bosses
have a third phase at a quarter HP: stronger again, no more bracing, and a
four-hit barrage.

Characters with a context window (the Vibe-Coder, see characters.py) pay
every card's token_cost out of it, and part of it frees up again at the end
of every turn. A card that would push them past it still plays, but
hallucinates with HALLUCINATION_CHANCE: an attack hits them instead, a
block or heal goes to the enemy, anything else fizzles. Dr. Chronos has no
window - none of that touches his fights, nor the rng sequence they roll.

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
from .cards import can_upgrade, upgrade_card
from .characters import profile
from .models import (
    CONTROL_FLOW_TYPES,
    DEFAULT_BARRAGE_HITS,
    DEFAULT_INTERRUPT_AFTER,
    DEFAULT_MOVE_POWER,
    PERMANENT_CARD_TYPES,
    Affix,
    Artifact,
    Card,
    CardType,
    Character,
    Enemy,
    EnemyMove,
    MoveKind,
    PlayerState,
    Scaling,
    Status,
)

HAND_SIZE = 5  # opening hand
CARDS_PER_TURN = 3  # drawn at the end of every turn, on top of what's left
MAX_HAND_SIZE = 8  # discard down to this at the end of the turn
FIELD_SIZE = 5
MAX_AUTO_TURNS = 50
# Bots stop playing after this many cards in one turn - a backstop so a
# card combo nobody foresaw can never hang the simulator or the tests.
MAX_AUTO_PLAYS_PER_TURN = 30
# Chance that a card played past the context window backfires.
HALLUCINATION_CHANCE = 0.5
# Copilot (CHAIN) counts at most this many cards played before it in a turn.
CHAIN_MAX_PLAYS = 3

# Move strength scales off the attack stat (plus a boss's phase strength).
# How hard each kind hits by default is models.DEFAULT_MOVE_POWER; a move in
# an enemy's move set can override it.
CHARGE_BLOCK_FACTOR = 0.25  # block raised while charging

# Elite affixes (models.Affix), scaled off the attack stat where they scale.
ARMORED_BLOCK_FACTOR = 0.3  # block raised after each of its turns
REGEN_FACTOR = 0.25  # HP healed after each of its turns
ENRAGE_FACTOR = 0.5  # extra attack once at or below half HP
THORNY_DAMAGE = 2  # HP every attack card played against it costs the player
AFFIX_DESCRIPTIONS = {
    Affix.ARMORED: "Raises block after every one of its turns.",
    Affix.REGENERATING: "Heals after every one of its turns.",
    Affix.ENRAGED: "Hits 50% harder once below half HP.",
    Affix.THORNY: f"Every attack card you play against it costs you {THORNY_DAMAGE} HP.",
}
# HP percentage at or below which a boss enters each phase past the first.
PHASE_HP_PERCENT = {2: 50, 3: 25}
PHASE_STRENGTH_FACTOR = 0.15  # attack gained on entering a phase
PHASE_BLOCK_FACTOR = 0.25  # block gained on entering a phase


class EnemyIntentType(StrEnum):
    # Same values as models.MoveKind - every move is an intent.
    ATTACK = "attack"
    DEFEND = "defend"
    BARRAGE = "barrage"  # several smaller hits
    CHARGE = "charge"  # raises block; the next intent is always OVERLOAD
    OVERLOAD = "overload"  # one crushing hit - never rolled, always follows a CHARGE
    PURGE = "purge"  # destroys the rightmost permanent, then hits
    INFECT = "infect"  # a light hit that leaves Malware on the player
    LOCK = "lock"  # a light hit that locks an empty field slot for the player's next turn
    CORRUPT = "corrupt"  # a light hit that shuffles Glitch cards into the draw pile
    INTERRUPT = "interrupt"  # a light hit; the program is cut off after a few lines
    REFACTOR = "refactor"  # bosses: a light hit; the program runs right to left


# Intents that hit the player - everything else deals no damage.
ATTACKING_INTENTS = frozenset(
    {
        EnemyIntentType.ATTACK,
        EnemyIntentType.BARRAGE,
        EnemyIntentType.OVERLOAD,
        EnemyIntentType.PURGE,
        EnemyIntentType.INFECT,
        EnemyIntentType.LOCK,
        EnemyIntentType.CORRUPT,
        EnemyIntentType.INTERRUPT,
        EnemyIntentType.REFACTOR,
    }
)

# The light hit every field move (infect, lock, corrupt, interrupt) comes with.
_LIGHT_HIT_KINDS = {
    EnemyIntentType.INFECT: MoveKind.INFECT,
    EnemyIntentType.LOCK: MoveKind.LOCK,
    EnemyIntentType.CORRUPT: MoveKind.CORRUPT,
    EnemyIntentType.INTERRUPT: MoveKind.INTERRUPT,
    EnemyIntentType.REFACTOR: MoveKind.REFACTOR,
}

# How often a boss refactors a program, against its other moves' weights
# (attack 4, barrage 2, charge 2, brace 3).
BOSS_REFACTOR_WEIGHT = 2

# What program mode queues: the cards that act on the fight, and the control
# flow steering them. Card flow (draw, retrieve, free plays, ...) still
# resolves on the spot - at the end of the turn it would come too late.
QUEUED_TYPES = CONTROL_FLOW_TYPES | {
    CardType.ATTACK,
    CardType.BLOCK,
    CardType.HEAL,
    CardType.FINAL_STRIKE,
}


# Statuses (models.Status).
EXPOSED_FACTOR = 1.5  # attack cards against an exposed enemy
THROTTLED_FACTOR = 0.75  # a throttled enemy's attack
STATUS_DESCRIPTIONS = {
    Status.MALWARE: "Loses that much HP at the end of each turn, then one stack fades.",
    Status.EXPOSED: "Attack cards deal 50% more to it. Lasts that many of its turns.",
    Status.THROTTLED: "Deals 25% less. Lasts that many of its turns.",
}


class CombatState(BaseModel):
    enemy: Enemy
    enemy_hp: int
    enemy_block: int = 0
    enemy_intent: EnemyIntentType = EnemyIntentType.ATTACK
    # Index into enemy.moves of the move behind the intent - for an OVERLOAD
    # the CHARGE it follows. None for bosses, which roll their own moves.
    enemy_move: int | None = None
    draw_pile: list[Card]
    hand: list[Card]
    discard_pile: list[Card]
    banished_pile: list[Card] = Field(default_factory=list)
    # Classic: FIELD_SIZE slots, a permanent's position counts. Program mode:
    # the permanents running in the background - as many as get played, in
    # play order, no gaps (see _empty_field).
    field: list[Card | None] = Field(default_factory=lambda: [None] * FIELD_SIZE)
    player_block: int = 0
    # The player's artifacts, copied in at the start so every hook below can
    # read them without being handed the PlayerState.
    artifacts: list[Artifact] = Field(default_factory=list)
    turn: int = 1
    # Boss fights only: the phase it is in (out of boss_phases), and the
    # attack it has gained.
    boss: bool = False
    boss_phases: int = 2
    phase: int = 1
    enemy_strength: int = 0
    # The character's card flow (see characters.py): the context window
    # (None: no window, token costs are ignored) and the tokens spent from
    # it, cards drawn after every play, and the change to the end-of-turn draw.
    token_limit: int | None = None
    tokens_used: int = 0
    token_regen: int = 0  # used tokens freed at the end of every turn
    draw_on_play: int = 0
    turn_draw_modifier: int = 0
    plays_this_turn: int = 0  # what Copilot (CHAIN) counts
    # Statuses and their stacks / turns left (models.Status).
    enemy_status: dict[Status, int] = Field(default_factory=dict)
    player_status: dict[Status, int] = Field(default_factory=dict)
    # Field slots an enemy's lock move has shut for the player's current turn.
    locked_slots: list[int] = Field(default_factory=list)
    # Program mode: action cards wait in `program` (by slot) and run left to
    # right at the end of the turn (run_program); whether each one was played
    # past the context window, and so will hallucinate, is rolled on queueing.
    program_mode: bool = False
    program: list[Card | None] = Field(default_factory=lambda: [None] * FIELD_SIZE)
    program_glitched: list[bool] = Field(default_factory=lambda: [False] * FIELD_SIZE)
    # cards left this turn that cost no tokens (Tab-Tab-Tab, Pair Programming)
    free_plays: int = 0


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
    return max(0, CARDS_PER_TURN + state.turn_draw_modifier + draw_bonus + artifact_bonus)


def token_cost(state: CombatState, card: Card) -> int:
    """What playing `card` takes from the context window - 0 without one,
    and 0 while a free play (Tab-Tab-Tab, Pair Programming) is pending."""
    if state.token_limit is None or state.free_plays:
        return 0
    return max(0, card.token_cost)


def tokens_left(state: CombatState) -> int | None:
    if state.token_limit is None:
        return None
    return max(0, state.token_limit - state.tokens_used)


def overflows(state: CombatState, card: Card) -> bool:
    """Whether `card` would push past the context window - and may hallucinate."""
    cost = token_cost(state, card)
    return cost > 0 and state.tokens_used + cost > state.token_limit


def hallucination_chance(state: CombatState) -> float:
    """Chance a card past the context window backfires, after artifacts."""
    percent = 100 + total(state.artifacts, "hallucination_percent")
    return max(0.0, HALLUCINATION_CHANCE * percent / 100)


def token_regen(state: CombatState) -> int:
    """Used tokens freed at the end of this turn: the character's own (after
    artifacts) plus Energy Drinks."""
    drinks = sum(c.value for c in state.field if c and c.type is CardType.TOKEN_REGEN)
    return state.token_regen + drinks


def _free_tokens(state: CombatState, amount: int) -> int:
    freed = max(0, min(amount, state.tokens_used))
    state.tokens_used -= freed
    return freed


def max_hand_size(state: CombatState) -> int:
    return MAX_HAND_SIZE + total(state.artifacts, "max_hand")


def is_enraged(state: CombatState) -> bool:
    return state.enemy.affix is Affix.ENRAGED and state.enemy_hp * 2 <= state.enemy.hp


def enemy_attack(state: CombatState) -> int:
    """The enemy's attack stat after artifacts and rage - before the d6 roll and block."""
    rage = round(state.enemy.attack * ENRAGE_FACTOR) if is_enraged(state) else 0
    attack = state.enemy.attack + state.enemy_strength + rage
    if Status.THROTTLED in state.enemy_status:
        attack = round(attack * THROTTLED_FACTOR)
    return max(0, attack + total(state.artifacts, "enemy_attack"))


def current_move(state: CombatState) -> EnemyMove | None:
    """The move-set entry behind the telegraphed intent (None for bosses)."""
    return None if state.enemy_move is None else state.enemy.moves[state.enemy_move]


def _move_power(state: CombatState, kind: MoveKind) -> int:
    """Percent of the attack stat the current intent works with."""
    move = current_move(state)
    return DEFAULT_MOVE_POWER[kind] if move is None else move.power


def move_name(state: CombatState) -> str | None:
    """The current move's own name, if its move set gave it one."""
    move = current_move(state)
    return None if move is None else move.name


def enemy_block_gain(state: CombatState) -> int:
    """Block the enemy raises with its current intent (0 if it isn't raising any)."""
    base = state.enemy.attack + state.enemy_strength
    if state.enemy_intent is EnemyIntentType.DEFEND:
        return round(base * _move_power(state, MoveKind.DEFEND) / 100)
    if state.enemy_intent is EnemyIntentType.CHARGE:
        return round(base * CHARGE_BLOCK_FACTOR)
    return 0


def intent_hits(state: CombatState) -> list[tuple[int, int]]:
    """(lowest, highest) raw damage of each hit the telegraphed intent deals -
    before block and armor. Empty for intents that don't attack.
    """
    base = enemy_attack(state)
    intent = state.enemy_intent
    if intent is EnemyIntentType.ATTACK:
        hit = round(base * _move_power(state, MoveKind.ATTACK) / 100)
        return [(hit + 1, hit + 6)]
    if intent is EnemyIntentType.BARRAGE:
        hit = round(base * _move_power(state, MoveKind.BARRAGE) / 100)
        return [(hit + 1, hit + 3)] * barrage_hits(state)
    if intent is EnemyIntentType.OVERLOAD:
        # The power of the CHARGE it follows.
        hit = round(base * _move_power(state, MoveKind.CHARGE) / 100)
        return [(hit + 1, hit + 6)]
    if intent is EnemyIntentType.PURGE:
        hit = round(base * _move_power(state, MoveKind.PURGE) / 100)
        return [(hit + 1, hit + 6)]
    if intent in _LIGHT_HIT_KINDS:
        hit = round(base * _move_power(state, _LIGHT_HIT_KINDS[intent]) / 100)
        return [(hit + 1, hit + 6)]
    return []


def barrage_hits(state: CombatState) -> int:
    move = current_move(state)
    if move is not None:
        return move.hits
    return DEFAULT_BARRAGE_HITS + (1 if state.phase >= 3 else 0)


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
    armor = sum(c.value for c in state.field if c is not None and c.type is CardType.ARMOR)
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


def _roll_enemy_move(state: CombatState, rng: random.Random) -> int:
    """Index of the move a regular enemy does next, weighted by the move set.

    Same rules as a boss's: a charge is always followed by its overload (the
    caller handles that), never straight by another charge, and a purge is
    only rolled while there is a permanent on the field to destroy.
    models.Enemy guarantees an attack or barrage, so something is always left.
    """
    previous = state.enemy_intent
    options = [
        i
        for i, move in enumerate(state.enemy.moves)
        if not (move.kind is MoveKind.PURGE and not permanent_count(state))
        and not (move.kind is MoveKind.CHARGE and previous is EnemyIntentType.OVERLOAD)
    ]
    # A single option still draws, so the rng stays in step either way.
    weights = [state.enemy.moves[i].weight for i in options]
    return rng.choices(options, weights=weights)[0]


def _roll_boss_intent(state: CombatState, rng: random.Random) -> EnemyIntentType:
    """A boss's next move: a charge is always followed by its overload, an
    overload never straight by another charge, purges only come from phase 2
    on while there is a permanent on the field to destroy, and in phase 3 it
    stops bracing. Against a program it refactors now and then - never
    twice in a row."""
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
    if state.phase >= 3:
        del weights[EnemyIntentType.DEFEND]
    if previous is EnemyIntentType.OVERLOAD:
        del weights[EnemyIntentType.CHARGE]
    if state.program_mode and previous is not EnemyIntentType.REFACTOR:
        weights[EnemyIntentType.REFACTOR] = BOSS_REFACTOR_WEIGHT
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _roll_next_intent(state: CombatState, rng: random.Random) -> None:
    """Set the enemy's next intent (and the move behind it)."""
    if state.boss:
        state.enemy_intent = _roll_boss_intent(state, rng)
        return
    if state.enemy_intent is EnemyIntentType.CHARGE:
        # enemy_move stays on the CHARGE: its power is the overload's.
        state.enemy_intent = EnemyIntentType.OVERLOAD
        return
    state.enemy_move = _roll_enemy_move(state, rng)
    state.enemy_intent = EnemyIntentType(state.enemy.moves[state.enemy_move].kind.value)


def _check_boss_phase(state: CombatState) -> str:
    """Move a boss into its next phase(s) once its HP drops to the threshold
    (PHASE_HP_PERCENT) - each phase entered once, and only up to boss_phases."""
    line = ""
    while (
        state.boss
        and state.phase < state.boss_phases
        and state.enemy_hp > 0
        and state.enemy_hp * 100 <= state.enemy.hp * PHASE_HP_PERCENT[state.phase + 1]
    ):
        state.phase += 1
        strength = max(1, round(state.enemy.attack * PHASE_STRENGTH_FACTOR))
        state.enemy_strength += strength
        block = round(state.enemy.attack * PHASE_BLOCK_FACTOR)
        state.enemy_block += block
        line += (
            f" {state.enemy.name} overclocks into phase {state.phase}: +{strength} attack "
            f"and {block} block!"
        )
    return line


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
    boss_phases: int = 2,
    character: Character = Character.CHRONOS,
    program_mode: bool = False,
) -> tuple[CombatState, list[str]]:
    """Shuffle a *copy* of `deck` into the draw pile and draw an opening hand.

    `deck` (the player's owned cards) is read, never mutated - the piles
    below are the combat-scoped working copy that gets folded back once the
    fight ends. `boss` switches on the boss move set, with `boss_phases`
    phases (2 or 3). `character` sets the card flow (see characters.py).
    """
    artifacts = list(artifacts or [])
    hero = profile(character)
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
        field=[] if program_mode else [None] * FIELD_SIZE,
        player_block=total(artifacts, "start_block"),
        artifacts=artifacts,
        boss=boss,
        boss_phases=boss_phases,
        token_limit=(
            None
            if hero.token_limit is None
            else max(1, hero.token_limit + total(artifacts, "token_window"))
        ),
        token_regen=hero.token_regen + total(artifacts, "token_regen"),
        draw_on_play=hero.draw_on_play,
        turn_draw_modifier=hero.turn_draw_modifier,
        free_plays=total(artifacts, "opening_free_plays"),
        program_mode=program_mode,
    )
    if program_mode:
        lines = FIELD_SIZE + hero.extra_program_lines + total(artifacts, "extra_lines")
        state.program, state.program_glitched = [None] * lines, [False] * lines
    _roll_next_intent(state, rng)
    _draw(state, HAND_SIZE + total(artifacts, "opening_hand"), rng)
    log = [f"A {enemy.name} appears! ({enemy.hp} HP)"]
    if enemy.taunt:
        log.append(enemy.taunt)
    if enemy.description:
        log.append(enemy.description)
    if enemy.affix is not None:
        log.append(f"It is {enemy.affix.value}: {AFFIX_DESCRIPTIONS[enemy.affix]}")
    if boss:
        later = " and again at a quarter" if boss_phases >= 3 else ""
        log.append(
            f"{enemy.name} is a boss: it barrages, charges up crushing blows, "
            f"and grows stronger at half HP{later}."
        )
    if opening := total(artifacts, "opening_damage"):
        _, dealt = _damage_enemy(state, opening)
        log.append(f"Your artifacts strike first for {dealt} damage.{_check_boss_phase(state)}")
    return state, log


def _amplifier_multiplier(state: CombatState, slot_index: int) -> float:
    """1 + every amplifier's percent to the left of `slot_index` (25 each, 40 upgraded)."""
    boost = sum(
        c.value
        for i, c in enumerate(state.field)
        if c is not None and c.type is CardType.AMPLIFIER and _boosts(state, i, slot_index)
    )
    return 1 + boost / 100


def _boosts(state: CombatState, field_index: int, slot_index: int) -> bool:
    """Whether a left-boosting permanent (Overclock, Copilot) at `field_index`
    reaches `slot_index`. A program's background permanents reach every line."""
    return state.program_mode or field_index < slot_index


def _chain_bonus(state: CombatState, slot_index: int) -> int:
    """Flat bonus from the Copilots (CHAIN) left of `slot_index`: their value
    for every card already played this turn, up to CHAIN_MAX_PLAYS of them -
    uncapped, a long chain would grow quadratically."""
    chain = sum(
        c.value
        for i, c in enumerate(state.field)
        if c is not None and c.type is CardType.CHAIN and _boosts(state, i, slot_index)
    )
    return chain * min(state.plays_this_turn, CHAIN_MAX_PLAYS)


def play_card(
    state: CombatState, hand_index: int, slot_index: int, player: PlayerState, rng: random.Random
) -> str:
    if not 0 <= hand_index < len(state.hand):
        raise ValueError(f"hand_index {hand_index} is out of range")
    if not 0 <= slot_index < len(state.program):
        raise ValueError(f"slot_index {slot_index} is out of range")
    if slot_taken(state, slot_index, state.hand[hand_index]):
        raise ValueError(f"slot {slot_index} is occupied")
    if slot_index in state.locked_slots and _needs_slot(state, state.hand[hand_index]):
        raise ValueError(f"slot {slot_index} is locked this turn")

    card = state.hand.pop(hand_index)
    # Rolled before anything else is paid, and only past the context window -
    # a character without one never rolls here.
    hallucinates = overflows(state, card) and rng.random() < hallucination_chance(state)
    state.tokens_used += token_cost(state, card)
    if state.free_plays:
        state.free_plays -= 1
    # The cost is paid before anything else, so a card like Memory Dump can't
    # throw away the very cards it is about to draw.
    cost_line = _pay_discard_cost(state, card, rng)

    if queues(state, card):
        # Paid for now, run at the end of the turn (run_program).
        state.program[slot_index] = card
        state.program_glitched[slot_index] = hallucinates
        line = cost_line + f"You queue {card.name} in line {slot_index + 1}."
    elif hallucinates:
        line = cost_line + _hallucinate(state, card, slot_index, player)
        (state.banished_pile if card.exhaust else state.discard_pile).append(card)
    elif card.type in PERMANENT_CARD_TYPES and state.program_mode:
        state.field.append(card)
        line = cost_line + f"You start {card.name} - it keeps running in the background."
    elif card.type in PERMANENT_CARD_TYPES:
        state.field[slot_index] = card
        line = cost_line + f"You play {card.name} in slot {slot_index + 1} - it stays on the field."
    else:
        # Action card: the multiplier is read from the field *before* the
        # effect runs, so e.g. Final Strike destroying the very Amplifier it
        # benefited from still counts that benefit.
        multiplier = _amplifier_multiplier(state, slot_index)
        bonus = _chain_bonus(state, slot_index)
        line = cost_line + _apply_action_effect(state, card, multiplier, player, rng, bonus)
        if card.applies is not None and state.enemy_hp > 0:
            line += " " + _afflict(state, card.applies, card.applies_amount)

        if card.exhaust:
            state.banished_pile.append(card)
            line += " It's used up and banished for the rest of the fight."
        else:
            state.discard_pile.append(card)

        if card.draw:
            drawn = _draw(state, card.draw, rng)
            line += f" You draw {drawn} card(s)."

    state.plays_this_turn += 1
    if state.draw_on_play:
        drawn = _draw(state, state.draw_on_play, rng)
        line += f" You draw {drawn} card(s)."
    if state.token_limit is not None:
        line += f" Context: {state.tokens_used}/{state.token_limit} tokens."
    return line + _check_boss_phase(state)


def move_queued(state: CombatState, from_slot: int, to_slot: int) -> None:
    """Program mode: move a queued action to another line - swapping with
    whatever action waits there. A locked line takes nothing."""
    if not state.program_mode:
        raise ValueError("only a program can be rearranged")
    for slot in (from_slot, to_slot):
        if not 0 <= slot < len(state.program):
            raise ValueError(f"slot {slot} is out of range")
    if state.program[from_slot] is None:
        raise ValueError(f"no queued card in line {from_slot}")
    if to_slot in state.locked_slots:
        raise ValueError(f"line {to_slot} is locked this turn")
    p, g = state.program, state.program_glitched
    p[from_slot], p[to_slot] = p[to_slot], p[from_slot]
    g[from_slot], g[to_slot] = g[to_slot], g[from_slot]


def run_program(state: CombatState, player: PlayerState, rng: random.Random) -> list[str]:
    """Program mode, end of the turn: run the queued actions left to right.

    Every action resolves as if it had just been played in its line (the
    amplifiers and Copilots to its left count). Control flow steers the
    actions after it: fork runs the next one twice, if_wounded does so only
    if the enemy is at half HP or less by the time it runs, loop runs the
    last one again. Once the enemy
    is down the rest is skipped - one-shots included, which are then kept
    for the next fight.

    The program artifacts hook in here: Hot Path upgrades the card in its
    line for the run, Branch Predictor boosts every action once the enemy is
    at half HP, Tail Call runs the last line once more, Pipeline boosts the
    action right after control flow and Compiler the last line's action, by
    the other card types that ran before it.
    """
    log: list[str] = []
    forks, last, ran = 0, None, 0
    # An interrupting enemy lets only its first few lines run.
    cut_after = interrupt_after(state)
    lines_run = 0
    # Copilot and Ship It count the cards played this turn - every queued
    # one but themselves has been by the time the program runs - or the
    # actions run so far, once forks and loops have run more than that.
    played = state.plays_this_turn
    hot = total(state.artifacts, "hot_path") - 1
    pipeline = total(state.artifacts, "pipeline")
    predictor = total(state.artifacts, "wounded_bonus")
    last_line = len(state.program) - 1
    tail_call = every_nth_turn(state.artifacts, "tail_call", "tail_call_every", state.turn)
    compiler = total(state.artifacts, "compiler_bonus")
    types: set[CardType] = set()  # what ran so far
    after_flow = False
    piped = 0  # Pipe's bonus for the next action
    # A refactoring boss runs it right to left: control flow then steers the
    # actions run after it, now the ones to its left.
    order = list(range(len(state.program)))
    if state.enemy_intent is EnemyIntentType.REFACTOR:
        order.reverse()
    for step, slot in enumerate(order):
        card = state.program[slot]
        if card is None:
            continue
        glitched = state.program_glitched[slot]
        state.program[slot], state.program_glitched[slot] = None, False
        if state.enemy_hp <= 0 or player.hp <= 0:
            state.discard_pile.append(card)  # never ran, so never used up
            continue
        if cut_after is not None and lines_run >= cut_after:
            if lines_run == cut_after:
                log.append(f"{state.enemy.name} interrupts your program after {cut_after} line(s)!")
                lines_run += 1  # announced once
            state.discard_pile.append(card)
            continue
        lines_run += 1
        line = f"[{slot + 1}] "
        # Hot Path: the card runs as its upgrade, the deck keeps the original.
        run = card
        if slot == hot and not glitched and can_upgrade(card):
            run = upgrade_card(card)
            line += "(hot path) "
        if run.type is CardType.FORK:
            forks += run.value
            log.append(line + f"{run.name}: the next action runs {1 + forks} times.")
        elif run.type is CardType.IF_WOUNDED:
            forks += run.value if _wounded(state) else 0
            state_line = "at half HP or less" if _wounded(state) else "still above half HP"
            log.append(line + f"{run.name}: the enemy is {state_line}.")
        elif run.type is CardType.PIPE:
            piped += run.value * ran
            log.append(line + f"{run.name}: the next action gets +{piped} ({ran} ran before).")
        elif run.type is CardType.BATCH:
            # the actions still to run after it - an interrupt's cut ones don't
            ahead = [state.program[s] for s in order[step + 1 :] if state.program[s]]
            if cut_after is not None:
                ahead = ahead[: max(0, cut_after - lines_run)]
            actions = sum(1 for c in ahead if c.type not in CONTROL_FLOW_TYPES)
            freed = min(state.tokens_used, run.value * actions)
            state.tokens_used -= freed
            log.append(line + f"{run.name} batches {actions} action(s): {freed} token(s) free up.")
        elif run.type is CardType.LOOP:
            repeats = run.value + (tail_call if slot == last_line else 0)
            if last is None:
                log.append(line + f"{run.name}: nothing has run yet to repeat.")
            for _ in range(repeats if last is not None else 0):
                state.plays_this_turn = max(played - 1, ran)
                wounded = predictor if _wounded(state) else 0
                log.append(
                    line + f"{run.name} -> " + _run_line(state, last, slot, player, rng, wounded)
                )
                ran += 1
                if state.enemy_hp <= 0:
                    break
        else:
            bonus = (pipeline if after_flow else 0) + piped
            piped = 0
            if slot == last_line:
                bonus += compiler * len(types - {run.type})
                forks += tail_call
            for _ in range(1 + forks):
                state.plays_this_turn = max(played - 1, ran)
                wounded = predictor if _wounded(state) else 0
                if glitched:
                    log.append(line + _hallucinate(state, run, slot, player))
                else:
                    log.append(line + _run_line(state, run, slot, player, rng, bonus + wounded))
                ran += 1
                if state.enemy_hp <= 0:
                    break
            forks = 0
            last = None if glitched else run
        after_flow = run.type in CONTROL_FLOW_TYPES
        types.add(run.type)
        if run.type in CONTROL_FLOW_TYPES and run.draw:
            log.append(line + f"You draw {_draw(state, run.draw, rng)} card(s).")
        if card.exhaust and card.type not in CONTROL_FLOW_TYPES:
            state.banished_pile.append(card)
        else:
            state.discard_pile.append(card)
        if line := _check_boss_phase(state):
            log.append(line.strip())
    return log


class ProgramPreview(BaseModel):
    """Where the fight stands once the queued program has run (program_preview)."""

    enemy_hp: int
    enemy_block: int
    player_hp: int
    player_block: int


def program_preview(state: CombatState, player: PlayerState) -> ProgramPreview:
    """What the queued program will have done by the time the enemy acts -
    run on copies, so planning a program can see its outcome (the enemy's
    HP and block, the player's HP and block) the way classic play sees each
    card's at once. Without a program, where things stand now. Cards the
    program would draw are left out: they don't change these numbers.
    """
    if not state.program_mode or all(c is None for c in state.program):
        return ProgramPreview(
            enemy_hp=state.enemy_hp,
            enemy_block=state.enemy_block,
            player_hp=player.hp,
            player_block=state.player_block,
        )
    trial, me = state.model_copy(deep=True), player.model_copy(deep=True)
    run_program(trial, me, random.Random(0))
    return ProgramPreview(
        enemy_hp=trial.enemy_hp,
        enemy_block=trial.enemy_block,
        player_hp=me.hp,
        player_block=trial.player_block,
    )


def interrupt_after(state: CombatState) -> int | None:
    """How many queued lines run before an interrupting enemy cuts the
    program off - None unless its intent is an interrupt."""
    if state.enemy_intent is not EnemyIntentType.INTERRUPT:
        return None
    move = current_move(state)
    return DEFAULT_INTERRUPT_AFTER if move is None else move.stacks


def _wounded(state: CombatState) -> bool:
    """If Wounded's (and Branch Predictor's) condition: the enemy at half HP or less."""
    return state.enemy_hp * 2 <= state.enemy.hp


def _run_line(
    state: CombatState,
    card: Card,
    slot: int,
    player: PlayerState,
    rng: random.Random,
    bonus: int = 0,
) -> str:
    """One action card's effect, as if played into `slot` right now - with
    `bonus` on top of the Copilots' (Pipeline)."""
    multiplier = _amplifier_multiplier(state, slot)
    bonus += _chain_bonus(state, slot)
    line = _apply_action_effect(state, card, multiplier, player, rng, bonus)
    if card.applies is not None and state.enemy_hp > 0:
        line += " " + _afflict(state, card.applies, card.applies_amount)
    if card.draw:
        line += f" You draw {_draw(state, card.draw, rng)} card(s)."
    return line


def _hallucinate(state: CombatState, card: Card, slot_index: int, player: PlayerState) -> str:
    """A card played past the context window backfires: an attack hits the
    player (block soaks it first), a block or heal goes to the enemy, and
    everything else - permanents included - fizzles without effect."""
    multiplier = _amplifier_multiplier(state, slot_index)
    bonus = _chain_bonus(state, slot_index)
    lead = f"Context overflow - {card.name} hallucinates"
    if any(c is not None and c.type is CardType.SAFEGUARD for c in state.field):
        return f"{lead}, but your rubber duck catches it - it does nothing."
    if card.type is CardType.ATTACK:
        hits = [attack_damage(state, card, player, multiplier, bonus)] * max(card.hits, 1)
        taken = _damage_taken(hits, state.player_block, 0)
        state.player_block = max(0, state.player_block - sum(hits))
        player.hp = max(player.hp - taken, 0)
        return f"{lead} and hits you for {taken} damage. You are at {player.hp} HP."
    if card.type is CardType.BLOCK:
        amount = block_amount(state, card, multiplier, bonus)
        state.enemy_block += amount
        return f"{lead}: {state.enemy.name} gains {amount} block."
    if card.type is CardType.HEAL:
        amount = round((card.value + total(state.artifacts, "heal_bonus") + bonus) * multiplier)
        healed = min(amount, state.enemy.hp - state.enemy_hp)
        state.enemy_hp += healed
        return f"{lead}: {state.enemy.name} heals {healed} HP."
    return f"{lead} and does nothing."


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


def queues(state: CombatState, card: Card) -> bool:
    """Whether playing `card` queues it into the program (program mode)."""
    return state.program_mode and card.type in QUEUED_TYPES


def _needs_slot(state: CombatState, card: Card | None) -> bool:
    """Whether `card` takes up a slot. In program mode only queued actions do:
    permanents run in the background and card flow resolves on the spot, so
    neither competes for lines (or minds a locked one)."""
    return not state.program_mode or (card is not None and queues(state, card))


def slot_taken(state: CombatState, slot_index: int, card: Card | None = None) -> bool:
    """Whether `card` can't go into the slot: a queued action needs a free
    program line, everything else a slot without a permanent (classic) or
    nothing at all (program mode, see _needs_slot)."""
    if card is not None and queues(state, card):
        return state.program[slot_index] is not None
    if state.program_mode:
        return False
    # Extra program lines (extra_lines) have no field slot under them.
    return slot_index >= FIELD_SIZE or state.field[slot_index] is not None


def free_slots(state: CombatState, card: Card | None = None) -> list[int]:
    """Slots `card` (any card but a queued action, if None) can be played
    into right now - free and not locked."""
    return [
        i
        for i in range(len(state.program))
        if not slot_taken(state, i, card)
        and (i not in state.locked_slots or not _needs_slot(state, card))
    ]


def permanent_count(state: CombatState) -> int:
    return sum(1 for c in state.field if c is not None)


def attack_damage(
    state: CombatState, card: Card, player: PlayerState, multiplier: float = 1.0, bonus: int = 0
) -> int:
    """Damage of one hit of an ATTACK card - also what the UI/bots preview.
    `bonus` is flat damage on top, before the multiplier (Copilot)."""
    base = card.value + player.attack + bonus + _scaling_bonus(state, card)
    boost = sum(c.value for c in state.field if c and c.type is CardType.DAMAGE_BOOST)
    base += boost * permanent_count(state)
    if Status.EXPOSED in state.enemy_status:
        multiplier *= EXPOSED_FACTOR
    return round(base * multiplier)


def block_amount(state: CombatState, card: Card, multiplier: float = 1.0, bonus: int = 0) -> int:
    """Block a BLOCK card raises - also what the UI/bots preview."""
    base = card.value + total(state.artifacts, "block_bonus") + bonus + _scaling_bonus(state, card)
    return round(base * multiplier)


def _scaling_bonus(state: CombatState, card: Card) -> int:
    """The card's `scale_value` times whatever its `scaling` counts."""
    count = {
        None: 0,
        Scaling.PERMANENT: permanent_count(state),
        Scaling.GRAVEYARD: len(state.discard_pile),
        Scaling.BANISHED: len(state.banished_pile),
        Scaling.PLAYED: state.plays_this_turn,
        Scaling.EMPTY_SLOT: max(0, FIELD_SIZE - permanent_count(state)),
        Scaling.MALWARE: state.enemy_status.get(Status.MALWARE, 0),
    }[card.scaling]
    return card.scale_value * count


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
    if slot_taken(state, slot_index, card) or slot_index in state.locked_slots:
        return None
    hot = total(state.artifacts, "hot_path") - 1
    if queues(state, card) and slot_index == hot and can_upgrade(card):
        card = upgrade_card(card)  # Hot Path runs it upgraded
    multiplier = _amplifier_multiplier(state, slot_index)
    bonus = _chain_bonus(state, slot_index)
    if card.type is CardType.ATTACK:
        return attack_damage(state, card, player, multiplier, bonus)
    if card.type is CardType.BLOCK:
        return block_amount(state, card, multiplier, bonus)
    if card.type is CardType.HEAL:
        return round((card.value + total(state.artifacts, "heal_bonus") + bonus) * multiplier)
    if card.type is CardType.FINAL_STRIKE:
        return round(card.value * permanent_count(state) * multiplier)
    return None


def _apply_action_effect(
    state: CombatState,
    card: Card,
    multiplier: float,
    player: PlayerState,
    rng: random.Random,
    bonus: int = 0,
) -> str:
    if card.type is CardType.ATTACK:
        damage = attack_damage(state, card, player, multiplier, bonus)
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
        if state.enemy.affix is Affix.THORNY:
            player.hp = max(player.hp - THORNY_DAMAGE, 0)
            leech += f" Its thorns cost you {THORNY_DAMAGE} HP."
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
        state.field = _empty_field(state)
        state.hand.extend(returning)
        return (
            f"You play {card.name}, wiping {len(destroyed)} permanent card(s) and "
            f"restoring {_names(returning)} from the banished pile."
        )

    if card.type is CardType.COMPACT:
        freed = _free_tokens(state, card.value)
        return f"You play {card.name}, freeing {freed} token(s) of context."

    if card.type is CardType.FREE_PLAY:
        state.free_plays += card.value
        return f"You play {card.name} - the next {card.value} card(s) this turn cost no tokens."

    if card.type is CardType.GLITCH:
        return f"You flush a {card.name} out of your hand."

    if card.type in CONTROL_FLOW_TYPES:
        # Only run_program gives these meaning; played on the spot they idle.
        return f"You play {card.name} - with no program running, it does nothing."

    if card.type is CardType.BLOCK:
        amount = block_amount(state, card, multiplier, bonus)
        state.player_block += amount
        return f"You play {card.name}, gaining {amount} block."

    if card.type is CardType.HEAL:
        amount = round((card.value + total(state.artifacts, "heal_bonus") + bonus) * multiplier)
        healed = heal(player, amount)
        return f"You play {card.name}, healing {healed} HP."

    # FINAL_STRIKE
    destroyed = [c for c in state.field if c is not None]
    state.banished_pile.extend(destroyed)
    state.field = _empty_field(state)
    damage = round(card.value * len(destroyed) * multiplier)
    absorbed, dealt = _damage_enemy(state, damage)
    return (
        f"You play {card.name}, destroying {len(destroyed)} permanent card(s) for "
        f"{damage} damage. {state.enemy.name} at {state.enemy_hp} HP."
    )


def _empty_field(state: CombatState) -> list[Card | None]:
    return [] if state.program_mode else [None] * FIELD_SIZE


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
    # A lock only lasts the player turn it was cast for.
    state.locked_slots = []
    if state.program_mode:
        log.extend(run_program(state, player, rng))
        if state.enemy_hp <= 0 or player.hp <= 0:
            return log

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
        how = f"uses {name}, gaining" if (name := move_name(state)) else "braces itself, gaining"
        log.append(f"{state.enemy.name} {how} {gained} block.")
    elif state.enemy_intent is not EnemyIntentType.ATTACK:
        log.extend(_special_move(state, player, rng))
        if state.enemy_hp <= 0:
            return log
    else:
        armor = player_armor(state)
        reduction = state.player_block + armor
        # The d6 on top of the move's hit.
        low, high = intent_hits(state)[0]
        raw_damage = low - 1 + rng.randint(1, high - low + 1)
        blocked = min(raw_damage, reduction)
        taken = raw_damage - blocked
        player.hp = max(player.hp - taken, 0)
        attack_name = move_name(state) or state.enemy.attack_name

        if blocked > 0:
            armor_note = f" (includes {armor} armor)" if armor else ""
            log.append(
                f"{state.enemy.name} uses {attack_name}. You block "
                f"{blocked}{armor_note} and take {taken} damage. You are at {player.hp} HP."
            )
        else:
            log.append(
                f"{state.enemy.name} uses {attack_name} for {taken} damage. "
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

    log.extend(_affix_after_turn(state))
    log.extend(_tick_statuses(state, player))
    if state.enemy_hp <= 0 or player.hp <= 0:
        return log
    state.player_block = 0
    _roll_next_intent(state, rng)
    state.turn += 1
    state.plays_this_turn = 0
    state.free_plays = sum(c.value for c in state.field if c and c.type is CardType.OPENER)
    if state.token_limit is not None:
        _free_tokens(state, token_regen(state))
    # Unplayed hand cards carry over to next turn; a fixed number of cards
    # is drawn on top, so holding cards back grows the hand (up to the limit).
    _draw(state, cards_per_turn(state), rng)
    return log


def _affix_after_turn(state: CombatState) -> list[str]:
    """What an elite's affix does once it has acted."""
    name, affix = state.enemy.name, state.enemy.affix
    if affix is Affix.ARMORED:
        gained = round(state.enemy.attack * ARMORED_BLOCK_FACTOR)
        state.enemy_block += gained
        return [f"{name}'s plating raises {gained} block."]
    if affix is Affix.REGENERATING and state.enemy_hp < state.enemy.hp:
        before = state.enemy_hp
        state.enemy_hp = min(state.enemy.hp, before + round(state.enemy.attack * REGEN_FACTOR))
        return [f"{name} regenerates {state.enemy_hp - before} HP. {name} at {state.enemy_hp} HP."]
    return []


def _afflict(state: CombatState, status: Status, amount: int) -> str:
    """Put `amount` of `status` on the enemy (stacks or turns add up)."""
    state.enemy_status[status] = state.enemy_status.get(status, 0) + amount
    return f"{state.enemy.name} is {status.value} ({state.enemy_status[status]})."


def _tick_statuses(state: CombatState, player: PlayerState) -> list[str]:
    """End of the round: Malware bites on both sides, then every status
    counts down one - Malware a stack, Exposed/Throttled a turn."""
    log: list[str] = []
    name = state.enemy.name
    if stacks := state.enemy_status.get(Status.MALWARE, 0):
        state.enemy_hp = max(state.enemy_hp - stacks, 0)
        log.append(f"Malware eats {stacks} HP off {name}. {name} at {state.enemy_hp} HP.")
    if stacks := state.player_status.get(Status.MALWARE, 0):
        player.hp = max(player.hp - stacks, 0)
        log.append(f"Malware eats {stacks} of your HP. You are at {player.hp} HP.")
    for statuses in (state.enemy_status, state.player_status):
        for status in list(statuses):
            statuses[status] -= 1
            if statuses[status] <= 0:
                del statuses[status]
    return log


def _glitch(state: CombatState, n: int) -> Card:
    """A junk card for the draw pile - this fight only, the deck never sees it."""
    serial = len(state.draw_pile) + len(state.discard_pile) + len(state.banished_pile) + n
    return Card(
        id=f"glitch-{state.turn}-{serial}",
        name="Glitch",
        type=CardType.GLITCH,
        value=0,
        exhaust=True,
        token_cost=0,
        description="Does nothing. Play it to flush it out.",
    )


def _special_move(state: CombatState, player: PlayerState, rng: random.Random) -> list[str]:
    """Resolve everything but a plain attack or brace."""
    name = state.enemy.name
    intent = state.enemy_intent
    # A named move announces itself; an OVERLOAD shares its CHARGE's name.
    uses = f"uses {own}: " if (own := move_name(state)) else ""
    if intent is EnemyIntentType.CHARGE:
        gained = enemy_block_gain(state)
        state.enemy_block += gained
        return [f"{name} {uses}charges up, gaining {gained} block - an overload is coming!"]

    log: list[str] = []
    if intent is EnemyIntentType.PURGE:
        slots = reversed(range(len(state.field)))
        slot = next((i for i in slots if state.field[i] is not None), None)
        if slot is not None and state.program_mode:
            purged = state.field.pop(slot)
            state.banished_pile.append(purged)
            log.append(f"{name} purges your {purged.name} - your newest background process!")
        elif slot is not None:
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
        EnemyIntentType.PURGE: "strikes" if own else f"strikes with {state.enemy.attack_name}",
        EnemyIntentType.INFECT: "infects you"
        if own
        else f"infects you with {state.enemy.attack_name}",
        EnemyIntentType.LOCK: "jams your field" if own else "strikes",
        EnemyIntentType.CORRUPT: "corrupts your code" if own else "strikes",
        EnemyIntentType.INTERRUPT: "strikes",
        EnemyIntentType.REFACTOR: "strikes",
    }[intent]
    rolled = " + ".join(str(h) for h in hits)
    log.append(
        f"{name} {uses}{move} ({rolled}). You take {taken} damage. You are at {player.hp} HP."
    )
    if intent is EnemyIntentType.LOCK:
        # A program locks one of its lines - they are all empty by now.
        empty = (
            list(range(len(state.program)))
            if state.program_mode
            else [i for i, c in enumerate(state.field) if c is None]
        )
        if empty:
            slot = rng.choice(empty)
            state.locked_slots = [slot]
            kind = "Line" if state.program_mode else "Slot"
            log.append(f"{kind} {slot + 1} is locked for your next turn.")
    if intent is EnemyIntentType.CORRUPT:
        glitches = [_glitch(state, i) for i in range(current_move(state).stacks)]
        for glitch in glitches:
            state.draw_pile.insert(rng.randrange(len(state.draw_pile) + 1), glitch)
        log.append(f"{len(glitches)} Glitch card(s) seep into your draw pile.")
    if intent is EnemyIntentType.INFECT:
        stacks = current_move(state).stacks if current_move(state) else 0
        state.player_status[Status.MALWARE] = state.player_status.get(Status.MALWARE, 0) + stacks
        log.append(
            f"{stacks} Malware creeps into your systems "
            f"({state.player_status[Status.MALWARE]} in total)."
        )
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
    boss_phases: int = 2,
    program_mode: bool = False,
) -> tuple[bool, list[str]]:
    """Play out a full fight non-interactively: dump the hand into the first
    empty field slot each turn, then end the turn, until someone runs out of HP.
    It never plays past the context window - no gambling on hallucinations.
    """
    state, log = start_combat(
        deck,
        enemy,
        rng,
        player.artifacts,
        boss=boss,
        boss_phases=boss_phases,
        character=player.character,
        program_mode=program_mode,
    )

    for _ in range(MAX_AUTO_TURNS):
        if state.enemy_hp <= 0 or player.hp <= 0:
            break
        for _ in range(MAX_AUTO_PLAYS_PER_TURN):
            play = next(
                (
                    (i, slots[0])
                    for i, c in enumerate(state.hand)
                    if not overflows(state, c) and (slots := free_slots(state, c))
                ),
                None,
            )
            if play is None:
                break
            log.append(play_card(state, *play, player, rng))
            # A thorny elite or a hallucination can take the player down mid-turn.
            if state.enemy_hp <= 0 or player.hp <= 0:
                break
        if state.enemy_hp <= 0 or player.hp <= 0:
            break
        log.extend(end_turn(state, player, rng))

    return state.enemy_hp <= 0, log
