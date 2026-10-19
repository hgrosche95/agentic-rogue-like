import random

import pytest
from fastapi.testclient import TestClient

from agentic_rogue_like.api import app
from agentic_rogue_like.artifacts import ARTIFACT_POOL
from agentic_rogue_like.cards import CARD_UPGRADES, can_upgrade, starter_deck, upgrade_card
from agentic_rogue_like.combat import action_preview, player_armor, start_combat
from agentic_rogue_like.engine import (
    REST_HEAL,
    new_run,
    open_rest,
    resolve_node,
    rest_heal,
    rest_remove,
    rest_upgrade,
)
from agentic_rogue_like.models import CardType, Enemy, NodeType
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.shop import MIN_DECK_SIZE


def _at_rest(**player):
    run = new_run(1)
    run.artifact_offer = run.card_reward = None
    rest_id = next(i for i, n in run.nodes.items() if n.type is NodeType.REST)
    run.current_node_id = rest_id
    for key, value in player.items():
        setattr(run.player, key, value)
    open_rest(run, narrator=lambda setting, situation: None)
    return run


def _deck_index(run, name: str) -> int:
    return next(i for i, c in enumerate(run.player.deck) if c.name == name)


# --------------------------------------------------------------- upgrades


def test_upgrade_improves_the_card_and_marks_it() -> None:
    exploit = next(c for c in starter_deck() if c.name == "Exploit")
    better = upgrade_card(exploit)

    assert (better.name, better.value, better.id) == ("Exploit+", 8, exploit.id)
    assert better.upgraded and not can_upgrade(better)
    assert "8" in better.description
    with pytest.raises(ValueError):
        upgrade_card(better)


def test_some_cards_have_no_upgrade() -> None:
    prefetch = next(c for c in starter_deck() if c.name == "Prefetch")
    assert not can_upgrade(prefetch)
    assert "Prefetch" not in CARD_UPGRADES


def test_upgraded_overclock_and_encryption_are_stronger_in_combat() -> None:
    deck = starter_deck()
    overclock = next(c for c in deck if c.type is CardType.AMPLIFIER)
    encryption = next(c for c in deck if c.type is CardType.ARMOR)
    exploit = next(c for c in deck if c.name == "Exploit")
    run = new_run(1)
    enemy = Enemy(id="e", name="E", hp=99, attack=5, attack_name="Hit")

    for amp, armor_card, damage, armor in (
        (overclock, encryption, round((5 + 2) * 1.25), 1),
        (upgrade_card(overclock), upgrade_card(encryption), round((5 + 2) * 1.4), 2),
    ):
        state, _ = start_combat(deck, enemy, random.Random(1))
        state.field[0], state.field[4] = amp, armor_card
        assert action_preview(state, exploit, run.player, 1) == damage
        assert player_armor(state) == armor


# --------------------------------------------------------------- the rest site


def test_rest_heals_by_default_through_resolve_node() -> None:
    run = new_run(1)
    run.artifact_offer = run.card_reward = None
    run.current_node_id = next(i for i, n in run.nodes.items() if n.type is NodeType.REST)
    run.player.hp = 10

    resolve_node(run, random.Random(1), narrator=lambda s, t: None)

    assert run.player.hp == 10 + REST_HEAL
    assert run.rest is None


def test_heal_amount_includes_artifacts() -> None:
    sleep_mode = next(a for a in ARTIFACT_POOL if a.rest_heal)
    run = new_run(1)
    run.artifact_offer = run.card_reward = None
    run.player.artifacts.append(sleep_mode)
    run.current_node_id = next(i for i, n in run.nodes.items() if n.type is NodeType.REST)
    open_rest(run, narrator=lambda s, t: None)

    assert run.rest.heal_amount == REST_HEAL + sleep_mode.rest_heal


def test_heal_closes_the_rest_site() -> None:
    run = _at_rest(hp=10)
    rest_heal(run)
    assert run.player.hp == 10 + REST_HEAL and run.rest is None


def test_upgrade_replaces_the_card_in_the_deck() -> None:
    run = _at_rest()
    index = _deck_index(run, "Firewall")

    rest_upgrade(run, index)

    assert run.player.deck[index].name == "Firewall+"
    assert run.rest is None


def test_upgrading_a_card_that_cant_be_upgraded_keeps_the_rest_site_open() -> None:
    run = _at_rest()
    with pytest.raises(ValueError):
        rest_upgrade(run, _deck_index(run, "Prefetch"))
    assert run.rest is not None


def test_remove_is_free_and_leaves_the_market_price_alone() -> None:
    run = _at_rest(gold=0)
    size = len(run.player.deck)

    rest_remove(run, 0)

    assert len(run.player.deck) == size - 1
    assert run.cards_removed == 0 and run.player.gold == 0


def test_remove_respects_the_minimum_deck_size() -> None:
    run = _at_rest()
    run.player.deck = run.player.deck[:MIN_DECK_SIZE]
    with pytest.raises(ValueError):
        rest_remove(run, 0)


def test_no_action_without_an_open_rest_site() -> None:
    run = new_run(1)
    for action in (rest_heal, lambda r: rest_upgrade(r, 0), lambda r: rest_remove(r, 0)):
        with pytest.raises(ValueError):
            action(run)


# --------------------------------------------------------------- API

client = TestClient(app)


def _api_run_at_rest() -> str:
    run_id = client.post("/runs", json={"seed": 1}).json()["run_id"]
    run = get_session(run_id).run
    run.artifact_offer = run.card_reward = None
    run.current_node_id = next(i for i, n in run.nodes.items() if n.type is NodeType.REST)
    return run_id


def test_api_rest_offers_heal_upgrades_and_removal() -> None:
    run_id = _api_run_at_rest()
    rest = client.post(f"/runs/{run_id}/resolve").json()["rest"]

    assert rest["heal_amount"] == REST_HEAL
    assert rest["can_remove"]
    names = {u["card"]["name"]: u["upgraded"] for u in rest["upgrades"]}
    assert "Prefetch" not in names
    assert names["Exploit"]["name"] == "Exploit+" and names["Exploit"]["value"] == 8


def test_api_rest_blocks_moving_on_until_chosen() -> None:
    run_id = _api_run_at_rest()
    run = client.post(f"/runs/{run_id}/resolve").json()
    assert not run["node_resolved"]
    blocked = client.post(
        f"/runs/{run_id}/choose-node", json={"node_id": run["current_node"]["connections"][0]}
    )
    assert blocked.status_code == 409

    index = run["rest"]["upgrades"][0]["deck_index"]
    run = client.post(f"/runs/{run_id}/rest/upgrade", json={"index": index}).json()

    assert run["rest"] is None and run["node_resolved"]
    assert run["player"]["deck"][index]["upgraded"]
    assert client.post(f"/runs/{run_id}/rest/heal").status_code == 409


def test_api_rejects_a_bad_rest_choice_and_keeps_the_site_open() -> None:
    run_id = _api_run_at_rest()
    client.post(f"/runs/{run_id}/resolve")

    response = client.post(f"/runs/{run_id}/rest/upgrade", json={"index": 999})

    assert response.status_code == 400
    assert client.get(f"/runs/{run_id}").json()["rest"] is not None


def test_cli_rest_prompt_upgrades_the_chosen_card(monkeypatch, capsys) -> None:
    from agentic_rogue_like import cli

    run = _at_rest()
    answers = iter(["2", "1"])  # "Upgrade a card", then the first upgradable one
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    action = cli._choose_rest(run)

    first = next(i for i, c in enumerate(run.player.deck) if can_upgrade(c))
    assert action == ("upgrade", first)
    assert "->" in capsys.readouterr().out  # shows what the upgrade does
