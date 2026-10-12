import random

import pytest

from agentic_rogue_like import sessions
from agentic_rogue_like.engine import new_run


@pytest.fixture
def clock(monkeypatch):
    """A fake monotonic clock, and an empty session store for each test."""
    now = [1000.0]
    monkeypatch.setattr(sessions, "_now", lambda: now[0])
    monkeypatch.setattr(sessions, "_sessions", sessions.OrderedDict())
    return now


def _create() -> str:
    return sessions.create_session(new_run(1), random.Random(1))


def test_session_expires_after_ttl(clock, monkeypatch):
    monkeypatch.setattr(sessions, "SESSION_TTL_SECONDS", 60)
    run_id = _create()

    clock[0] += 59
    assert sessions.get_session(run_id) is not None

    # The lookup above refreshed it, so the TTL counts from there.
    clock[0] += 59
    assert sessions.get_session(run_id) is not None

    clock[0] += 60
    assert sessions.get_session(run_id) is None


def test_expired_sessions_are_freed_on_create(clock, monkeypatch):
    monkeypatch.setattr(sessions, "SESSION_TTL_SECONDS", 60)
    _create()
    _create()

    clock[0] += 61
    _create()

    assert len(sessions._sessions) == 1


def test_least_recently_used_session_makes_room(clock, monkeypatch):
    monkeypatch.setattr(sessions, "MAX_SESSIONS", 2)
    first, second = _create(), _create()

    # Touching the first one makes the second the least recently used.
    sessions.get_session(first)
    third = _create()

    assert sessions.get_session(second) is None
    assert sessions.get_session(first) is not None
    assert sessions.get_session(third) is not None


def test_evicted_session_cancels_its_prefetch(clock, monkeypatch):
    monkeypatch.setattr(sessions, "MAX_SESSIONS", 1)
    run_id = _create()
    cancelled = []
    sessions._sessions[run_id].prefetch.cancel_all = lambda: cancelled.append(run_id)

    _create()

    assert cancelled == [run_id]
