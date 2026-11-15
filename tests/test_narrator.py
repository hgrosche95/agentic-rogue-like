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


# --------------------------------------------------------- LLM usage accounting


class _UsedResponse:
    """A reply that carries usage_metadata, the way a real LangChain reply does."""

    def __init__(self, content: str, usage_metadata: dict) -> None:
        self.content = content
        self.usage_metadata = usage_metadata


class _TwoReplies:
    """Answers with `responses` in turn - the narrator is called twice here."""

    def __init__(self, *responses: _UsedResponse) -> None:
        self.responses = list(responses)

    def invoke(self, prompt: str) -> _UsedResponse:
        return self.responses.pop(0)


def test_narrator_usage_two_calls(monkeypatch) -> None:
    from agentic_rogue_like.agent import usage

    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.setattr(usage, "_totals", {})
    reply_one = _UsedResponse(
        "Neon rain hisses off cracked chrome.", {"input_tokens": 12, "output_tokens": 30}
    )
    reply_two = _UsedResponse(
        "Vending machines hum in the dark.", {"input_tokens": 8, "output_tokens": 10}
    )
    model = _TwoReplies(reply_one, reply_two)

    with patch.object(narrator, "_model", return_value=model):
        first = narrator.narrate("cyberpunk", "a quiet moment of rest")
        second = narrator.narrate("cyberpunk", "a shop full of humming machines")

    assert (first, second) == (
        "Neon rain hisses off cracked chrome.",
        "Vending machines hum in the dark.",
    )
    assert usage.totals()["narrator"] == {"calls": 2, "input_tokens": 20, "output_tokens": 40}


def test_narrator_without_usage_metadata(monkeypatch) -> None:
    """_WellBehaved's plain _Response has no usage_metadata: the text comes out
    unchanged and the call is counted with 0 tokens, not an error."""
    from agentic_rogue_like.agent import usage

    monkeypatch.setenv("ENCOUNTER_AGENT_ENABLED", "1")
    monkeypatch.setattr(usage, "_totals", {})

    with patch.object(narrator, "_model", return_value=_WellBehaved()):
        text = narrator.narrate("cyberpunk", "a quiet moment of rest")

    assert text == "Neon rain hisses off cracked chrome as you catch your breath."
    assert usage.totals()["narrator"] == {"calls": 1, "input_tokens": 0, "output_tokens": 0}
