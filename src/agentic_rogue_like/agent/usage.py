"""Usage accounting for every LLM call: one log line per call plus process-wide
totals per purpose ("encounter", "event", "narrator", "act_pack").

The numbers come from the model response's usage_metadata. For structured
output, usage.invoke_structured() asks for include_raw=True, because LangChain
otherwise hides the raw response (and with it usage_metadata) behind the parser.
Where usage_metadata is missing - no attribute, None, or a dict without the key -
the call counts with 0 tokens: what is measured is that the call happened.

A retry is a call of its own and is counted separately, because every attempt
costs tokens. A call is only counted once there is a response: if invoke itself
raises (network error, timeout), nothing is recorded; if it returns an answer
that cannot be parsed, that is recorded first and the error raised afterwards.

The totals are process-wide and deliberately have no reset API - a game process
should keep its total usage until it ends. Resetting is the tests' business
(monkeypatch replaces _totals). Every access, reading or writing, happens under
one lock, because the API server calls the agents from worker threads.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_totals: dict[str, dict[str, int]] = {}
_lock = threading.Lock()


def record(purpose: str, input_tokens: int, output_tokens: int) -> None:
    """A call happened: one log line for it, and it goes into this purpose's
    totals (calls, input_tokens, output_tokens)."""
    with _lock:
        total = _totals.setdefault(purpose, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
        total["calls"] += 1
        total["input_tokens"] += input_tokens
        total["output_tokens"] += output_tokens
    logger.info("llm usage purpose=%s input=%d output=%d", purpose, input_tokens, output_tokens)


def tokens_from(message: Any) -> tuple[int, int]:
    """(input, output) tokens of a model response, (0, 0) wherever the numbers
    are missing - including when the response itself is None."""
    metadata = getattr(message, "usage_metadata", None)
    return _token(metadata, "input_tokens"), _token(metadata, "output_tokens")


def totals() -> dict[str, dict[str, int]]:
    """A copy of the totals, so a reader (GET /usage) never writes to _totals
    itself; empty before the first call."""
    with _lock:
        return {purpose: dict(total) for purpose, total in _totals.items()}


def invoke_structured(model: Any, schema: type, prompt: Any, purpose: str) -> Any:
    """A structured call through include_raw=True, so the raw response's
    usage_metadata stays reachable: the call is recorded either way, and the
    parsed result is what comes back.

    LangChain delivers an unparsable answer in parsing_error; it is recorded
    first (it has long since cost its tokens) and then raised, just as the
    error was passed on without include_raw before.
    """
    result = model.with_structured_output(schema, include_raw=True).invoke(prompt)
    record(purpose, *tokens_from(result.get("raw")))
    parsing_error = result.get("parsing_error")
    if parsing_error is not None:
        raise parsing_error
    return result.get("parsed")


def _token(metadata: Any, key: str) -> int:
    """One value out of usage_metadata, 0 for anything that is not a number.
    LangChain delivers usage_metadata as a dict, other integrations as an object."""
    if metadata is None:
        return 0
    getter = getattr(metadata, "get", None)
    value = getter(key) if callable(getter) else getattr(metadata, key, None)
    return value if isinstance(value, int) else 0
