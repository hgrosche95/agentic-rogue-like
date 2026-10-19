"""In-memory run storage for the web API.

The CLI needed no session concept - one process, one run, state on the
stack. The API serves possibly-concurrent runs over stateless HTTP requests,
so each run's `RunState`, its `random.Random` (must persist between requests
to keep a seed's outcomes reproducible) and any event awaiting a player
choice live here, keyed by run_id. A dict is enough for now: runs are only
ever needed while the process is up, and losing them on restart is fine for
a single-player hobby project.

What a dict alone is not fine for is a long-running container: nobody ever
tells the server a run was abandoned, so without eviction every run ever
started stays in memory. Sessions therefore expire after SESSION_TTL_SECONDS
without a request, and MAX_SESSIONS caps how many live at once - beyond it
the least recently used one makes room. The dict is kept in access order
(OrderedDict + move_to_end), so both checks only ever look at its front.
"""

from __future__ import annotations

import os
import random
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from .combat import CombatState
from .events import GameEvent
from .models import RunState
from .prefetch import Prefetch

# Env-configurable so the same image can be tuned per deployment without a
# rebuild, like FRONTEND_ORIGINS in api.py.
SESSION_TTL_SECONDS = float(os.environ.get("SESSION_TTL_SECONDS", 2 * 60 * 60))
MAX_SESSIONS = int(os.environ.get("MAX_SESSIONS", 500))


def _now() -> float:
    # Indirection so tests can move the clock without sleeping.
    return time.monotonic()


@dataclass
class RunSession:
    run: RunState
    rng: random.Random
    pending_event: GameEvent | None = field(default=None)
    combat: CombatState | None = field(default=None)
    prefetch: Prefetch = field(default_factory=Prefetch)
    last_seen: float = field(default_factory=_now)


_sessions: OrderedDict[str, RunSession] = OrderedDict()
# FastAPI runs the (sync) endpoints in a thread pool, so two requests can
# touch the dict at once.
_lock = threading.Lock()


def _drop(run_id: str) -> None:
    # Queued LLM calls for a run nobody will finish are wasted quota.
    _sessions.pop(run_id).prefetch.cancel_all()


def _evict_expired(now: float) -> None:
    while _sessions:
        oldest_id, oldest = next(iter(_sessions.items()))
        if now - oldest.last_seen < SESSION_TTL_SECONDS:
            return
        _drop(oldest_id)


def create_session(run: RunState, rng: random.Random) -> str:
    run_id = uuid.uuid4().hex
    with _lock:
        now = _now()
        _evict_expired(now)
        while len(_sessions) >= MAX_SESSIONS:
            _drop(next(iter(_sessions)))
        _sessions[run_id] = RunSession(run=run, rng=rng, last_seen=now)
    return run_id


def get_session(run_id: str) -> RunSession | None:
    """The run's session, refreshing its expiry - or None if unknown or expired."""
    with _lock:
        now = _now()
        _evict_expired(now)
        session = _sessions.get(run_id)
        if session is not None:
            session.last_seen = now
            _sessions.move_to_end(run_id)
        return session
