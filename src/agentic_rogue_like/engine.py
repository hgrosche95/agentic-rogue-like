"""The terminal-playable core loop - Phase 1, no LLM involved yet.

Ties map generation, combat and events together into a single playable run.
This is the loop the encounter agent (Phase 2) plugs into later: it only
replaces *where node content comes from*, not this loop's structure.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import replace

from .agent.encounter_agent import enemy_for_node
from .agent.narrator import narrate
from .artifacts import ARTIFACT_EVERY_STEPS, gain_artifact, heal, roll_artifact_offer, total
from .cards import reward_card, roll_card_reward, starter_deck
from .combat import CombatState, auto_resolve_combat
from .combat import end_turn as _end_combat_turn
from .combat import play_card as _play_combat_card
from .combat import start_combat as _start_combat
from .enemies import escalate
from .events import EventOption, GameEvent, random_event
from .map_gen import NUM_FLOORS, generate_map
from .models import (
    DEFAULT_SETTING,
    Artifact,
    Card,
    Enemy,
    MapNode,
    NodeType,
    PlayerState,
    RunState,
    RunStatus,
)
from .shop import leave_shop, roll_shop

ChooseEventOption = Callable[[GameEvent], EventOption]
# Index into the offered cards, or None to skip the reward.
ChooseCardReward = Callable[[list[Card]], int | None]
# Index into the offered artifacts - picking one is not optional.
ChooseArtifact = Callable[[list[Artifact]], int]
# Called while a shop is open, to buy from it (shop.buy_card/buy_artifact);
# the shop closes when it returns.
BrowseShop = Callable[[RunState], None]
# (setting, situation) -> flavor text or None. Defaults to a live narrate()
# call; the web API passes one that reads background-prefetched text instead.
Narrator = Callable[[str, str], str | None]

# Tuned with `balance-sim` together with enemies.escalate() for a run win
# rate below 50% - see the README's Balancing section.
PLAYER_HP = 45
PLAYER_ATTACK = 2
REST_HEAL = 15

# Beating an act's boss opens the next act's map (advance_act); beating the
# last act's boss wins the run. Between acts the player recovers this share
# of their max HP, on top of the boss's gold and card reward.
NUM_ACTS = 2
ACT_HEAL_PERCENT = 50

REST_SITUATION = "a weary adventurer resting and tending their wounds"
SHOP_SITUATION = "a traveling merchant offering strange wares for sale"


def new_run(seed: int, setting: str = DEFAULT_SETTING) -> RunState:
    player = PlayerState(
        hp=PLAYER_HP, max_hp=PLAYER_HP, attack=PLAYER_ATTACK, gold=0, deck=starter_deck()
    )
    nodes = generate_map(seed)
    run = RunState(seed=seed, player=player, nodes=nodes, current_node_id="0-0", setting=setting)
    # Its own rng, so offering artifacts doesn't shift the run rng's sequence
    # (enemies, events, rewards) compared to a run without them.
    run.artifact_offer = roll_artifact_offer(random.Random(f"{seed}-artifacts-0"), [])
    return run


def available_choices(run: RunState) -> list[str]:
    return run.nodes[run.current_node_id].connections


def move_to(run: RunState, node_id: str) -> None:
    """Step onto `node_id`; every ARTIFACT_EVERY_STEPS steps an artifact offer waits there."""
    run.current_node_id = node_id
    run.steps += 1
    if run.steps % ARTIFACT_EVERY_STEPS == 0:
        rng = random.Random(f"{run.seed}-artifacts-{run.steps}")
        run.artifact_offer = roll_artifact_offer(rng, run.player.artifacts) or None


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


def start_event(run: RunState, rng: random.Random, narrator: Narrator | None = None) -> GameEvent:
    """First half of resolving an EVENT node: draw the event, record its text.

    Split out from `resolve_node` so a caller that can't supply an option
    synchronously (the web API, which has to wait for a second request with
    the player's choice) can pause here instead of blocking on a callback.
    """
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor

    event = random_event(rng)
    flavor = (narrator or narrate)(run.setting, event.description)
    if flavor:
        # EVENT_POOL entries are shared singletons re-picked by every run -
        # replace() makes a themed copy instead of mutating the pool itself.
        event = replace(event, description=flavor)
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


def apply_event_choice(run: RunState, option: EventOption, rng: random.Random) -> None:
    """Second half of resolving an EVENT node: apply the chosen option's effect."""
    outcome = option.effect(run.player, rng)
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
    run.card_reward = roll_card_reward(rng, elite=node.type is not NodeType.COMBAT)
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

    enemy = escalate(
        enemy_for_node(
            enemy_id=f"agent-{rng.getrandbits(32):08x}",
            floor=node.floor,
            num_floors=NUM_FLOORS,
            elite=node.type is NodeType.ELITE,
            boss=node.type is NodeType.BOSS,
            rng=rng,
            setting=run.setting,
            prefetched=prefetched_enemy,
            act=run.act,
        ),
        node.floor,
        NUM_FLOORS,
        run.act,
    )
    state, log = _start_combat(
        run.player.deck, enemy, rng, run.player.artifacts, boss=node.type is NodeType.BOSS
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
) -> None:
    if run.artifact_offer is not None:
        offer = run.artifact_offer
        choose_artifact(
            run,
            choose_artifact_option(offer) if choose_artifact_option else rng.randrange(len(offer)),
        )

    node = run.nodes[run.current_node_id]

    if node.type is NodeType.EVENT:
        event = start_event(run, rng, narrator)
        option = choose_event_option(event) if choose_event_option else rng.choice(event.options)
        apply_event_choice(run, option, rng)
        return

    node.visited = True
    run.floor = node.floor

    if node.type in (NodeType.COMBAT, NodeType.ELITE, NodeType.BOSS):
        enemy = escalate(
            enemy_for_node(
                enemy_id=f"agent-{rng.getrandbits(32):08x}",
                floor=node.floor,
                num_floors=NUM_FLOORS,
                elite=node.type is NodeType.ELITE,
                boss=node.type is NodeType.BOSS,
                rng=rng,
                setting=run.setting,
                act=run.act,
            ),
            node.floor,
            NUM_FLOORS,
            run.act,
        )
        victory, log = auto_resolve_combat(
            run.player.deck, enemy, run.player, rng, boss=node.type is NodeType.BOSS
        )
        run.history.extend(log)
        _finish_combat(run, node, enemy.name, victory, rng)
        if run.card_reward is not None:
            offer = run.card_reward
            choose_card_reward(
                run, choose_card(offer) if choose_card else rng.randrange(len(offer))
            )

    elif node.type is NodeType.REST:
        flavor = (narrator or narrate)(run.setting, REST_SITUATION)
        if flavor:
            run.history.append(flavor)
        healed = heal(run.player, REST_HEAL + total(run.player.artifacts, "rest_heal"))
        run.history.append(f"You rest and recover {healed} HP.")

    elif node.type is NodeType.SHOP:
        # without a browse_shop callback (bots, tests) nothing is bought
        open_shop(run, narrator)
        if browse_shop is not None:
            browse_shop(run)
        leave_shop(run)
