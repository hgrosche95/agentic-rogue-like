"""The terminal-playable core loop - Phase 1, no LLM involved yet.

Ties map generation, combat and events together into a single playable run.
This is the loop the encounter agent (Phase 2) plugs into later: it only
replaces *where node content comes from*, not this loop's structure.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from .agent.encounter_agent import enemy_for_node
from .combat import resolve_combat
from .events import EventOption, GameEvent, random_event
from .map_gen import NUM_FLOORS, generate_map
from .models import NodeType, PlayerState, RunState, RunStatus

ChooseEventOption = Callable[[GameEvent], EventOption]


def new_run(seed: int) -> RunState:
    player = PlayerState(hp=50, max_hp=50, attack=5, gold=0)
    nodes = generate_map(seed)
    return RunState(seed=seed, player=player, nodes=nodes, current_node_id="0-0")


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
    run.history.append(event.description)
    return event


def apply_event_choice(run: RunState, option: EventOption, rng: random.Random) -> None:
    """Second half of resolving an EVENT node: apply the chosen option's effect."""
    outcome = option.effect(run.player, rng)
    run.history.append(f"> {option.label}: {outcome}")


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
        )
        result = resolve_combat(run.player, enemy, rng)
        run.history.extend(result.log)

        if not result.victory:
            run.status = RunStatus.DEFEAT
        elif node.type is NodeType.BOSS:
            run.status = RunStatus.VICTORY
        else:
            reward = rng.randint(15, 35)
            run.player.gold += reward
            run.history.append(f"You loot {reward} gold from the {enemy.name}.")

    elif node.type is NodeType.REST:
        healed = min(15, run.player.max_hp - run.player.hp)
        run.player.hp += healed
        run.history.append(f"You rest and recover {healed} HP.")

    elif node.type is NodeType.SHOP:
        # TODO(Phase 3): the shop is announced but sells nothing until there
        # are relics and cards to spend gold on.
        run.history.append(f"A merchant offers wares. You have {run.player.gold} gold.")
