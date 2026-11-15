import pytest

from agentic_rogue_like import prefetch
from agentic_rogue_like.agent.voice import fallback_voice


@pytest.fixture(autouse=True)
def _no_voice_call(monkeypatch):
    """Every test that turns the agent on and warms a run would otherwise
    start a real voice call (agent/voice.py) in the background. The voice
    tests put their own stub over this one."""
    monkeypatch.setattr(prefetch, "generate_voice", lambda setting: fallback_voice())
