import threading

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like import prefetch
from agentic_rogue_like.agent import encounter_agent, event_agent
from agentic_rogue_like.api import app
from agentic_rogue_like.engine import new_run
from agentic_rogue_like.events import EventEffect, EventOption, GameEvent
from agentic_rogue_like.models import Enemy
from agentic_rogue_like.sessions import get_session

client = TestClient(app)


def _resolve(run_id: str):
    """POST /resolve, first taking the first artifact if one is on offer and
    picking the first kit and turning the deal down."""
    run = client.get(f"/runs/{run_id}").json()
    if run["artifact_offer"] is not None:
        client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 0})
    if run["kit_offer"] is not None:
        client.post(f"/runs/{run_id}/kit", json={"kit_index": 0})
        client.post(f"/runs/{run_id}/agi-deal", json={"deal_index": None})
    return client.post(f"/runs/{run_id}/resolve")


def _prefetched_enemy(**kwargs) -> Enemy:
    return Enemy(
        id=kwargs["enemy_id"], name="Prefetched Wisp", hp=12, attack=3, attack_name="Glimmer"
    )


def _live_call_is_a_bug(*args, **kwargs):
    raise AssertionError("a room waited on a live agent call instead of the prefetch")


PREFETCHED_EVENT_TEXT = "A prefetched rift flickers open."


def _prefetched_event(setting: str) -> GameEvent:
    return GameEvent(
        description=PREFETCHED_EVENT_TEXT,
        options=[
            EventOption(
                label="Reach in",
                effects=[EventEffect(kind="gold", amount=40), EventEffect(kind="hp", amount=-5)],
            ),
            EventOption(label="Back away"),
        ],
    )


@pytest.fixture
def agent_enabled(monkeypatch):
    # Stubs on both paths: prefetch must feed every combat room, and no test
    # here may reach Groq.
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.setattr(prefetch, "generate_balanced_enemy", _prefetched_enemy)
    monkeypatch.setattr(encounter_agent, "generate_balanced_enemy", _live_call_is_a_bug)
    monkeypatch.setattr(prefetch, "generate_valid_event", _prefetched_event)
    monkeypatch.setattr(event_agent, "generate_valid_event", _live_call_is_a_bug)
    monkeypatch.setattr(prefetch, "narrate", lambda setting, situation: f"themed: {situation}")


def _walk_to_first_combat(run: dict) -> dict:
    run_id = run["run_id"]
    for _ in range(100):
        run = _resolve(run_id).json()
        if run["pending_combat"] is not None:
            return run
        if run["pending_event"] is not None:
            run = client.post(f"/runs/{run_id}/event-choice", json={"option_index": 0}).json()
        run = client.post(
            f"/runs/{run_id}/choose-node", json={"node_id": run["available_choices"][0]["id"]}
        ).json()
    raise AssertionError("no combat room reached")


def test_combat_rooms_use_the_prefetched_enemy(agent_enabled) -> None:
    run = client.post("/runs", json={"seed": 7}).json()

    run = _walk_to_first_combat(run)

    assert run["pending_combat"]["enemy_name"] == "Prefetched Wisp"


def test_non_combat_rooms_use_prefetched_narration(agent_enabled, monkeypatch) -> None:
    narrated_on: list[str] = []

    def _narrate(setting, situation):
        narrated_on.append(threading.current_thread().name)
        return f"themed: {situation}"

    monkeypatch.setattr(prefetch, "narrate", _narrate)
    run = client.post("/runs", json={"seed": 7}).json()
    run_id = run["run_id"]
    narrated_rooms = event_rooms = 0

    while run["status"] == "ongoing":
        # Rest and shop rooms get narration; event rooms an agent-written event.
        narrated_rooms += run["current_node"]["type"] in ("rest", "shop")
        run = _resolve(run_id).json()
        if run["pending_event"] is not None:
            event_rooms += 1
            assert run["pending_event"]["description"] == PREFETCHED_EVENT_TEXT
            assert run["pending_event"]["options"][0]["effects"] == "+40 gold, -5 HP"
            run = client.post(f"/runs/{run_id}/event-choice", json={"option_index": 0}).json()
        while run["pending_combat"] is not None:
            combat = run["pending_combat"]
            free = [
                i
                for i, c in enumerate(combat["field"])
                if c is None and i not in combat["locked_slots"]
            ]
            if combat["hand"] and free:
                run = client.post(
                    f"/runs/{run_id}/combat/play-card",
                    json={"hand_index": 0, "slot_index": free[0]},
                ).json()
            else:
                excess = max(0, len(combat["hand"]) - combat["max_hand_size"])
                run = client.post(
                    f"/runs/{run_id}/combat/end-turn",
                    json={"discard_indices": list(range(excess))},
                ).json()
        if run["card_reward"] is not None:
            run = client.post(f"/runs/{run_id}/card-reward", json={"card_index": None}).json()
        if run["shop"] is not None:
            run = client.post(f"/runs/{run_id}/shop/leave").json()
        if run["rest"] is not None:
            run = client.post(f"/runs/{run_id}/rest/heal").json()
        if run["status"] == "ongoing":
            next_node_id = run["available_choices"][0]["id"]
            run = client.post(f"/runs/{run_id}/choose-node", json={"node_id": next_node_id}).json()

    themed = [line for line in run["history"] if line.startswith("themed: ")]
    assert narrated_rooms and event_rooms
    assert len(themed) == narrated_rooms
    # Every narration ran in the background pool, none on a request thread.
    assert all(name.startswith("prefetch") for name in narrated_on)


def test_rooms_no_longer_reachable_are_dropped(agent_enabled) -> None:
    run = new_run(seed=7)
    cache = prefetch.Prefetch()
    cache.warm(run)

    for _ in range(3):
        run.nodes[run.current_node_id].visited = True
        run.current_node_id = run.nodes[run.current_node_id].connections[-1]
        cache.warm(run)

        reachable = {run.current_node_id, *run.nodes[run.current_node_id].connections}
        assert set(cache.enemies) <= reachable


def test_failed_prefetch_falls_back_to_the_static_pool(agent_enabled, monkeypatch) -> None:
    def _api_is_down(**kwargs) -> Enemy:
        raise ConnectionError("groq unreachable")

    monkeypatch.setattr(prefetch, "generate_balanced_enemy", _api_is_down)
    run = client.post("/runs", json={"seed": 7}).json()

    run = _walk_to_first_combat(run)

    assert run["pending_combat"]["enemy_name"] != "Prefetched Wisp"


def test_nothing_is_prefetched_when_the_agent_is_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_ENABLED", raising=False)

    run = client.post("/runs", json={"seed": 7}).json()

    session = get_session(run["run_id"])
    assert session.prefetch.enemies == {}
    assert session.prefetch.flavors == {}
