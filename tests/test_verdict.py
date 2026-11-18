"""The AGI's verdict on the player (agent/verdict.py) with a simulated model answer, no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentic_rogue_like.agent import usage, verdict
from agentic_rogue_like.engine import new_run
from agentic_rogue_like.models import KillingBlow, RunState, RunStatus


@pytest.fixture(autouse=True)
def _fresh_usage(monkeypatch):
    monkeypatch.setattr(usage, "_totals", {})


@pytest.fixture
def agent_on(monkeypatch):
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")


def _run(status: RunStatus, act: int = 1) -> RunState:
    run = new_run(1)
    run.status = status
    run.act = act
    return run


class _Model:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.invocations = 0

    def invoke(self, prompt):
        self.invocations += 1
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            content=self.content,
            usage_metadata={"input_tokens": 40, "output_tokens": 60},
        )


def test_fallback_mentions_run_facts() -> None:
    run = _run(RunStatus.DEFEAT, act=2)
    run.stats.killed_by = KillingBlow(enemy="Null Pointer", move="Segfault")
    run.stats.play_counts = {"Refactor": 5, "Patch": 2}

    text = verdict.fallback_verdict(run)

    assert "Null Pointer" in text
    assert "Refactor" in text
    assert "2" in text


def test_fallback_victory_omits_killer() -> None:
    run = _run(RunStatus.VICTORY)
    run.stats.killed_by = None
    run.stats.play_counts = {}

    text = verdict.fallback_verdict(run)

    assert "None" not in text
    assert len(text) <= 400


def test_clip_cuts_at_sentence_end() -> None:
    text = " ".join(["Abc def ghi."] * 30)

    clipped = verdict._clip(text)

    assert len(clipped) <= 400
    assert clipped.endswith(".")


def test_clip_hard_cut_without_sentence_end() -> None:
    clipped = verdict._clip("x" * 600)

    assert len(clipped) == 400
    assert clipped.endswith("…")


def test_generate_uses_model_and_records_usage(agent_on, monkeypatch) -> None:
    model = _Model("You were adequate.")
    monkeypatch.setattr(verdict, "_model", lambda: model)

    result = verdict.generate_verdict(_run(RunStatus.DEFEAT))

    assert result == "You were adequate."
    assert model.invocations == 1
    assert "verdict" in usage.totals()


def test_generate_clips_long_model_text(agent_on, monkeypatch) -> None:
    model = _Model("y" * 900)
    monkeypatch.setattr(verdict, "_model", lambda: model)

    result = verdict.generate_verdict(_run(RunStatus.DEFEAT))

    assert len(result) <= 400


def test_generate_falls_back_on_error(agent_on, monkeypatch) -> None:
    model = _Model(error=RuntimeError("boom"))
    monkeypatch.setattr(verdict, "_model", lambda: model)
    run = _run(RunStatus.DEFEAT)

    assert verdict.generate_verdict(run) == verdict.fallback_verdict(run)


def test_generate_without_agent_never_builds_model(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_ENABLED", raising=False)

    def _no_model():
        raise AssertionError("the verdict built a model with the agent off")

    monkeypatch.setattr(verdict, "_model", _no_model)
    run = _run(RunStatus.DEFEAT)

    assert verdict.generate_verdict(run) == verdict.fallback_verdict(run)
