from agentic_rogue_like.map_gen import NUM_FLOORS, generate_map
from agentic_rogue_like.models import NodeType


def test_generates_all_floors() -> None:
    nodes = generate_map(seed=42)
    floors_present = {node.floor for node in nodes.values()}
    assert floors_present == set(range(NUM_FLOORS))


def test_last_floor_is_single_boss_node() -> None:
    nodes = generate_map(seed=42)
    last_floor_nodes = [n for n in nodes.values() if n.floor == NUM_FLOORS - 1]
    assert len(last_floor_nodes) == 1
    assert last_floor_nodes[0].type is NodeType.BOSS


def test_start_node_is_combat() -> None:
    nodes = generate_map(seed=42)
    assert nodes["0-0"].type is NodeType.COMBAT


def test_every_node_past_floor_zero_has_incoming_connection() -> None:
    nodes = generate_map(seed=42)
    reachable: set[str] = set()
    for node in nodes.values():
        reachable.update(node.connections)

    for node in nodes.values():
        if node.floor > 0:
            assert node.id in reachable, f"{node.id} is unreachable"


def test_every_non_boss_node_has_outgoing_connection() -> None:
    nodes = generate_map(seed=42)
    for node in nodes.values():
        if node.type is not NodeType.BOSS:
            assert node.connections, f"{node.id} is a dead end"


def test_same_seed_is_deterministic() -> None:
    assert generate_map(seed=7) == generate_map(seed=7)
