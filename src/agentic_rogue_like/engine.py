"""The terminal-playable core loop - Phase 1, no LLM involved yet.

Ties map generation, combat and events together into a single playable run.
This is the loop the encounter agent (Phase 2) plugs into later: it only
replaces *where node content comes from*, not this loop's structure.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from .combat import resolve_combat
from .enemies import pick_enemy
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


def resolve_node(
    run: RunState,
    rng: random.Random,
    choose_event_option: ChooseEventOption | None = None,
) -> None:
    node = run.nodes[run.current_node_id]
    node.visited = True
    run.floor = node.floor

    if node.type in (NodeType.COMBAT, NodeType.ELITE, NodeType.BOSS):
        enemy = pick_enemy(
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

    elif node.type is NodeType.EVENT:
        event = random_event(rng)
        run.history.append(event.description)
        option = choose_event_option(event) if choose_event_option else rng.choice(event.options)
        outcome = option.effect(run.player, rng)
        run.history.append(f"> {option.label}: {outcome}")

    elif node.type is NodeType.REST:
        healed = min(15, run.player.max_hp - run.player.hp)
        run.player.hp += healed
        run.history.append(f"You rest and recover {healed} HP.")

    elif node.type is NodeType.SHOP:
        run.history.append(f"A merchant offers wares. You have {run.player.gold} gold.")
