from fastapi.testclient import TestClient

from agentic_rogue_like.api import app

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


def _play_combat(run_id: str, run: dict) -> dict:
    turns = 0
    while run["pending_combat"] is not None:
        combat = run["pending_combat"]
        empty_slot = next(
            (
                i
                for i, c in enumerate(combat["field"])
                if c is None and i not in combat["locked_slots"]
            ),
            None,
        )
        # never past the Vibe-Coder's context window - always false for Dr. Chronos
        card = next((c for c in combat["hand"] if not c["overflows"]), None)

        if card is not None and empty_slot is not None:
            run = client.post(
                f"/runs/{run_id}/combat/play-card",
                json={"hand_index": card["hand_index"], "slot_index": empty_slot},
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


def _play_full_run(seed: int, character: str = "chronos") -> dict:
    run = client.post("/runs", json={"seed": seed, "character": character}).json()
    run_id = run["run_id"]
    steps = 0

    while run["status"] == "ongoing":
        run = _resolve(run_id).json()

        if run["pending_event"] is not None:
            run = client.post(f"/runs/{run_id}/event-choice", json={"option_index": 0}).json()

        run = _play_combat(run_id, run)

        if run["card_reward"] is not None:
            run = client.post(f"/runs/{run_id}/card-reward", json={"card_index": 0}).json()

        if run["shop"] is not None:
            run = client.post(f"/runs/{run_id}/shop/leave").json()

        if run["rest"] is not None:
            # Alternate the three choices, so full runs exercise all of them.
            if steps % 3 == 0 and run["rest"]["upgrades"]:
                index = run["rest"]["upgrades"][0]["deck_index"]
                run = client.post(f"/runs/{run_id}/rest/upgrade", json={"index": index}).json()
            elif steps % 3 == 1 and run["rest"]["can_remove"]:
                run = client.post(f"/runs/{run_id}/rest/remove", json={"index": 0}).json()
            else:
                run = client.post(f"/runs/{run_id}/rest/heal").json()

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

    _resolve(run_id)
    response = _resolve(run_id)

    assert response.status_code == 409


def test_unknown_run_id_returns_404() -> None:
    response = client.get("/runs/does-not-exist")

    assert response.status_code == 404


def _won_fight(seed: int) -> tuple[str, dict]:
    """Seeds where the first fight is won, so a card reward is pending."""
    run = client.post("/runs", json={"seed": seed}).json()
    run_id = run["run_id"]
    run = _play_combat(run_id, _resolve(run_id).json())
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
    run = _resolve(run_id).json()

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


def test_combat_view_names_the_telegraphed_move() -> None:
    from agentic_rogue_like.combat import EnemyIntentType
    from agentic_rogue_like.models import EnemyMove, MoveKind
    from agentic_rogue_like.sessions import get_session

    run_id = client.post("/runs", json={"seed": 3}).json()["run_id"]
    run = _resolve(run_id).json()
    # The static pool's moves are named.
    assert run["pending_combat"]["enemy_intent_name"] is not None

    combat = get_session(run_id).combat
    combat.enemy = combat.enemy.model_copy(
        update={"moves": [EnemyMove(kind=MoveKind.BARRAGE, name="Bristle Volley", hits=2)]}
    )
    combat.enemy_move, combat.enemy_intent = 0, EnemyIntentType.BARRAGE

    view = client.get(f"/runs/{run_id}").json()["pending_combat"]
    assert view["enemy_intent_name"] == "Bristle Volley"
    assert view["enemy_intent_hits"] == 2


def test_characters_are_listed() -> None:
    characters = client.get("/characters").json()

    assert [c["id"] for c in characters] == ["chronos", "vibe_coder"]
    assert characters[0]["token_limit"] is None
    assert characters[1]["token_limit"] > 0


def test_unknown_character_is_rejected() -> None:
    response = client.post("/runs", json={"seed": 1, "character": "wizard"})

    assert response.status_code == 422


def test_vibe_coder_fight_shows_and_spends_the_context_window() -> None:
    run = client.post("/runs", json={"seed": 3, "character": "vibe_coder"}).json()
    run_id = run["run_id"]
    assert run["player"]["character"] == "vibe_coder"

    combat = _resolve(run_id).json()["pending_combat"]
    assert combat["token_limit"] > 0
    assert combat["tokens_used"] == 0
    assert all("token_cost" in c and not c["overflows"] for c in combat["hand"])

    # a basic card - a kit card may discard as it is played
    card = next(c for c in combat["hand"] if c["token_cost"] == 1 and c["rarity"] == "starter")
    hand_size = len(combat["hand"])
    run = client.post(
        f"/runs/{run_id}/combat/play-card",
        json={"hand_index": card["hand_index"], "slot_index": 0},
    ).json()

    combat = run["pending_combat"]
    assert combat["tokens_used"] == 1
    assert len(combat["hand"]) == hand_size  # drew a card for the one played


def test_chronos_fight_has_no_context_window() -> None:
    run_id = client.post("/runs", json={"seed": 3}).json()["run_id"]

    combat = _resolve(run_id).json()["pending_combat"]

    assert combat["token_limit"] is None
    assert combat["tokens_used"] == 0


def test_vibe_coder_run_always_terminates() -> None:
    for seed in range(5):
        run = _play_full_run(seed, character="vibe_coder")
        assert run["status"] in ("victory", "defeat")


def test_health_answers_for_the_keep_alive() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_client_errors_are_logged_and_capped(caplog) -> None:
    import agentic_rogue_like.api as api

    api._client_error_times.clear()
    with caplog.at_level("WARNING", logger="agentic_rogue_like.client"):
        response = client.post(
            "/client-errors",
            json={"message": "boom", "stack": "at CombatPanel", "run_id": "r1", "where": "render"},
        )
        assert response.status_code == 204
        assert "boom" in caplog.text and "at CombatPanel" in caplog.text

        for _ in range(api.CLIENT_ERRORS_PER_MINUTE + 5):
            client.post("/client-errors", json={"message": "again"})
    assert caplog.text.count("again") == api.CLIENT_ERRORS_PER_MINUTE - 1
    api._client_error_times.clear()
