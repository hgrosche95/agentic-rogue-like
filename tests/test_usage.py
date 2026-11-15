"""Accounting for every LLM call (see agent/usage.py): sums per purpose, read
from the model reply's usage_metadata. No network - every reply here is a stub.
"""

import threading
from types import SimpleNamespace

import pytest

from agentic_rogue_like.agent import usage


@pytest.fixture(autouse=True)
def _empty_ledger(monkeypatch) -> None:
    """_totals is process-wide and usage.py offers no reset on purpose, so each
    test starts from an empty ledger and asserts only on what it recorded itself."""
    monkeypatch.setattr(usage, "_totals", {})


class _Proposal:
    """Stand-in for the pydantic schema invoke_structured forwards to LangChain."""


class _StructuredReply:
    """Model stub in the shape invoke_structured is specified to call:
    with_structured_output(schema, include_raw=True).invoke(prompt) answering with
    the raw reply, the parsed output and the parsing error LangChain reports."""

    def __init__(self, raw, parsed, parsing_error=None) -> None:
        self.calls: list[tuple[type, bool]] = []
        self.reply = {"raw": raw, "parsed": parsed, "parsing_error": parsing_error}

    def with_structured_output(self, schema: type, include_raw: bool = False):
        self.calls.append((schema, include_raw))
        return self

    def invoke(self, prompt: str) -> dict:
        return self.reply


def test_two_calls_sum() -> None:
    usage.record("encounter", 100, 20)
    usage.record("encounter", 50, 5)

    assert usage.totals() == {
        "encounter": {"aufrufe": 2, "eingabe_tokens": 150, "ausgabe_tokens": 25}
    }


def test_purposes_separate() -> None:
    usage.record("event", 1, 2)
    usage.record("narrator", 3, 4)

    totals = usage.totals()
    assert totals["event"] == {"aufrufe": 1, "eingabe_tokens": 1, "ausgabe_tokens": 2}
    assert totals["narrator"] == {"aufrufe": 1, "eingabe_tokens": 3, "ausgabe_tokens": 4}
    assert set(totals) == {"event", "narrator"}


def test_tokens_from_missing() -> None:
    """No usage_metadata attribute, one that is None, and one that only covers
    the input side all mean the same thing: 0 tokens, no exception."""
    assert usage.tokens_from(SimpleNamespace()) == (0, 0)
    assert usage.tokens_from(SimpleNamespace(usage_metadata=None)) == (0, 0)
    assert usage.tokens_from(SimpleNamespace(usage_metadata={"input_tokens": 7})) == (7, 0)


def test_threadsafe() -> None:
    """8 threads x 1000 calls, none of them lost on the way to the shared sums."""

    def hammer() -> None:
        for _ in range(1000):
            usage.record("x", 1, 2)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert usage.totals() == {
        "x": {"aufrufe": 8000, "eingabe_tokens": 8000, "ausgabe_tokens": 16000}
    }


def test_invoke_structured_records() -> None:
    model = _StructuredReply(
        SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 3}), parsed="P"
    )

    parsed = usage.invoke_structured(model, _Proposal, "invent an enemy", "encounter")

    assert model.calls == [(_Proposal, True)]  # token counts come from include_raw's raw reply
    assert parsed == "P"
    assert usage.totals() == {
        "encounter": {"aufrufe": 1, "eingabe_tokens": 10, "ausgabe_tokens": 3}
    }


def test_invoke_structured_parsing_error() -> None:
    """The call happened and cost tokens even though its output was unusable, so
    it is counted before the parsing error goes back to the caller."""
    model = _StructuredReply(
        SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 2}),
        parsed=None,
        parsing_error=ValueError("output did not match the schema"),
    )

    with pytest.raises(ValueError, match="output did not match the schema"):
        usage.invoke_structured(model, _Proposal, "invent an enemy", "event")

    assert usage.totals() == {"event": {"aufrufe": 1, "eingabe_tokens": 10, "ausgabe_tokens": 2}}
