from fastapi.testclient import TestClient

from agentic_rogue_like.api import app

client = TestClient(app)


def _play_combat(run_id: str, run: dict) -> dict:
    turns = 0
    while run["pending_combat"] is not None:
        combat = run["pending_combat"]
        empty_slot = next((i for i, c in enumerate(combat["field"]) if c is None), None)

        if combat["hand"] and empty_slot is not None:
            run = client.post(
                f"/runs/{run_id}/combat/play-card",
                json={"hand_index": combat["hand"][0]["hand_index"], "slot_index": empty_slot},
            ).json()
        else:
            run = client.post(f"/runs/{run_id}/combat/end-turn").json()

        turns += 1
        assert turns < 200, "combat did not terminate"

    return run


def _play_full_run(seed: int) -> dict:
    run = client.post("/runs", json={"seed": seed}).json()
    run_id = run["run_id"]
    steps = 0

    while run["status"] == "ongoing":
        run = client.post(f"/runs/{run_id}/resolve").json()

        if run["pending_event"] is not None:
            run = client.post(
                f"/runs/{run_id}/event-choice", json={"option_index": 0}
            ).json()

        run = _play_combat(run_id, run)

        if run["status"] != "ongoing":
            break

        next_node_id = run["available_choices"][0]["id"]
        run = client.post(f"/runs/{run_id}/choose-node", json={"node_id": next_node_id}).json()

        steps += 1
        assert steps < 100, "run did not terminate - possible infinite loop in the map"

    return run


def test_run_always_terminates_in_victory_or_defeat() -> None:
    for seed in range(20):
        run = _play_full_run(seed)
        assert run["status"] in ("victory", "defeat")


def test_resolve_twice_without_choosing_next_node_is_rejected() -> None:
    run = client.post("/runs", json={"seed": 1}).json()
    run_id = run["run_id"]

    client.post(f"/runs/{run_id}/resolve")
    response = client.post(f"/runs/{run_id}/resolve")

    assert response.status_code == 409


def test_unknown_run_id_returns_404() -> None:
    response = client.get("/runs/does-not-exist")

    assert response.status_code == 404
