"""In-memory run storage for the web API.

The CLI needed no session concept - one process, one run, state on the
stack. The API serves possibly-concurrent runs over stateless HTTP requests,
so each run's `RunState`, its `random.Random` (must persist between requests
to keep a seed's outcomes reproducible) and any event awaiting a player
choice live here, keyed by run_id. A dict is enough for now: runs are only
ever needed while the process is up, and losing them on restart is fine for
a single-player hobby project.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field

from .combat import CombatState
from .events import GameEvent
from .models import RunState


@dataclass
class RunSession:
    run: RunState
    rng: random.Random
    pending_event: GameEvent | None = field(default=None)
    combat: CombatState | None = field(default=None)


_sessions: dict[str, RunSession] = {}


def create_session(run: RunState, rng: random.Random) -> str:
    run_id = uuid.uuid4().hex
    _sessions[run_id] = RunSession(run=run, rng=rng)
    return run_id


def get_session(run_id: str) -> RunSession | None:
    return _sessions.get(run_id)
