from agentic_rogue_like.models import (
    MapNode,
    NodeType,
    PlayerState,
    RunState,
    RunStatus,
)


def test_player_is_alive_above_zero_hp() -> None:
    player = PlayerState(hp=10, max_hp=10)
    assert player.is_alive


def test_player_is_not_alive_at_zero_hp() -> None:
    player = PlayerState(hp=0, max_hp=10)
    assert not player.is_alive


def test_run_state_defaults_to_ongoing() -> None:
    run = RunState(seed=1, player=PlayerState(hp=10, max_hp=10))
    assert run.status is RunStatus.ONGOING
    assert run.nodes == {}


def test_map_node_tracks_connections() -> None:
    node = MapNode(id="0-0", floor=0, type=NodeType.COMBAT, connections=["1-0", "1-1"])
    assert node.connections == ["1-0", "1-1"]
    assert not node.visited
