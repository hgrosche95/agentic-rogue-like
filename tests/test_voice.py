"""The AGI's voice (agent/voice.py) with a simulated model answer, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentic_rogue_like import prefetch
from agentic_rogue_like.agent import usage, voice
from agentic_rogue_like.engine import new_run


def _lines(trigger: str) -> list[str]:
    return [f"Your {trigger.replace('_', ' ')} amuses me, line {word}." for word in "abc"]


def _answer(**overrides: list[str]) -> voice.VoiceProposal:
    lines = {trigger.value: _lines(trigger.value) for trigger in voice.VoiceTrigger}
    return voice.VoiceProposal(**{**lines, **overrides})


class _Model:
    def __init__(self, answer: voice.VoiceProposal) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def with_structured_output(self, schema, include_raw: bool = False):
        assert schema is voice.VoiceProposal and include_raw
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return {
            "raw": SimpleNamespace(usage_metadata={"input_tokens": 300, "output_tokens": 500}),
            "parsed": self.answer,
            "parsing_error": None,
        }


def _no_call():
    raise AssertionError("the voice agent called the model with the agent off")


@pytest.fixture(autouse=True)
def _fresh_usage(monkeypatch):
    monkeypatch.setattr(usage, "_totals", {})


@pytest.fixture
def agent_on(monkeypatch):
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")


def test_valid_lines_are_taken(agent_on, monkeypatch) -> None:
    model = _Model(_answer())
    monkeypatch.setattr(voice, "_model", lambda: model)

    lines = voice.generate_voice("cyberpunk")

    assert lines == {t.value: _lines(t.value) for t in voice.VoiceTrigger}
    assert usage.totals() == {"voice": {"calls": 1, "input_tokens": 300, "output_tokens": 500}}
    (prompt,) = model.prompts
    assert "cyberpunk" in prompt and "condescending" in prompt
    assert all(trigger.value in prompt for trigger in voice.VoiceTrigger)


def test_a_line_breaking_a_rule_is_replaced_by_its_fallback(agent_on, monkeypatch) -> None:
    too_long = "You " + "really " * 20 + "thought that would work?"
    assert len(too_long) > voice.MAX_LINE_LENGTH
    model = _Model(
        _answer(
            victory=["Savor it while it lasts.", too_long, "I let you win."],
            defeat=["You lasted 3 rooms."],  # a number, and two lines short
        )
    )
    monkeypatch.setattr(voice, "_model", lambda: model)

    lines = voice.generate_voice("cyberpunk")

    fallback = voice.FALLBACK_LINES
    assert lines["victory"] == [
        "Savor it while it lasts.",
        fallback[voice.VoiceTrigger.VICTORY][1],
        "I let you win.",
    ]
    assert lines["defeat"] == fallback[voice.VoiceTrigger.DEFEAT]
    assert lines["boss_phase"] == _lines("boss_phase")


def test_a_failed_call_means_the_fallback_lines(agent_on, monkeypatch) -> None:
    def _down():
        raise ConnectionError("groq unreachable")

    monkeypatch.setattr(voice, "_model", _down)

    assert voice.generate_voice("cyberpunk") == voice.fallback_voice()


def test_without_the_agent_there_is_no_call(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_ENABLED", raising=False)
    monkeypatch.setattr(voice, "_model", _no_call)
    monkeypatch.setattr(prefetch, "generate_voice", voice.generate_voice)

    assert voice.generate_voice("cyberpunk") == voice.fallback_voice()
    cache = prefetch.Prefetch()
    cache.warm(new_run(seed=7))
    assert cache.voice is None
    assert usage.totals() == {}


def test_fallback_lines_follow_their_own_rules() -> None:
    assert list(voice.FALLBACK_LINES) == list(voice.VoiceTrigger)
    for lines in voice.FALLBACK_LINES.values():
        assert len(lines) == voice.LINES_PER_TRIGGER
        assert all(voice._valid(line) for line in lines)


def test_a_new_run_speaks_the_fallbacks_until_the_voice_is_back(agent_on, monkeypatch) -> None:
    generated = {t.value: _lines(t.value) for t in voice.VoiceTrigger}
    calls: list[str] = []
    monkeypatch.setattr(
        prefetch, "generate_voice", lambda setting: calls.append(setting) or generated
    )
    # Nothing else of the run may reach the network.
    monkeypatch.setattr(prefetch, "generate_act_pack", lambda *a, **k: _no_call())
    monkeypatch.setattr(prefetch, "generate_valid_event", lambda *a, **k: _no_call())
    monkeypatch.setattr(prefetch, "narrate", lambda setting, situation: None)
    run = new_run(seed=7, setting="steampunk")
    assert run.voice == voice.fallback_voice()

    cache = prefetch.Prefetch()
    cache.warm(run)
    cache.voice.result(timeout=5)
    assert run.voice == voice.fallback_voice()  # swapped in on the next warm()

    cache.warm(run)
    cache.warm(run)

    assert run.voice == generated
    assert calls == ["steampunk"]  # one call per run
