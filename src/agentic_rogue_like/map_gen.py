"""Procedural node-map generation - the deterministic backbone every run is built on.

Later, node *content* (which enemy, which event) comes from the encounter
agent (Phase 2); this module only decides the map's shape.
"""

from __future__ import annotations

import random

from .models import MapNode, NodeType

NUM_FLOORS = 8
MIN_NODES_PER_FLOOR = 2
MAX_NODES_PER_FLOOR = 4

_FLOOR_WEIGHTS: dict[NodeType, int] = {
    NodeType.COMBAT: 5,
    NodeType.ELITE: 2,
    NodeType.EVENT: 3,
    NodeType.SHOP: 1,
    NodeType.REST: 2,
}


ELITE_MIN_FLOOR = 3


def _node_type_for_floor(floor: int, rng: random.Random, act: int = 1) -> NodeType:
    if floor == 0:
        # A later act opens on a single camp the player lands in, already
        # resolved (see engine.advance_act) - the boss fight was enough.
        return NodeType.COMBAT if act <= 1 else NodeType.REST
    if floor == NUM_FLOORS - 1:
        return NodeType.BOSS

    weights = _FLOOR_WEIGHTS
    if floor < ELITE_MIN_FLOOR:
        weights = {t: w for t, w in _FLOOR_WEIGHTS.items() if t is not NodeType.ELITE}
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def generate_map(seed: int, act: int = 1) -> dict[str, MapNode]:
    """Build a layered graph: each floor's nodes connect to 1-2 nodes on the next floor.

    Every node past floor 0 is guaranteed at least one incoming connection
    and every non-boss node at least one outgoing one, so there are no dead
    ends and no unreachable nodes. Act 1's map comes from `seed` alone, so
    it is the same map runs always had; later acts start from a single node.
    """
    rng = random.Random(seed if act <= 1 else f"{seed}-act-{act}")
    nodes: dict[str, MapNode] = {}
    floors: list[list[str]] = []

    for floor in range(NUM_FLOORS):
        is_boss_floor = floor == NUM_FLOORS - 1
        single = is_boss_floor or (floor == 0 and act > 1)
        count = 1 if single else rng.randint(MIN_NODES_PER_FLOOR, MAX_NODES_PER_FLOOR)
        floor_ids = []
        for i in range(count):
            node_id = f"{floor}-{i}"
            nodes[node_id] = MapNode(
                id=node_id, floor=floor, type=_node_type_for_floor(floor, rng, act)
            )
            floor_ids.append(node_id)
        floors.append(floor_ids)

    for floor in range(NUM_FLOORS - 1):
        current_ids = floors[floor]
        next_ids = floors[floor + 1]
        reached: set[str] = set()

        for node_id in current_ids:
            branch_count = 1 if len(next_ids) == 1 else rng.randint(1, 2)
            targets = rng.sample(next_ids, k=min(branch_count, len(next_ids)))
            nodes[node_id].connections = targets
            reached.update(targets)

        for missing in set(next_ids) - reached:
            source = rng.choice(current_ids)
            nodes[source].connections.append(missing)

    return nodes
