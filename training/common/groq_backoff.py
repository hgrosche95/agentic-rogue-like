"""Shared by eval/harness.py and data_gen/generate.py - both hammer the same
Groq free-tier limits (as of 2026-09: 8000 tokens/minute AND 200,000
tokens/day, both rolling windows) and both need the resulting wait to stay
out of whatever they're timing.

First version of this used a flat 15s sleep on every 429. Two problems
showed up in practice:
1. Groq's error message spells minutes-plus-seconds as "2m12.19s", which the
   original regex (tuned on the minute-limit's "4.38s"-style messages) didn't
   match at all - it silently fell back to the flat 15s, so a genuine 132s
   wait turned into nine separate 15s naps that each immediately 429'd again.
2. There's no point waiting out a daily-limit 429 within a single run: at
   200k/day, "the request that just failed" being retryable in 2 minutes
   doesn't mean the *next* 50 will be - the whole run is effectively blocked
   until real daily headroom returns. So a wait beyond _MAX_SINGLE_WAIT_SECONDS
   is treated as "not now" and raised immediately instead of blocking here.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable

from groq import RateLimitError

MAX_RATE_LIMIT_RETRIES = 8
# Only used if Groq's response has neither a retry-after header nor a
# parseable "try again in ...s" in the message - shouldn't normally trigger.
_FALLBACK_BACKOFF_SECONDS = 15.0
# Small safety margin: retrying a hair early just earns another 429.
_WAIT_MARGIN_SECONDS = 0.5
# A per-minute 429 clears in seconds; a per-day 429 can ask for minutes to
# hours. Waiting that long inside a single call would stall the whole run for
# no benefit - let the caller decide instead (retry later, abort, etc).
MAX_SINGLE_WAIT_SECONDS = 30.0

# Matches Groq's "try again in Xs" (minute limit) and "try again in XmY.Zs"
# (day limit) - hours haven't been observed but are parsed for the same reason.
_RETRY_AFTER_IN_MESSAGE = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s")


def _parse_wait_from_message(message: str) -> float | None:
    match = _RETRY_AFTER_IN_MESSAGE.search(message)
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    total = float(seconds)
    if minutes:
        total += int(minutes) * 60
    if hours:
        total += int(hours) * 3600
    return total


def _wait_seconds(exc: RateLimitError) -> float:
    header_value = exc.response.headers.get("retry-after")
    if header_value is not None:
        try:
            return float(header_value) + _WAIT_MARGIN_SECONDS
        except ValueError:
            pass
    parsed = _parse_wait_from_message(str(exc))
    if parsed is not None:
        return parsed + _WAIT_MARGIN_SECONDS
    return _FALLBACK_BACKOFF_SECONDS


class RateLimitTooLong(Exception):
    """Raised instead of blocking when a 429's wait exceeds MAX_SINGLE_WAIT_SECONDS -
    almost always a near-exhausted daily quota, not a burst worth sleeping out."""


def call_with_backoff[T](fn: Callable[[], T]) -> tuple[T, float]:
    """Returns (result, seconds spent in the successful attempt) - backoff
    sleeps between attempts are excluded from that duration on purpose."""
    for attempt in range(MAX_RATE_LIMIT_RETRIES):
        start = time.perf_counter()
        try:
            return fn(), time.perf_counter() - start
        except RateLimitError as exc:
            wait = _wait_seconds(exc)
            if wait > MAX_SINGLE_WAIT_SECONDS:
                cap = MAX_SINGLE_WAIT_SECONDS
                raise RateLimitTooLong(
                    f"rate limit wants {wait:.0f}s (>{cap:.0f}s cap): {exc}"
                ) from exc
            if attempt == MAX_RATE_LIMIT_RETRIES - 1:
                raise
            time.sleep(wait)
    raise AssertionError("unreachable")
