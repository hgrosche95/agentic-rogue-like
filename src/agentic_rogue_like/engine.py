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
from .cards import starter_deck
from .combat import CombatState, auto_resolve_combat
from .combat import end_turn as _end_combat_turn
from .combat import play_card as _play_combat_card
from .combat import start_combat as _start_combat
from .events import EventOption, GameEvent, random_event
from .map_gen import NUM_FLOORS, generate_map
from .models import DEFAULT_SETTING, MapNode, NodeType, PlayerState, RunState, RunStatus

ChooseEventOption = Callable[[GameEvent], EventOption]


def new_run(seed: int, setting: str = DEFAULT_SETTING) -> RunState:
    player = PlayerState(hp=50, max_hp=50, attack=5, gold=0, deck=starter_deck())
    nodes = generate_map(seed)
    return RunState(
        seed=seed, player=player, nodes=nodes, current_node_id="0-0", setting=setting
    )


def available_choices(run: RunState) -> list[str]:
    return run.nodes[run.current_node_id].connections


def start_event(run: RunState, rng: random.Random) -> GameEvent:
    """First half of resolving an EVENT node: draw the event, record its text.

    Split out from `resolve_node` so a caller that can't supply an option
    synchronously (the web API, which has to wait for a second request with
    the player's choice) can pause here instead of blocking on a callback.
    """
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor

    event = random_event(rng)
    flavor = narrate(run.setting, event.description)
    if flavor:
        # EVENT_POOL entries are shared singletons re-picked by every run -
        # replace() makes a themed copy instead of mutating the pool itself.
        event = replace(event, description=flavor)
    run.history.append(event.description)
    return event


def apply_event_choice(run: RunState, option: EventOption, rng: random.Random) -> None:
    """Second half of resolving an EVENT node: apply the chosen option's effect."""
    outcome = option.effect(run.player, rng)
    run.history.append(f"> {option.label}: {outcome}")


def _finish_combat(
    run: RunState, node: MapNode, enemy_name: str, victory: bool, rng: random.Random
) -> None:
    if not victory:
        run.history.append("You have fallen.")
        run.status = RunStatus.DEFEAT
        return
    run.history.append("Victory!")
    if node.type is NodeType.BOSS:
        run.status = RunStatus.VICTORY
    else:
        reward = rng.randint(15, 35)
        run.player.gold += reward
        run.history.append(f"You loot {reward} gold from the {enemy_name}.")


def start_combat_node(run: RunState, rng: random.Random) -> CombatState:
    """First step of resolving a COMBAT/ELITE/BOSS node the interactive way.

    Mirrors start_event: picks the enemy and shuffles/draws an opening hand,
    then hands the CombatState back to the caller (the web API) to hold
    between requests - play_combat_card/end_combat_turn advance it one
    action at a time instead of auto_resolve_combat playing it out in one go.
    """
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor

    enemy = enemy_for_node(
        enemy_id=f"agent-{rng.getrandbits(32):08x}",
        floor=node.floor,
        num_floors=NUM_FLOORS,
        elite=node.type is NodeType.ELITE,
        boss=node.type is NodeType.BOSS,
        rng=rng,
        setting=run.setting,
    )
    state, log = _start_combat(run.player.deck, enemy, rng)
    run.history.extend(log)
    return state


def play_combat_card(
    run: RunState, state: CombatState, hand_index: int, slot_index: int, rng: random.Random
) -> None:
    """Raises ValueError (via combat.play_card) on an invalid index or an occupied slot."""
    run.history.append(_play_combat_card(state, hand_index, slot_index, run.player, rng))


def end_combat_turn(run: RunState, state: CombatState, rng: random.Random) -> None:
    run.history.extend(_end_combat_turn(state, run.player, rng))


def finalize_combat(run: RunState, state: CombatState, rng: random.Random) -> None:
    """Call once state.enemy_hp <= 0 or run.player.hp <= 0 to close out an interactive fight."""
    node = run.nodes[run.current_node_id]
    _finish_combat(run, node, state.enemy.name, victory=run.player.hp > 0, rng=rng)


def resolve_node(
    run: RunState,
    rng: random.Random,
    choose_event_option: ChooseEventOption | None = None,
) -> None:
    node = run.nodes[run.current_node_id]

    if node.type is NodeType.EVENT:
        event = start_event(run, rng)
        option = choose_event_option(event) if choose_event_option else rng.choice(event.options)
        apply_event_choice(run, option, rng)
        return

    node.visited = True
    run.floor = node.floor

    if node.type in (NodeType.COMBAT, NodeType.ELITE, NodeType.BOSS):
        enemy = enemy_for_node(
            enemy_id=f"agent-{rng.getrandbits(32):08x}",
            floor=node.floor,
            num_floors=NUM_FLOORS,
            elite=node.type is NodeType.ELITE,
            boss=node.type is NodeType.BOSS,
            rng=rng,
            setting=run.setting,
        )
        victory, log = auto_resolve_combat(run.player.deck, enemy, run.player, rng)
        run.history.extend(log)
        _finish_combat(run, node, enemy.name, victory, rng)

    elif node.type is NodeType.REST:
        flavor = narrate(run.setting, "a weary adventurer resting and tending their wounds")
        if flavor:
            run.history.append(flavor)
        healed = min(15, run.player.max_hp - run.player.hp)
        run.player.hp += healed
        run.history.append(f"You rest and recover {healed} HP.")

    elif node.type is NodeType.SHOP:
        flavor = narrate(run.setting, "a traveling merchant offering strange wares for sale")
        if flavor:
            run.history.append(flavor)
        # TODO(Phase 3): the shop is announced but sells nothing until there
        # are relics and cards to spend gold on.
        run.history.append(f"A merchant offers wares. You have {run.player.gold} gold.")
