import random

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like.api import app
from agentic_rogue_like.engine import new_run, open_shop, resolve_node
from agentic_rogue_like.models import MapNode, NodeType
from agentic_rogue_like.shop import (
    SHOP_ARTIFACTS,
    SHOP_CARDS,
    buy_artifact,
    buy_card,
    leave_shop,
    roll_shop,
)


def _at_shop(seed: int = 7, gold: int = 500):
    """A run standing in a shop room (the start node, retyped - no narrator call)."""
    run = new_run(seed)
    run.artifact_offer = None
    run.nodes[run.current_node_id] = MapNode(id=run.current_node_id, floor=0, type=NodeType.SHOP)
    run.player.gold = gold
    open_shop(run, narrator=lambda setting, situation: None)
    return run


def test_shop_offers_four_distinct_cards_and_two_new_artifacts() -> None:
    run = _at_shop()
    shop = run.shop
    assert shop is not None
    assert len(shop.cards) == SHOP_CARDS == 4
    assert len(shop.artifacts) == SHOP_ARTIFACTS == 2
    assert len({item.card.id for item in shop.cards}) == 4
    assert len({item.artifact.id for item in shop.artifacts}) == 2
    assert all(item.price > 0 and not item.sold for item in [*shop.cards, *shop.artifacts])


def test_shop_stock_is_random_but_fixed_per_run_and_room() -> None:
    stocks = {tuple(item.card.id for item in roll_shop(_at_shop(seed)).cards) for seed in range(12)}
    assert len(stocks) > 1
    assert roll_shop(_at_shop(3)) == roll_shop(_at_shop(3))


def test_shop_never_offers_an_owned_artifact() -> None:
    run = _at_shop()
    owned = run.shop.artifacts[0].artifact
    run.player.artifacts.append(owned)
    assert all(item.artifact.id != owned.id for item in roll_shop(run).artifacts)


def test_buying_a_card_costs_gold_and_adds_a_fresh_copy() -> None:
    run = _at_shop(gold=500)
    item = run.shop.cards[1]
    deck = len(run.player.deck)
    buy_card(run, 1)
    assert run.player.gold == 500 - item.price
    assert len(run.player.deck) == deck + 1
    assert run.player.deck[-1].name == item.card.name
    assert item.sold
    ids = [c.id for c in run.player.deck]
    assert len(ids) == len(set(ids))
    with pytest.raises(ValueError, match="already sold"):
        buy_card(run, 1)


def test_buying_an_artifact_installs_it() -> None:
    run = _at_shop(gold=500)
    item = run.shop.artifacts[0]
    buy_artifact(run, 0)
    assert run.player.artifacts[-1].id == item.artifact.id
    assert run.player.gold == 500 - item.price


def test_cannot_buy_without_enough_gold() -> None:
    run = _at_shop(gold=0)
    with pytest.raises(ValueError, match="not enough gold"):
        buy_card(run, 0)
    with pytest.raises(ValueError, match="not enough gold"):
        buy_artifact(run, 0)
    assert run.player.gold == 0
    assert not any(item.sold for item in run.shop.cards)


def test_leaving_closes_the_shop() -> None:
    run = _at_shop()
    leave_shop(run)
    assert run.shop is None
    with pytest.raises(ValueError, match="no shop open"):
        buy_card(run, 0)


def test_resolve_node_opens_and_closes_the_shop_and_can_buy() -> None:
    run = new_run(5)
    run.artifact_offer = None
    run.nodes[run.current_node_id] = MapNode(id=run.current_node_id, floor=0, type=NodeType.SHOP)
    run.player.gold = 200
    seen = []

    def browse(r):
        seen.append(len(r.shop.cards))
        buy_card(r, 0)

    resolve_node(run, random.Random(5), narrator=lambda s, t: None, browse_shop=browse)
    assert seen == [4]
    assert run.shop is None
    assert run.player.gold < 200


client = TestClient(app)


def _api_run_at_shop() -> tuple[str, dict]:
    run = client.post("/runs", json={"seed": 1}).json()
    run_id = run["run_id"]
    if run["artifact_offer"] is not None:
        client.post(f"/runs/{run_id}/artifact", json={"artifact_index": 0})
    return run_id, client.post(f"/runs/{run_id}/resolve").json()


def test_api_shop_flow(monkeypatch) -> None:
    import agentic_rogue_like.api as api

    monkeypatch.setattr(api, "new_run", _patched_new_run(api.new_run))
    run_id, run = _api_run_at_shop()
    assert run["shop"] is not None
    assert len(run["shop"]["cards"]) == 4 and len(run["shop"]["artifacts"]) == 2
    assert not run["node_resolved"]

    next_id = run["current_node"]["connections"][0]
    assert client.post(f"/runs/{run_id}/choose-node", json={"node_id": next_id}).status_code == 409

    gold = run["player"]["gold"]
    price = run["shop"]["cards"][0]["price"]
    run = client.post(f"/runs/{run_id}/shop/buy-card", json={"index": 0}).json()
    assert run["player"]["gold"] == gold - price
    assert run["shop"]["cards"][0]["sold"]
    again = client.post(f"/runs/{run_id}/shop/buy-card", json={"index": 0})
    assert again.status_code == 400

    run = client.post(f"/runs/{run_id}/shop/leave").json()
    assert run["shop"] is None and run["node_resolved"]
    assert client.post(f"/runs/{run_id}/shop/leave").status_code == 409


def _patched_new_run(original):
    """Every API run starts in a shop room with 300 gold."""

    def new_run(seed, setting="dungeon"):
        run = original(seed, setting=setting)
        node = run.nodes[run.current_node_id]
        run.nodes[node.id] = node.model_copy(update={"type": NodeType.SHOP})
        run.player.gold = 300
        return run

    return new_run
