import random

import pytest

from agentic_rogue_like.combat import start_combat
from agentic_rogue_like.consumables import (
    CONSUMABLE_POOL,
    add_consumable,
    roll_drop,
    use_consumable,
)
from agentic_rogue_like.engine import _finish_combat, new_run
from agentic_rogue_like.models import (
    MAX_CONSUMABLES,
    Card,
    CardType,
    Consumable,
    ConsumableKind,
    Enemy,
    MapNode,
    NodeType,
    PlayerState,
    Status,
)

STRIKE = Card(id="strike", name="Strike", type=CardType.ATTACK, value=6, description="")


def _item(kind: ConsumableKind) -> Consumable:
    return next(c for c in CONSUMABLE_POOL if c.kind is kind)


def _player(items: list[Consumable] | None = None, hp: int = 50) -> PlayerState:
    return PlayerState(
        hp=hp, max_hp=50, attack=5, deck=[STRIKE] * 20, consumables=list(items or [])
    )


def _combat(player: PlayerState):
    enemy = Enemy(id="foe", name="Foe", hp=100, attack=0, attack_name="Slam")
    state, _ = start_combat(player.deck, enemy, random.Random(1))
    return state


def _player_hp(state, player: PlayerState) -> int:
    return state.player_hp if hasattr(state, "player_hp") else player.hp


def test_pool_has_five_distinct_kinds() -> None:
    assert len(CONSUMABLE_POOL) == 5
    assert {c.kind for c in CONSUMABLE_POOL} == set(ConsumableKind)


def test_add_consumable_caps_at_three() -> None:
    player = _player()
    item = CONSUMABLE_POOL[0]
    assert MAX_CONSUMABLES == 3
    assert [add_consumable(player, item) for _ in range(3)] == [True, True, True]
    assert add_consumable(player, item) is False
    assert len(player.consumables) == 3


def test_player_state_default_consumables_empty() -> None:
    assert PlayerState(hp=10, max_hp=10).consumables == []


def test_heal_script() -> None:
    player = _player([_item(ConsumableKind.HEAL)], hp=20)
    state = _combat(player)
    use_consumable(state, player, 0, random.Random(1))
    assert _player_hp(state, player) == 30

    player = _player([_item(ConsumableKind.HEAL)], hp=45)
    state = _combat(player)
    use_consumable(state, player, 0, random.Random(1))
    assert _player_hp(state, player) == 50


def test_block_script() -> None:
    player = _player([_item(ConsumableKind.BLOCK)])
    state = _combat(player)
    assert state.player_block == 0
    use_consumable(state, player, 0, random.Random(1))
    assert state.player_block == 8


def test_draw_script() -> None:
    player = _player([_item(ConsumableKind.DRAW)])
    state = _combat(player)
    hand = len(state.hand)
    use_consumable(state, player, 0, random.Random(1))
    assert len(state.hand) == hand + 2


def test_damage_script() -> None:
    player = _player([_item(ConsumableKind.DAMAGE)])
    state = _combat(player)
    state.enemy_block = 0
    hp = state.enemy_hp
    use_consumable(state, player, 0, random.Random(1))
    assert state.enemy_hp == hp - 10


def test_purge_script() -> None:
    player = _player([_item(ConsumableKind.PURGE)])
    state = _combat(player)
    state.player_status = {Status.MALWARE: 3}
    use_consumable(state, player, 0, random.Random(1))
    assert Status.MALWARE not in state.player_status


def test_use_removes_item_and_keeps_tokens() -> None:
    player = _player([_item(ConsumableKind.BLOCK), _item(ConsumableKind.HEAL)])
    state = _combat(player)
    tokens = state.tokens_used
    free = state.free_plays
    plays = state.plays_this_turn
    use_consumable(state, player, 0, random.Random(1))
    assert len(player.consumables) == 1
    assert state.tokens_used == tokens
    assert state.free_plays == free
    assert state.plays_this_turn == plays


def test_use_invalid_index_raises() -> None:
    player = _player()
    state = _combat(player)
    with pytest.raises(ValueError):
        use_consumable(state, player, 5, random.Random(1))


def _hitting_seed(node_id: str) -> int:
    run = new_run(1)
    for seed in range(1000):
        run.seed = seed
        if roll_drop(run, node_id) is not None:
            return seed
    raise AssertionError("no seed produced a drop")


def _non_hitting_seed(node_id: str) -> int:
    run = new_run(1)
    for seed in range(1000):
        run.seed = seed
        if roll_drop(run, node_id) is None:
            return seed
    raise AssertionError("every seed produced a drop")


def test_roll_drop_deterministic() -> None:
    run = new_run(5)
    assert roll_drop(run, "n1") == roll_drop(run, "n1")


def test_roll_drop_rate_roughly_30_percent() -> None:
    run = new_run(1)
    hits = 0
    for seed in range(1000):
        run.seed = seed
        hits += roll_drop(run, "n1") is not None
    assert 0.25 <= hits / 1000 <= 0.35


def test_drop_discarded_when_full() -> None:
    run = new_run(1)
    node = MapNode(id="n1", floor=0, type=NodeType.COMBAT)
    run.nodes[node.id] = node
    run.seed = _hitting_seed(node.id)
    run.player.consumables = [CONSUMABLE_POOL[0]] * 3
    _finish_combat(run, node, "Foe", True, random.Random(1))
    assert len(run.player.consumables) == 3


def test_no_drop_on_defeat() -> None:
    run = new_run(1)
    node = MapNode(id="n1", floor=0, type=NodeType.COMBAT)
    run.nodes[node.id] = node
    run.seed = _hitting_seed(node.id)
    before = list(run.player.consumables)
    _finish_combat(run, node, "Foe", False, random.Random(1))
    assert run.player.consumables == before


def test_won_fight_adds_the_script_it_rolled() -> None:
    run = new_run(1)
    node = MapNode(id="n1", floor=0, type=NodeType.COMBAT)
    run.nodes[node.id] = node
    run.seed = _hitting_seed(node.id)
    item = roll_drop(run, node.id)
    assert item is not None
    before = list(run.player.consumables)
    _finish_combat(run, node, "Foe", True, random.Random(1))
    assert run.player.consumables == before + [item]
    assert f"Found script {item.name}." in run.history


def test_full_slots_report_the_lost_script() -> None:
    run = new_run(1)
    node = MapNode(id="n1", floor=0, type=NodeType.COMBAT)
    run.nodes[node.id] = node
    run.seed = _hitting_seed(node.id)
    item = roll_drop(run, node.id)
    assert item is not None
    run.player.consumables = [CONSUMABLE_POOL[1]] * 3
    _finish_combat(run, node, "Foe", True, random.Random(1))
    assert len(run.player.consumables) == 3
    assert f"Script {item.name} lost: no free slot." in run.history


def test_roll_drop_does_not_shift_the_run_rng() -> None:
    """The drop is rolled on its own rng: the run rng's sequence is unchanged."""
    node = MapNode(id="n1", floor=0, type=NodeType.COMBAT)
    outcomes = []
    for seed in (_hitting_seed(node.id), _non_hitting_seed(node.id)):
        run = new_run(1)
        run.nodes[node.id] = node
        run.seed = seed
        rng = random.Random(7)
        _finish_combat(run, node, "Foe", True, rng)
        outcomes.append((rng.random(), rng.randint(0, 10_000), len(run.player.consumables)))
    assert outcomes[0][:2] == outcomes[1][:2]
    assert outcomes[0][2] == 1 and outcomes[1][2] == 0
