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
            excess = max(0, len(combat["hand"]) - combat["max_hand_size"])
            run = client.post(
                f"/runs/{run_id}/combat/end-turn",
                json={"discard_indices": list(range(excess))},
            ).json()

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

        if run["card_reward"] is not None:
            run = client.post(f"/runs/{run_id}/card-reward", json={"card_index": 0}).json()

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


def test_custom_setting_is_accepted() -> None:
    response = client.post("/runs", json={"seed": 1, "setting": "underwater steampunk city"})

    assert response.status_code == 200
    assert response.json()["setting"] == "underwater steampunk city"


def test_empty_custom_setting_is_rejected() -> None:
    response = client.post("/runs", json={"seed": 1, "setting": "   "})

    assert response.status_code == 422


def test_overly_long_custom_setting_is_rejected() -> None:
    response = client.post("/runs", json={"seed": 1, "setting": "x" * 41})

    assert response.status_code == 422


def test_resolve_twice_without_choosing_next_node_is_rejected() -> None:
    run = client.post("/runs", json={"seed": 1}).json()
    run_id = run["run_id"]

    client.post(f"/runs/{run_id}/resolve")
    response = client.post(f"/runs/{run_id}/resolve")

    assert response.status_code == 409


def test_unknown_run_id_returns_404() -> None:
    response = client.get("/runs/does-not-exist")

    assert response.status_code == 404


def _won_fight(seed: int) -> tuple[str, dict]:
    """Seeds where the first fight is won, so a card reward is pending."""
    run = client.post("/runs", json={"seed": seed}).json()
    run_id = run["run_id"]
    run = _play_combat(run_id, client.post(f"/runs/{run_id}/resolve").json())
    return run_id, run


def test_card_reward_blocks_moving_on_until_picked() -> None:
    run_id, run = _won_fight(3)
    assert run["status"] == "ongoing"
    assert run["card_reward"] is not None and len(run["card_reward"]) == 3
    assert not run["node_resolved"]

    next_id = run["current_node"]["connections"][0]
    blocked = client.post(f"/runs/{run_id}/choose-node", json={"node_id": next_id})
    assert blocked.status_code == 409

    deck_size = len(run["player"]["deck"])
    picked = run["card_reward"][1]
    run = client.post(f"/runs/{run_id}/card-reward", json={"card_index": 1}).json()
    assert run["card_reward"] is None
    assert run["node_resolved"]
    assert len(run["player"]["deck"]) == deck_size + 1
    assert run["player"]["deck"][-1]["name"] == picked["name"]
    ids = [c["id"] for c in run["player"]["deck"]]
    assert len(ids) == len(set(ids))


def test_card_reward_can_be_skipped() -> None:
    run_id, run = _won_fight(3)
    deck_size = len(run["player"]["deck"])
    run = client.post(f"/runs/{run_id}/card-reward", json={"card_index": None}).json()
    assert run["card_reward"] is None
    assert len(run["player"]["deck"]) == deck_size
    again = client.post(f"/runs/{run_id}/card-reward", json={"card_index": 0})
    assert again.status_code == 409


def test_card_reward_rejects_bad_index() -> None:
    run_id, _ = _won_fight(3)
    response = client.post(f"/runs/{run_id}/card-reward", json={"card_index": 7})
    assert response.status_code == 400


def test_end_turn_requires_discarding_down_to_the_hand_limit() -> None:
    run_id = client.post("/runs", json={"seed": 3}).json()["run_id"]
    run = client.post(f"/runs/{run_id}/resolve").json()

    # Holding every card grows the hand past the limit after one turn.
    while len(run["pending_combat"]["hand"]) <= run["pending_combat"]["max_hand_size"]:
        run = client.post(f"/runs/{run_id}/combat/end-turn").json()
        assert run["pending_combat"] is not None, "fight ended before the hand filled up"

    combat = run["pending_combat"]
    excess = len(combat["hand"]) - combat["max_hand_size"]
    assert client.post(f"/runs/{run_id}/combat/end-turn").status_code == 400

    run = client.post(
        f"/runs/{run_id}/combat/end-turn", json={"discard_indices": list(range(excess))}
    ).json()
    assert any("you discard" in line for line in run["history"][-3:])
