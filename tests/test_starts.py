import pytest

from agentic_rogue_like.engine import choose_artifact, choose_deal, choose_kit, new_run
from agentic_rogue_like.models import Character, DealKind, Rarity


def _at_kit(seed: int = 3, **kwargs):
    run = new_run(seed, **kwargs)
    choose_artifact(run, 0)
    return run


def test_a_run_opens_with_three_kits_instead_of_a_card_pick() -> None:
    run = new_run(3)

    assert run.card_reward is None
    assert run.kit_offer is not None and len(run.kit_offer) == 3
    assert new_run(3).kit_offer == run.kit_offer  # seeded


def test_the_artifact_comes_before_the_kit() -> None:
    run = new_run(3)
    with pytest.raises(ValueError, match="artifact first"):
        choose_kit(run, 0)


def test_a_kit_swaps_a_basic_attack_and_two_basic_blocks_for_its_cards() -> None:
    run = _at_kit()
    kit = run.kit_offer[0]
    before = [c.name for c in run.player.deck]

    choose_kit(run, 0)

    after = [c.name for c in run.player.deck]
    assert len(after) == len(before) - 1
    assert after.count("Exploit") == before.count("Exploit") - 1
    assert after.count("Firewall") == before.count("Firewall") - 2
    assert all(c.name in after for c in kit.cards)
    assert run.kit_offer is None and run.agi_deals is not None


def test_a_kit_keeps_the_starter_decks_strategy_cards() -> None:
    # It swaps plain basics only, so every strategy the starter deck shows
    # (Ping, Undo, Garbage Collect, ...) survives it - and there are basics enough.
    for character in Character:
        for program_mode in (False, True):
            run = _at_kit(character=character, program_mode=program_mode)
            before = list(run.player.deck)
            kit = run.kit_offer[0]

            choose_kit(run, 0)

            gone = [c for c in before if c not in run.player.deck]
            assert len(gone) == len(before) + len(kit.cards) - len(run.player.deck)
            assert {c.name for c in gone} <= {"Exploit", "Firewall", "Prompt", "Make It Safe"}
            assert len(gone) == (3 if character is Character.CHRONOS else 2)


def test_kits_only_come_from_the_runs_own_pool() -> None:
    names = {k.id for seed in range(40) for k in new_run(seed).kit_offer}
    assert {"move_fast", "rubber_duck", "control_flow", "pipeline"}.isdisjoint(names)

    vibe = {
        k.id
        for seed in range(40)
        for k in new_run(seed, character=Character.VIBE_CODER, program_mode=True).kit_offer
    }
    assert {"move_fast", "pipeline"} & vibe


def test_turning_the_deal_down_changes_nothing() -> None:
    run = _at_kit()
    choose_kit(run, 0)
    deck = list(run.player.deck)

    choose_deal(run, None)

    assert run.player.deck == deck and run.agi_deals is None


def _take(kind: DealKind):
    """A run right after taking the first deal of `kind` found across seeds."""
    for seed in range(60):
        run = _at_kit(seed)
        choose_kit(run, 0)
        kinds = [d.kind for d in run.agi_deals]
        if kind in kinds:
            before = run.player.model_copy(deep=True)
            deal = run.agi_deals[kinds.index(kind)]
            choose_deal(run, kinds.index(kind))
            return before, run.player, deal
    raise AssertionError(f"no {kind} deal in 60 seeds")


def test_strip_removes_a_basic_attack_and_block() -> None:
    before, after, deal = _take(DealKind.STRIP)
    assert len(after.deck) == len(before.deck) - 2
    assert not {c.id for c in after.deck} & set(deal.remove)


def test_mutate_turns_two_basics_into_commons() -> None:
    before, after, deal = _take(DealKind.MUTATE)
    assert len(after.deck) == len(before.deck)
    assert sum(c.rarity is Rarity.COMMON for c in after.deck) >= 2


def test_forbidden_patch_costs_max_hp() -> None:
    before, after, deal = _take(DealKind.FORBIDDEN)
    assert after.max_hp == before.max_hp - 5 and after.hp <= after.max_hp
    assert after.deck[-1].rarity is Rarity.RARE


def test_trojan_gift_brings_an_artifact_and_a_glitch() -> None:
    before, after, deal = _take(DealKind.TROJAN)
    assert len(after.artifacts) == len(before.artifacts) + 1
    glitch = after.deck[-1]
    assert glitch.name == "Glitch" and glitch.rarity is Rarity.STARTER


def test_hotfix_upgrades_two_basics() -> None:
    before, after, deal = _take(DealKind.HOTFIX)
    assert sum(c.upgraded for c in after.deck) == sum(c.upgraded for c in before.deck) + 2


def test_bribe_pays_credits() -> None:
    before, after, deal = _take(DealKind.BRIBE)
    assert after.gold == before.gold + 90


def test_api_walks_through_the_start_of_a_run() -> None:
    from fastapi.testclient import TestClient

    from agentic_rogue_like.api import app

    client = TestClient(app)
    run = client.post("/runs", json={"seed": 4}).json()
    run_id = run["run_id"]
    assert len(run["kit_offer"]) == 3 and run["agi_deals"] is None
    assert client.post(f"/runs/{run_id}/kit", json={"kit_index": 0}).status_code == 400

    client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 0})
    assert client.post(f"/runs/{run_id}/resolve").status_code == 409
    run = client.post(f"/runs/{run_id}/kit", json={"kit_index": 1}).json()
    assert run["kit_offer"] is None and len(run["agi_deals"]) == 3
    assert client.post(f"/runs/{run_id}/agi-deal", json={"deal_index": 7}).status_code == 400

    run = client.post(f"/runs/{run_id}/agi-deal", json={"deal_index": 0}).json()
    assert run["agi_deals"] is None
    assert client.post(f"/runs/{run_id}/resolve").status_code == 200


def test_a_vibe_coder_kit_swaps_one_basic_attack_and_one_basic_block() -> None:
    run = _at_kit(character=Character.VIBE_CODER)
    size = len(run.player.deck)
    choose_kit(run, 0)
    assert len(run.player.deck) == size


def test_api_deals_name_their_cards_for_hover_previews() -> None:
    from fastapi.testclient import TestClient

    from agentic_rogue_like.api import app

    client = TestClient(app)
    for seed in range(30):
        run = client.post("/runs", json={"seed": seed}).json()
        run_id = run["run_id"]
        client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 0})
        run = client.post(f"/runs/{run_id}/kit", json={"kit_index": 0}).json()
        for deal in run["agi_deals"]:
            for card in deal["mentions"]:
                assert card["name"].rstrip("+") in deal["description"]
            if deal["kind"] == "hotfix":
                assert all(c["upgraded"] for c in deal["mentions"])
