"""The act pack in the game: prefetch starts one call per act, enemy_for_node
draws each regular and elite room's enemy out of it."""

from __future__ import annotations

import random
from concurrent.futures import Future

import pytest

from agentic_rogue_like import prefetch
from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.act_pack import ActPack
from agentic_rogue_like.enemies import pick_enemy
from agentic_rogue_like.engine import new_run
from agentic_rogue_like.map_gen import NUM_FLOORS
from agentic_rogue_like.models import Enemy, EnemyMove, MoveKind
from agentic_rogue_like.style import PlayStyle, answers

_PLAIN = [
    EnemyMove(kind=MoveKind.ATTACK, name="Data Spike", weight=3, power=100),
    EnemyMove(kind=MoveKind.DEFEND, name="Firewall", weight=2, power=100),
]
# Malware ignores block: this one answers a turtle deck.
_INFECTING = [
    EnemyMove(kind=MoveKind.ATTACK, name="Data Spike", weight=3, power=100),
    EnemyMove(kind=MoveKind.INFECT, name="Worm Bite", weight=2, power=50, stacks=3),
]


def _enemy(name: str, moves: list[EnemyMove] = _PLAIN) -> Enemy:
    return Enemy(id="packed", name=name, hp=40, attack=9, attack_name="Data Spike", moves=moves)


def _pack(**tiers: list[Enemy]) -> ActPack:
    return ActPack(act=1, setting="cyberpunk", **tiers)


def _live_call_is_a_bug(*args, **kwargs):
    raise AssertionError("a regular room made a model call of its own")


@pytest.fixture
def agent_enabled(monkeypatch):
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.setattr(encounter_agent, "generate_balanced_enemy", _live_call_is_a_bug)
    monkeypatch.setattr(prefetch, "generate_valid_event", _live_call_is_a_bug)
    monkeypatch.setattr(prefetch, "narrate", lambda setting, situation: None)


def _draw(act_pack, *, floor: int = 0, elite: bool = False, style=None, seed="room", rng=None):
    return encounter_agent.enemy_for_node(
        enemy_id="agent-1234",
        floor=floor,
        num_floors=NUM_FLOORS,
        elite=elite,
        boss=False,
        rng=rng if rng is not None else random.Random(0),
        style=style,
        act_pack=act_pack,
        pack_rng=random.Random(seed),
    )


def test_one_pack_call_feeds_several_rooms(agent_enabled, monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def _generate(setting: str, act: int) -> ActPack:
        calls.append((setting, act))
        return _pack(
            early=[_enemy(f"Early {i}") for i in range(4)],
            elite=[_enemy(f"Elite {i}") for i in range(3)],
        )

    monkeypatch.setattr(prefetch, "generate_act_pack", _generate)
    monkeypatch.setattr(prefetch, "generate_balanced_enemy", _live_call_is_a_bug)
    run = new_run(seed=7)
    cache = prefetch.Prefetch()

    # The player walks on: every warm() of the act reuses the one pack.
    for _ in range(3):
        cache.warm(run)
        run.nodes[run.current_node_id].visited = True
        run.current_node_id = run.nodes[run.current_node_id].connections[0]
    cache.act_packs[1].result(timeout=5)

    getter = cache.act_pack(1)
    early = [_draw(getter, seed=f"room-{i}").name for i in range(4)]
    elites = [_draw(getter, elite=True, seed=f"elite-{i}").name for i in range(2)]

    assert calls == [(run.setting, 1)]
    # Each room took its own enemy out of the pack, with the room's id swapped in.
    assert sorted(early) == [f"Early {i}" for i in range(4)]
    assert len(set(elites)) == 2 and all(name.startswith("Elite ") for name in elites)
    assert getter().early == [] and len(getter().elite) == 1
    # Regular rooms are no longer prefetched one by one.
    assert all(run.nodes[node_id].type.value == "boss" for node_id in cache.enemies)


def test_a_new_act_starts_its_own_pack(agent_enabled, monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(prefetch, "generate_act_pack", lambda s, act: calls.append(act) or _pack())
    monkeypatch.setattr(prefetch, "generate_balanced_enemy", _live_call_is_a_bug)
    run = new_run(seed=7)
    cache = prefetch.Prefetch()
    cache.warm(run)
    cache.warm(run)
    cache.act_packs[1].result(timeout=5)

    run.act = 2
    cache.warm(run)
    cache.act_packs[2].result(timeout=5)

    assert calls == [1, 2]
    assert list(cache.act_packs) == [2]


def test_a_style_prefers_the_enemies_answering_it(agent_enabled) -> None:
    infecting, plain = _enemy("Worm", _INFECTING), _enemy("Plain")
    assert answers(infecting, PlayStyle.TURTLE) and not answers(plain, PlayStyle.TURTLE)

    def share_of_worms(style: PlayStyle | None) -> float:
        draws = [
            _draw(lambda: _pack(early=[plain, infecting]), style=style, seed=f"room-{i}").name
            for i in range(600)
        ]
        return draws.count("Worm") / len(draws)

    # COUNTER_WEIGHT 3 against 1: three in four rooms, against one in two.
    assert share_of_worms(PlayStyle.TURTLE) == pytest.approx(0.75, abs=0.06)
    assert share_of_worms(None) == pytest.approx(0.5, abs=0.06)


def test_the_pack_draw_leaves_the_run_rng_alone(agent_enabled) -> None:
    rng = random.Random(42)
    untouched = random.Random(42)

    first = _draw(lambda: _pack(early=[_enemy("A"), _enemy("B"), _enemy("C")]), rng=rng, seed="x")
    again = _draw(lambda: _pack(early=[_enemy("A"), _enemy("B"), _enemy("C")]), seed="x")

    assert rng.random() == untouched.random()
    # Same room seed, same draw.
    assert first.name == again.name


@pytest.mark.parametrize(
    "getter",
    [
        pytest.param(lambda: (_ for _ in ()).throw(ConnectionError("groq down")), id="failed"),
        pytest.param(lambda: None, id="not-done"),
        pytest.param(lambda: _pack(mid=[_enemy("Mid only")]), id="tier-empty"),
    ],
)
def test_no_pack_enemy_falls_back_to_the_static_pool(agent_enabled, getter) -> None:
    enemy = _draw(getter, rng=random.Random(5))

    expected = pick_enemy(
        floor=0, num_floors=NUM_FLOORS, elite=False, boss=False, rng=random.Random(5)
    )
    assert enemy == expected


def test_a_failed_pack_call_falls_back_through_prefetch(agent_enabled, monkeypatch) -> None:
    def _api_is_down(setting: str, act: int) -> ActPack:
        raise ConnectionError("groq unreachable")

    monkeypatch.setattr(prefetch, "generate_act_pack", _api_is_down)
    monkeypatch.setattr(prefetch, "generate_balanced_enemy", _live_call_is_a_bug)
    cache = prefetch.Prefetch()
    cache.warm(new_run(seed=7))
    assert cache.act_packs[1].exception(timeout=5) is not None

    enemy = _draw(cache.act_pack(1), rng=random.Random(5))

    assert enemy == pick_enemy(
        floor=0, num_floors=NUM_FLOORS, elite=False, boss=False, rng=random.Random(5)
    )


def test_a_pack_still_running_is_not_waited_for(agent_enabled) -> None:
    cache = prefetch.Prefetch()
    cache.act_packs[1] = Future()  # never finishes

    assert cache.act_pack(1)() is None
    assert cache.act_pack(2) is None
