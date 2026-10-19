"""The terminal-playable core loop - Phase 1, no LLM involved yet.

Ties map generation, combat and events together into a single playable run.
This is the loop the encounter agent (Phase 2) plugs into later: it only
replaces *where node content comes from*, not this loop's structure.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from .agent.encounter_agent import enemy_for_node
from .agent.event_agent import event_for_room
from .agent.narrator import narrate
from .artifacts import ARTIFACT_EVERY_STEPS, gain_artifact, heal, roll_artifact_offer, total
from .cards import START_CARD_WEIGHTS, can_upgrade, reward_card, roll_card_reward, upgrade_card
from .characters import CHARACTERS, artifact_pool, reward_pool
from .combat import CombatState, auto_resolve_combat
from .combat import end_turn as _end_combat_turn
from .combat import play_card as _play_combat_card
from .combat import start_combat as _start_combat
from .enemies import escalate, with_affix
from .events import EventOption, GameEvent, apply_option
from .map_gen import NUM_FLOORS, generate_map
from .models import (
    DEFAULT_SETTING,
    Artifact,
    Card,
    Character,
    Enemy,
    MapNode,
    NodeType,
    PlayerState,
    RestSite,
    RunState,
    RunStatus,
)
from .shop import MIN_DECK_SIZE, leave_shop, roll_shop
from .style import answers, play_style, taunt

ChooseEventOption = Callable[[GameEvent], EventOption]
# Index into the offered cards, or None to skip the reward.
ChooseCardReward = Callable[[list[Card]], int | None]
# Index into the offered artifacts - picking one is not optional.
ChooseArtifact = Callable[[list[Artifact]], int]
# Called while a shop is open, to buy from it (shop.buy_card/buy_artifact);
# the shop closes when it returns.
BrowseShop = Callable[[RunState], None]
# What to do at a rest site: ("heal", None), or ("upgrade" | "remove", deck index).
RestAction = tuple[str, int | None]
ChooseRest = Callable[[RunState], RestAction]
# (setting, situation) -> flavor text or None. Defaults to a live narrate()
# call; the web API passes one that reads background-prefetched text instead.
Narrator = Callable[[str, str], str | None]

# Tuned with `balance-sim` together with enemies.escalate() for a run win
# rate below 50% - see the README's Balancing section.
# Dr. Chronos's - every character's own stats live in characters.py.
PLAYER_HP = CHARACTERS[Character.CHRONOS].hp
PLAYER_ATTACK = CHARACTERS[Character.CHRONOS].attack
REST_HEAL = 15

# Beating an act's boss opens the next act's map (advance_act); beating the
# last act's boss wins the run. Between acts the player recovers this share
# of their max HP, on top of the boss's gold and card reward.
NUM_ACTS = 2
ACT_HEAL_PERCENT = 40


def boss_phases(act: int) -> int:
    """Act 1's boss has two phases, every later act's boss a third one."""
    return 2 if act <= 1 else 3


REST_SITUATION = "a weary adventurer resting and tending their wounds"
SHOP_SITUATION = "a traveling merchant offering strange wares for sale"


def new_run(
    seed: int,
    setting: str = DEFAULT_SETTING,
    character: Character = Character.CHRONOS,
    program_mode: bool = False,
) -> RunState:
    """`program_mode`: the field runs as a program (combat.run_program) for
    the whole run, and rewards offer control flow cards."""
    hero = CHARACTERS[character]
    player = PlayerState(
        character=character,
        hp=hero.hp,
        max_hp=hero.hp,
        attack=hero.attack,
        gold=0,
        deck=hero.deck(),
    )
    nodes = generate_map(seed)
    run = RunState(
        seed=seed,
        player=player,
        nodes=nodes,
        current_node_id="0-0",
        setting=setting,
        program_mode=program_mode,
    )
    # Its own rng, so offering artifacts doesn't shift the run rng's sequence
    # (enemies, events, rewards) compared to a run without them.
    run.artifact_offer = roll_artifact_offer(
        random.Random(f"{seed}-artifacts-0"), [], pool=artifact_pool(run)
    )
    # ... and so does the starting card pick: three uncommon/rare cards, one of
    # which (or none) joins the starter deck before the first room.
    run.card_reward = roll_card_reward(
        random.Random(f"{seed}-start-cards"), weights=START_CARD_WEIGHTS, pool=reward_pool(run)
    )
    return run


def available_choices(run: RunState) -> list[str]:
    return run.nodes[run.current_node_id].connections


def move_to(run: RunState, node_id: str) -> None:
    """Step onto `node_id`; every ARTIFACT_EVERY_STEPS steps an artifact offer waits there."""
    run.current_node_id = node_id
    run.steps += 1
    if run.steps % ARTIFACT_EVERY_STEPS == 0:
        rng = random.Random(f"{run.seed}-artifacts-{run.steps}")
        run.artifact_offer = (
            roll_artifact_offer(rng, run.player.artifacts, pool=artifact_pool(run)) or None
        )


def choose_artifact(run: RunState, index: int) -> None:
    """Take artifact `index` of the pending offer.

    Raises ValueError if no offer is pending or the index is out of range.
    """
    offer = run.artifact_offer
    if offer is None:
        raise ValueError("no artifact offer pending")
    if not 0 <= index < len(offer):
        raise ValueError(f"artifact index {index} is out of range")
    gain_artifact(run.player, offer[index])
    run.history.append(f"You install {offer[index].name}: {offer[index].description}")
    run.artifact_offer = None


def start_event(
    run: RunState,
    rng: random.Random,
    narrator: Narrator | None = None,
    prefetched_event: Callable[[], GameEvent] | None = None,
) -> GameEvent:
    """First half of resolving an EVENT node: draw the event, record its text.

    Split out from `resolve_node` so a caller that can't supply an option
    synchronously (the web API, which has to wait for a second request with
    the player's choice) can pause here instead of blocking on a callback.
    """
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor

    event, written_by_agent = event_for_room(rng, run.setting, prefetched_event)
    # The agent already writes for the setting; the static pool gets themed.
    flavor = None if written_by_agent else (narrator or narrate)(run.setting, event.description)
    if flavor:
        # EVENT_POOL entries are shared singletons re-picked by every run -
        # model_copy() makes a themed copy instead of mutating the pool itself.
        event = event.model_copy(update={"description": flavor})
    run.history.append(event.description)
    return event


def open_shop(run: RunState, narrator: Narrator | None = None) -> None:
    """Enter a SHOP room: roll its stock and leave it open (run.shop).

    Like start_event, split out from resolve_node so the web API can keep the
    shop open across requests while the player browses.
    """
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor
    flavor = (narrator or narrate)(run.setting, SHOP_SITUATION)
    if flavor:
        run.history.append(flavor)
    run.shop = roll_shop(run)
    run.history.append(
        f"A merchant lays out {len(run.shop.cards)} cards and "
        f"{len(run.shop.artifacts)} artifacts. You have {run.player.gold} gold."
    )


def open_rest(run: RunState, narrator: Narrator | None = None) -> None:
    """Enter a REST room and leave its choice open (run.rest): heal, upgrade
    a card, or remove a card - one of the three.

    Like open_shop, split out from resolve_node so the web API can wait for
    the player's pick in a second request.
    """
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor
    flavor = (narrator or narrate)(run.setting, REST_SITUATION)
    if flavor:
        run.history.append(flavor)
    run.rest = RestSite(heal_amount=REST_HEAL + total(run.player.artifacts, "rest_heal"))


def _open_rest(run: RunState) -> RestSite:
    if run.rest is None:
        raise ValueError("no rest site open")
    return run.rest


def rest_heal(run: RunState) -> None:
    healed = heal(run.player, _open_rest(run).heal_amount)
    run.history.append(f"You rest and recover {healed} HP.")
    run.rest = None


def rest_upgrade(run: RunState, deck_index: int) -> None:
    """Upgrade card `deck_index` for good. Raises ValueError for a bad index
    or a card that can't be upgraded (see cards.can_upgrade)."""
    _open_rest(run)
    deck = run.player.deck
    if not 0 <= deck_index < len(deck):
        raise ValueError(f"deck index {deck_index} is out of range")
    before = deck[deck_index]
    deck[deck_index] = upgrade_card(before)
    run.history.append(f"You rework {before.name} into {deck[deck_index].name}.")
    run.rest = None


def rest_remove(run: RunState, deck_index: int) -> None:
    """Remove card `deck_index` for free - unlike the black market's removal,
    it costs the rest instead of gold, and doesn't raise the market's price."""
    _open_rest(run)
    deck = run.player.deck
    if not 0 <= deck_index < len(deck):
        raise ValueError(f"deck index {deck_index} is out of range")
    if len(deck) <= MIN_DECK_SIZE:
        raise ValueError(f"your deck can't get smaller than {MIN_DECK_SIZE} cards")
    card = deck.pop(deck_index)
    run.history.append(f"You strip {card.name} out of your deck.")
    run.rest = None


def apply_rest_action(run: RunState, action: RestAction) -> None:
    kind, index = action
    if kind == "heal":
        rest_heal(run)
    elif kind == "upgrade" and index is not None:
        rest_upgrade(run, index)
    elif kind == "remove" and index is not None:
        rest_remove(run, index)
    else:
        raise ValueError(f"unknown rest action {action!r}")


def upgradable_indices(run: RunState) -> list[int]:
    return [i for i, card in enumerate(run.player.deck) if can_upgrade(card)]


def apply_event_choice(run: RunState, option: EventOption, rng: random.Random) -> None:
    """Second half of resolving an EVENT node: apply the chosen option's effect."""
    outcome = apply_option(option, run.player, reward_pool(run), rng)
    run.history.append(f"> {option.label}: {outcome}")


def advance_act(run: RunState) -> None:
    """Move the run onto the next act's map, at its (already resolved) start camp.

    Called once the current act's boss is beaten. The player keeps
    everything - deck, artifacts, gold - and recovers ACT_HEAL_PERCENT of
    their max HP; enemies from here on are stronger (enemies.escalate).
    """
    run.act += 1
    run.nodes = generate_map(run.seed, run.act)
    run.current_node_id = "0-0"
    run.nodes["0-0"].visited = True
    run.floor = 0
    healed = heal(run.player, run.player.max_hp * ACT_HEAL_PERCENT // 100)
    run.history.append(
        f"The way to act {run.act} opens. You catch your breath and recover {healed} HP - "
        f"the enemies ahead are stronger."
    )


def _finish_combat(
    run: RunState, node: MapNode, enemy_name: str, victory: bool, rng: random.Random
) -> None:
    if not victory:
        run.history.append("You have fallen.")
        run.status = RunStatus.DEFEAT
        return
    run.history.append("Victory!")
    if node.type is NodeType.BOSS and run.act >= NUM_ACTS:
        run.status = RunStatus.VICTORY
        return
    reward = rng.randint(15, 35)
    if node.type is NodeType.BOSS:
        reward *= 2
    run.player.gold += reward
    run.history.append(f"You loot {reward} gold from the {enemy_name}.")
    if healed := heal(run.player, total(run.player.artifacts, "heal_after_combat")):
        run.history.append(f"Your artifacts patch you up for {healed} HP.")
    run.card_reward = roll_card_reward(
        rng,
        elite=node.type is not NodeType.COMBAT,
        pool=reward_pool(run),
    )
    if node.type is NodeType.BOSS:
        advance_act(run)


def choose_card_reward(run: RunState, index: int | None) -> None:
    """Take card `index` of the pending reward into the deck, or skip it (None).

    Raises ValueError if no reward is pending or the index is out of range.
    """
    offer = run.card_reward
    if offer is None:
        raise ValueError("no card reward pending")
    if index is None:
        run.history.append("You leave the cards behind.")
    else:
        if not 0 <= index < len(offer):
            raise ValueError(f"card index {index} is out of range")
        card = reward_card(offer[index], run.player.deck)
        run.player.deck.append(card)
        run.history.append(f"You add {card.name} to your deck.")
    run.card_reward = None


def _room_enemy(
    run: RunState,
    node: MapNode,
    rng: random.Random,
    prefetched: Callable[[], Enemy] | None = None,
) -> Enemy:
    """The enemy of a combat room, ready to fight: picked (agent or pool),
    affixed if elite, escalated for the timeline.

    Once the player's deck shows a clear style (style.play_style), the AGI
    prefers enemies and affixes that answer it - and an enemy that does opens
    its fight with a taunt. An elite's affix comes from its own rng, seeded
    per room, so it never shifts the run rng's other draws.
    """
    boss = node.type is NodeType.BOSS
    style = None if boss else play_style(run.player.deck)
    enemy = enemy_for_node(
        enemy_id=f"agent-{rng.getrandbits(32):08x}",
        floor=node.floor,
        num_floors=NUM_FLOORS,
        elite=node.type is NodeType.ELITE,
        boss=boss,
        rng=rng,
        setting=run.setting,
        prefetched=prefetched,
        act=run.act,
        style=style,
    )
    if node.type is NodeType.ELITE:
        affix_rng = random.Random(f"{run.seed}-affix-{run.act}-{node.id}")
        enemy = with_affix(enemy, affix_rng, style)
    if style is not None and answers(enemy, style):
        enemy = enemy.model_copy(update={"taunt": taunt(style)})
    return escalate(enemy, node.floor, NUM_FLOORS, run.act)


def start_combat_node(
    run: RunState,
    rng: random.Random,
    prefetched_enemy: Callable[[], Enemy] | None = None,
) -> CombatState:
    """First step of resolving a COMBAT/ELITE/BOSS node the interactive way.

    Mirrors start_event: picks the enemy and shuffles/draws an opening hand,
    then hands the CombatState back to the caller (the web API) to hold
    between requests - play_combat_card/end_combat_turn advance it one
    action at a time instead of auto_resolve_combat playing it out in one go.
    """
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor

    enemy = _room_enemy(run, node, rng, prefetched_enemy)
    state, log = _start_combat(
        run.player.deck,
        enemy,
        rng,
        run.player.artifacts,
        boss=node.type is NodeType.BOSS,
        boss_phases=boss_phases(run.act),
        character=run.player.character,
        program_mode=run.program_mode,
    )
    run.history.extend(log)
    return state


def play_combat_card(
    run: RunState, state: CombatState, hand_index: int, slot_index: int, rng: random.Random
) -> None:
    """Raises ValueError (via combat.play_card) on an invalid index or an occupied slot."""
    run.history.append(_play_combat_card(state, hand_index, slot_index, run.player, rng))


def end_combat_turn(
    run: RunState, state: CombatState, rng: random.Random, discard: list[int] | None = None
) -> None:
    """Raises ValueError (via combat.end_turn) if `discard` doesn't bring the
    hand down to exactly the hand limit."""
    run.history.extend(_end_combat_turn(state, run.player, rng, discard))


def finalize_combat(run: RunState, state: CombatState, rng: random.Random) -> None:
    """Call once state.enemy_hp <= 0 or run.player.hp <= 0 to close out an interactive fight."""
    node = run.nodes[run.current_node_id]
    _finish_combat(run, node, state.enemy.name, victory=run.player.hp > 0, rng=rng)


def resolve_node(
    run: RunState,
    rng: random.Random,
    choose_event_option: ChooseEventOption | None = None,
    narrator: Narrator | None = None,
    choose_card: ChooseCardReward | None = None,
    choose_artifact_option: ChooseArtifact | None = None,
    browse_shop: BrowseShop | None = None,
    choose_rest: ChooseRest | None = None,
) -> None:
    if run.artifact_offer is not None:
        offer = run.artifact_offer
        choose_artifact(
            run,
            choose_artifact_option(offer) if choose_artifact_option else rng.randrange(len(offer)),
        )

    if run.card_reward is not None:  # the starting card pick
        offer = run.card_reward
        choose_card_reward(run, choose_card(offer) if choose_card else rng.randrange(len(offer)))

    node = run.nodes[run.current_node_id]

    if node.type is NodeType.EVENT:
        event = start_event(run, rng, narrator)
        option = choose_event_option(event) if choose_event_option else rng.choice(event.options)
        apply_event_choice(run, option, rng)
        return

    node.visited = True
    run.floor = node.floor

    if node.type in (NodeType.COMBAT, NodeType.ELITE, NodeType.BOSS):
        enemy = _room_enemy(run, node, rng)
        victory, log = auto_resolve_combat(
            run.player.deck,
            enemy,
            run.player,
            rng,
            boss=node.type is NodeType.BOSS,
            boss_phases=boss_phases(run.act),
            program_mode=run.program_mode,
        )
        run.history.extend(log)
        _finish_combat(run, node, enemy.name, victory, rng)
        if run.card_reward is not None:
            offer = run.card_reward
            choose_card_reward(
                run, choose_card(offer) if choose_card else rng.randrange(len(offer))
            )

    elif node.type is NodeType.REST:
        # without a choose_rest callback (bots, tests) the player heals
        open_rest(run, narrator)
        apply_rest_action(run, choose_rest(run) if choose_rest else ("heal", None))

    elif node.type is NodeType.SHOP:
        # without a browse_shop callback (bots, tests) nothing is bought
        open_shop(run, narrator)
        if browse_shop is not None:
            browse_shop(run)
        leave_shop(run)
