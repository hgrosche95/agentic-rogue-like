import random
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from agentic_rogue_like.agent import event_agent
from agentic_rogue_like.cards import REWARD_POOL, starter_deck
from agentic_rogue_like.events import (
    EVENT_MAX_VALUE,
    EVENT_POOL,
    GOLD_PER_HP,
    EffectKind,
    EventEffect,
    EventOption,
    EventViolation,
    GameEvent,
    apply_option,
    describe_option,
    option_value,
    validate_event,
)
from agentic_rogue_like.models import PlayerState, Rarity


def _e(kind: str, amount: int = 0, rarity: Rarity | None = None) -> EventEffect:
    return EventEffect(kind=kind, amount=amount, rarity=rarity)


def _player(**kw) -> PlayerState:
    return PlayerState(**{"hp": 30, "max_hp": 45, "gold": 20, "deck": starter_deck(), **kw})


def _event(*options: EventOption) -> GameEvent:
    return GameEvent(description="Something happens.", options=list(options))


@pytest.mark.parametrize("event", EVENT_POOL, ids=lambda e: e.description[:20])
def test_every_static_event_is_a_real_choice(event: GameEvent) -> None:
    validate_event(event)


def test_an_option_without_a_price_is_rejected() -> None:
    free_gold = EventOption(label="Take it", effects=[_e("gold", 30)])
    with pytest.raises(EventViolation, match="no price"):
        validate_event(_event(free_gold, EventOption(label="Leave")))


def test_a_gamble_that_costs_nothing_when_it_fails_has_no_price() -> None:
    gamble = EventOption(label="Try", effects=[_e("gold", 40)], chance=0.5)
    with pytest.raises(EventViolation, match="no price"):
        validate_event(_event(gamble, EventOption(label="Leave")))


def test_an_option_worth_too_much_is_rejected() -> None:
    jackpot = EventOption(label="Grab", effects=[_e("add_card", rarity=Rarity.RARE), _e("hp", -2)])
    assert option_value(jackpot) > EVENT_MAX_VALUE
    with pytest.raises(EventViolation, match="more than"):
        validate_event(_event(jackpot, EventOption(label="Leave")))


def test_only_one_walk_away_option() -> None:
    with pytest.raises(EventViolation, match="at most one"):
        validate_event(_event(EventOption(label="A"), EventOption(label="B")))


def test_effects_are_bounded_and_well_formed() -> None:
    with pytest.raises(ValidationError):
        _e("gold", 500)
    with pytest.raises(ValidationError):
        _e("add_card")  # no rarity
    with pytest.raises(ValidationError):
        _e("lose_card", 3)  # no amount


def test_a_gamble_is_valued_by_its_chance() -> None:
    gamble = EventOption(
        label="Bet", effects=[_e("gold", 60)], chance=0.75, fail_effects=[_e("hp", -10)]
    )
    assert option_value(gamble) == pytest.approx(0.75 * 60 - 0.25 * 10 * GOLD_PER_HP)
    assert describe_option(gamble) == "75%: +60 gold - otherwise: -10 HP"


def test_applying_effects() -> None:
    player = _player(hp=12)
    option = EventOption(
        label="Deal",
        effects=[_e("gold", -50), _e("hp", -20), _e("add_card", rarity=Rarity.UNCOMMON)],
    )
    apply_option(option, player, REWARD_POOL, random.Random(1))

    assert player.gold == 0  # can't pay more than you have
    assert player.hp == 1  # events never kill
    assert player.deck[-1].rarity is Rarity.UNCOMMON


def test_max_hp_lose_card_and_upgrade() -> None:
    player = _player(hp=45)
    size = len(player.deck)
    option = EventOption(
        label="Change", effects=[_e("max_hp", -5), _e("lose_card"), _e("upgrade_card")]
    )
    text = apply_option(option, player, REWARD_POOL, random.Random(2))

    assert (player.max_hp, player.hp) == (40, 40)
    assert len(player.deck) == size - 1
    assert sum(c.upgraded for c in player.deck) == 1
    assert "becomes" in text


def test_leave_does_nothing() -> None:
    player = _player()
    before = player.model_copy(deep=True)
    assert apply_option(EventOption(label="Go"), player, REWARD_POOL, random.Random(1))
    assert player == before


class _Scripted:
    def __init__(self, *events):
        self.events, self.prompts = list(events), []

    def with_structured_output(self, schema):
        assert schema is GameEvent
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.events.pop(0)


def test_event_agent_retries_with_the_reason(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.delenv("ENCOUNTER_AGENT_MODEL_SOURCE", raising=False)
    too_good = _event(EventOption(label="Free", effects=[_e("gold", 30)]), EventOption(label="No"))
    fair = EVENT_POOL[1]
    model = _Scripted(too_good, fair)
    with patch.object(event_agent.encounter_agent, "_model", return_value=model):
        event, by_agent = event_agent.event_for_room(random.Random(1), "cyberpunk")

    assert by_agent and event == fair
    assert "cyberpunk" in model.prompts[0]
    assert "rejected: option 'Free' has no price" in model.prompts[1]


def test_event_agent_falls_back_to_the_pool(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    class _Down:
        def with_structured_output(self, schema):
            return self

        def invoke(self, prompt):
            raise ConnectionError("groq unreachable")

    with patch.object(event_agent.encounter_agent, "_model", return_value=_Down()):
        event, by_agent = event_agent.event_for_room(random.Random(1))

    assert not by_agent and event in EVENT_POOL


def test_event_agent_is_off_without_the_flag_or_on_ollama(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_ENABLED", raising=False)
    assert not event_agent.agent_enabled()
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.setenv("ENCOUNTER_AGENT_MODEL_SOURCE", "ollama")
    assert not event_agent.agent_enabled()


def test_effect_kinds_are_all_covered_by_the_pool() -> None:
    used = {
        e.kind
        for event in EVENT_POOL
        for option in event.options
        for e in option.effects + option.fail_effects
    }
    assert used == set(EffectKind)
