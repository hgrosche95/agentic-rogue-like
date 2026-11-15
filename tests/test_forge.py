import random
from unittest.mock import patch

import pytest

from agentic_rogue_like.agent import card_agent
from agentic_rogue_like.cards import PROGRAM_REWARD_POOL, REWARD_POOL
from agentic_rogue_like.engine import choose_deal, new_run, offer_forged_card
from agentic_rogue_like.forge import (
    FALLBACK_SPECS,
    FORGE_MAX_HP_COST,
    CardSpec,
    ForgeViolation,
    card_power,
    describe,
    fallback_card,
    forged_deal,
    validate_spec,
)
from agentic_rogue_like.models import CardType, DealKind, Scaling
from agentic_rogue_like.style import PlayStyle


def _card(name: str):
    return next(c for c in REWARD_POOL + PROGRAM_REWARD_POOL if c.name == name).model_copy()


# ---- the budget and the rules text


@pytest.mark.parametrize("style", list(PlayStyle))
def test_every_fallback_design_is_inside_the_budget(style: PlayStyle) -> None:
    card = fallback_card(style, program_mode=True)
    assert card.description == describe(FALLBACK_SPECS[style])
    # classic runs get a design without line scalings
    assert fallback_card(style, program_mode=False).scaling not in (
        Scaling.LINES,
        Scaling.FIRST_LINE,
        Scaling.LAST_LINE,
    )


def test_the_game_writes_the_rules_text() -> None:
    spec = CardSpec(
        name="Core Dump",
        attack=True,
        value=3,
        scaling=Scaling.GRAVEYARD,
        scale_value=3,
        discard_cost=1,
    )
    assert describe(spec) == (
        "Discard 1 random card. Deal 3 (+ATK) damage, +3 per card in your Graveyard."
    )
    assert card_power(spec) == 3 + 3 * 4 - 3
    worm = CardSpec(name="Worm", attack=True, value=2, hits=2, malware=3, one_shot=True)
    assert describe(worm) == "One-shot. Hit 2 times for 2 (+ATK) damage. Infect it with 3 Malware."


def test_a_design_outside_the_rules_is_rejected() -> None:
    with pytest.raises(ForgeViolation, match="power 40.0"):
        validate_spec(CardSpec(name="Nuke", attack=True, value=20, hits=2), program_mode=False)
    with pytest.raises(ForgeViolation, match="power 5.0"):
        validate_spec(CardSpec(name="Dud", attack=True, value=5), program_mode=False)
    with pytest.raises(ForgeViolation, match="block card"):
        validate_spec(CardSpec(name="Wall", attack=False, value=7, hits=2), program_mode=False)
    with pytest.raises(ForgeViolation, match="program mode"):
        validate_spec(
            CardSpec(name="Main", attack=True, value=6, scaling=Scaling.LINES, scale_value=3),
            program_mode=False,
        )
    card = validate_spec(CardSpec(name="Air Gap", attack=False, value=13), program_mode=False)
    assert card.type is CardType.BLOCK and card.value == 13


# ---- the deal: when it comes, what it costs


def test_the_agi_forges_once_as_the_first_boss_reward() -> None:
    run = new_run(3)
    run.artifact_offer = run.kit_offer = run.agi_deals = None
    run.player.deck += [_card("Stack Overflow"), _card("Brute Force"), _card("Stack Overflow")]
    offer_forged_card(run)
    assert run.agi_deals is None  # act 1: still watching

    run.act = 2  # the first boss is down
    offer_forged_card(run)
    (deal,) = run.agi_deals
    assert deal.kind is DealKind.FORGED
    assert "GRAVEYARD" in deal.greeting
    forged = deal.add[0]
    assert forged.name == "Core Dump" and forged.description in deal.description

    deck, max_hp = len(run.player.deck), run.player.max_hp
    choose_deal(run, 0)
    assert len(run.player.deck) == deck + len(deal.add)
    assert run.player.max_hp == max_hp + deal.max_hp
    # once per run
    offer_forged_card(run)
    assert run.agi_deals is None


def test_without_a_clear_style_the_agi_forges_for_the_leading_one() -> None:
    run = new_run(3)
    run.artifact_offer = run.kit_offer = run.agi_deals = None
    run.act = 2
    offer_forged_card(run)  # nothing chosen yet: raw attacks
    assert "RAW ATTACKS" in run.agi_deals[0].greeting


def test_every_forged_deal_has_a_price() -> None:
    card = fallback_card(PlayStyle.AGGRO, program_mode=False)
    prices = set()
    for seed in range(20):
        deal = forged_deal(card, PlayStyle.AGGRO, random.Random(seed))
        glitch = any(c.type is CardType.GLITCH for c in deal.add)
        assert glitch or deal.max_hp == -FORGE_MAX_HP_COST
        prices.add(glitch)
    assert prices == {True, False}


# ---- the card agent


class _Scripted:
    def __init__(self, *specs: CardSpec) -> None:
        self.specs, self.prompts = list(specs), []

    def with_structured_output(self, schema):
        assert schema is CardSpec
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.specs.pop(0)


def test_the_card_agent_retries_with_the_reason(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    too_strong = CardSpec(name="Overkill", attack=True, value=24, hits=3)
    fair = CardSpec(
        name="Necro Cache", attack=True, value=4, scaling=Scaling.GRAVEYARD, scale_value=2
    )
    model = _Scripted(too_strong, fair)
    with patch.object(card_agent.encounter_agent, "_model", return_value=model):
        card, by_agent = card_agent.card_for_style(
            PlayStyle.GRAVEYARD, ["Stack Overflow"], program_mode=False, setting="cyberpunk"
        )

    assert by_agent and card.name == "Necro Cache"
    assert card.description == "Deal 4 (+ATK) damage, +2 per card in your Graveyard."
    assert "cyberpunk" in model.prompts[0] and "Stack Overflow" in model.prompts[0]
    assert "rejected: power 72.0" in model.prompts[1]


def test_the_card_agent_falls_back_to_the_static_design(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    always_bad = _Scripted(*[CardSpec(name="Dud", attack=True, value=1)] * 3)
    with patch.object(card_agent.encounter_agent, "_model", return_value=always_bad):
        card, by_agent = card_agent.card_for_style(PlayStyle.AGGRO, [], program_mode=False)
    assert not by_agent and card.name == "Brute Loop"
    assert len(always_bad.prompts) == card_agent.MAX_ATTEMPTS


def test_a_forged_card_has_to_fit_the_analysed_style() -> None:
    counts_permanents = CardSpec(
        name="Botnet Bomb", attack=True, value=4, scaling=Scaling.PERMANENT, scale_value=4
    )
    with pytest.raises(ForgeViolation, match="doesn't fit a deck that leans on one-shot cards"):
        validate_spec(counts_permanents, program_mode=False, style=PlayStyle.ONE_SHOT)
    assert validate_spec(counts_permanents, program_mode=False, style=PlayStyle.PERMANENTS)
    # the static design for a banish deck pays off the banished pile
    assert fallback_card(PlayStyle.ONE_SHOT, program_mode=False).scaling is Scaling.BANISHED


def test_the_card_agent_only_hears_the_scalings_of_the_style(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    wrong = CardSpec(
        name="Botnet Bomb", attack=True, value=4, scaling=Scaling.PERMANENT, scale_value=4
    )
    right = CardSpec(
        name="Shred Storm", attack=True, value=4, scaling=Scaling.BANISHED, scale_value=4
    )
    model = _Scripted(wrong, right)
    with patch.object(card_agent.encounter_agent, "_model", return_value=model):
        card, by_agent = card_agent.card_for_style(PlayStyle.ONE_SHOT, ["Payload"], False)
    assert by_agent and card.name == "Shred Storm"
    assert "banished (typically" in model.prompts[0] and "permanent (" not in model.prompts[0]
    assert "doesn't fit a deck that leans on one-shot cards" in model.prompts[1]
