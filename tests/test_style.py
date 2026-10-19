import random
from collections import Counter
from unittest.mock import patch

from fastapi.testclient import TestClient

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.api import app
from agentic_rogue_like.cards import REWARD_POOL, reward_card, starter_deck
from agentic_rogue_like.enemies import ENEMY_POOL, pick_enemy, with_affix
from agentic_rogue_like.engine import new_run, start_combat_node
from agentic_rogue_like.models import Affix, NodeType
from agentic_rogue_like.sessions import get_session
from agentic_rogue_like.style import (
    COUNTER_AFFIX,
    PlayStyle,
    agent_hint,
    answers,
    play_style,
    style_counts,
)
from agentic_rogue_like.threat import threat


def _deck_with(*names: str):
    deck = starter_deck()
    for name in names:
        deck.append(reward_card(next(c for c in REWARD_POOL if c.name == name), deck))
    return deck


def test_the_starter_deck_has_no_style() -> None:
    assert play_style(starter_deck()) is None
    assert set(style_counts(starter_deck()).values()) == {0}


def test_chosen_cards_make_the_style() -> None:
    deck = _deck_with("Daemon", "Mainframe", "Load Balancer", "Botnet")
    assert play_style(deck) is PlayStyle.PERMANENTS
    assert play_style(_deck_with("Trojan", "Worm", "Ransomware")) is PlayStyle.MALWARE


def test_too_few_or_tied_cards_are_no_style() -> None:
    assert play_style(_deck_with("Daemon", "Mainframe")) is None
    # Two attack/graveyard cards and two of something else - nothing leads.
    assert play_style(_deck_with("Daemon", "Mainframe", "Honeypot", "Sandbox")) is None


def test_answers_needs_a_counter_move_or_affix() -> None:
    rust = next(e for e in ENEMY_POOL["mid"] if e.id == "rust-monster")  # purges
    bandit = next(e for e in ENEMY_POOL["mid"] if e.id == "bandit")  # parries at 90%
    assert answers(rust, PlayStyle.PERMANENTS)
    assert not answers(bandit, PlayStyle.PERMANENTS)
    assert not answers(bandit, PlayStyle.AGGRO)  # a weak guard doesn't count
    gargoyle = next(e for e in ENEMY_POOL["elite"] if e.id == "gargoyle")  # petrify 150%
    assert answers(gargoyle, PlayStyle.AGGRO)
    assert answers(bandit.model_copy(update={"affix": Affix.THORNY}), PlayStyle.AGGRO)
    assert not answers(rust, None)


def test_the_pool_prefers_answers_but_still_mixes() -> None:
    rng = random.Random(1)
    picks = Counter(
        pick_enemy(5, 8, False, False, rng, style=PlayStyle.PERMANENTS).id for _ in range(3000)
    )
    assert picks["rust-monster"] > 2 * picks["bandit"] > 0


def test_no_style_keeps_the_old_draw() -> None:
    a = [pick_enemy(5, 8, False, False, random.Random(s)).id for s in range(30)]
    b = [pick_enemy(5, 8, False, False, random.Random(s), style=None).id for s in range(30)]
    assert a == b


def test_affixes_lean_towards_the_counter_and_keep_the_threat() -> None:
    ogre = ENEMY_POOL["elite"][0]
    rng = random.Random(3)
    affixes = Counter(with_affix(ogre, rng, PlayStyle.AGGRO).affix for _ in range(2000))
    assert affixes[COUNTER_AFFIX[PlayStyle.AGGRO]] > 1.5 * affixes[Affix.ARMORED]
    armed = with_affix(ogre, random.Random(4), PlayStyle.MALWARE)
    assert abs(threat(armed) - threat(ogre)) / threat(ogre) < 0.03


def test_answering_enemy_opens_with_a_taunt() -> None:
    run = new_run(2)
    run.artifact_offer = run.card_reward = None
    run.player.deck = _deck_with("Daemon", "Mainframe", "Load Balancer", "Botnet")
    run.current_node_id = next(
        i for i, n in run.nodes.items() if n.type is NodeType.COMBAT and n.floor >= 4
    )
    with patch("agentic_rogue_like.engine.answers", return_value=True):
        state = start_combat_node(run, random.Random(1))
    assert state.enemy.taunt.startswith("AGI:")
    assert any(line.startswith("AGI:") for line in run.history)


def test_the_agent_is_told_what_to_answer(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    seen = {}

    def _fake(**kwargs):
        seen.update(kwargs)
        raise ConnectionError("no network in tests")

    with patch.object(encounter_agent, "generate_balanced_enemy", side_effect=_fake):
        encounter_agent.enemy_for_node(
            "e", 5, 8, False, False, random.Random(1), style=PlayStyle.TURTLE
        )
    assert seen["counter_hint"] == agent_hint(PlayStyle.TURTLE)
    assert "infect" in seen["counter_hint"]


def test_api_reports_the_style() -> None:
    client = TestClient(app)
    run_id = client.post("/runs", json={"seed": 1}).json()["run_id"]
    get_session(run_id).run.player.deck = _deck_with("Trojan", "Worm", "Ransomware")

    view = client.get(f"/runs/{run_id}").json()

    assert view["play_style"] == "malware"
    assert view["style_counts"]["malware"] == 3
