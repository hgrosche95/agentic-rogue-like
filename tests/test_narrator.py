from unittest.mock import patch

from agentic_rogue_like.agent import narrator


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _WellBehaved:
    def invoke(self, prompt: str) -> _Response:
        return _Response("Neon rain hisses off cracked chrome as you catch your breath.")


class _ApiIsDown:
    def invoke(self, prompt: str) -> _Response:
        raise ConnectionError("groq unreachable")


class _EmptyReply:
    def invoke(self, prompt: str) -> _Response:
        return _Response("   ")


def test_narrate_returns_none_when_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ENCOUNTER_AGENT_ENABLED", raising=False)

    def _fail_if_called() -> None:
        raise AssertionError("model should never be built when the agent is disabled")

    with patch.object(narrator, "_model", side_effect=_fail_if_called):
        assert narrator.narrate("cyberpunk", "a quiet moment of rest") is None


def test_narrate_returns_themed_text_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    with patch.object(narrator, "_model", return_value=_WellBehaved()):
        result = narrator.narrate("cyberpunk", "a quiet moment of rest")

    assert result == "Neon rain hisses off cracked chrome as you catch your breath."


def test_narrate_falls_back_to_none_when_the_api_is_unreachable(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    with patch.object(narrator, "_model", return_value=_ApiIsDown()):
        assert narrator.narrate("cyberpunk", "a quiet moment of rest") is None


def test_narrate_falls_back_to_none_on_empty_reply(monkeypatch) -> None:
    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")

    with patch.object(narrator, "_model", return_value=_EmptyReply()):
        assert narrator.narrate("cyberpunk", "a quiet moment of rest") is None
