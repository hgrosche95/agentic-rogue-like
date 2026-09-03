"""Static placeholder events for Phase 1 - hand-authored for now.

Phase 2 replaces this fixed pool with agent-generated events built to the
same GameEvent/EventOption schema, so the game loop itself won't need to
change - only where content comes from.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from .models import PlayerState

EventEffect = Callable[[PlayerState, random.Random], str]


@dataclass
class EventOption:
    label: str
    effect: EventEffect


@dataclass
class GameEvent:
    description: str
    options: list[EventOption]


def _find_gold(player: PlayerState, rng: random.Random) -> str:
    amount = rng.randint(10, 30)
    player.gold += amount
    return f"You find {amount} gold."


def _leave_it(player: PlayerState, rng: random.Random) -> str:
    return "You walk on, nothing gained."


def _risky_shortcut(player: PlayerState, rng: random.Random) -> str:
    if rng.random() < 0.5:
        healed = min(10, player.max_hp - player.hp)
        player.hp += healed
        return f"The shortcut pays off. You recover {healed} HP."
    damage = rng.randint(5, 15)
    player.hp = max(player.hp - damage, 0)
    return f"The shortcut was a trap. You take {damage} damage."


def _safe_path(player: PlayerState, rng: random.Random) -> str:
    return "You stay the safe course."


def _rest_briefly(player: PlayerState, rng: random.Random) -> str:
    healed = min(5, player.max_hp - player.hp)
    player.hp += healed
    return f"You rest briefly and recover {healed} HP."


def _press_on(player: PlayerState, rng: random.Random) -> str:
    return "You press on without resting."


EVENT_POOL: list[GameEvent] = [
    GameEvent(
        description="A dusty chest sits half-buried in rubble.",
        options=[
            EventOption("Open it", _find_gold),
            EventOption("Leave it - could be trapped", _leave_it),
        ],
    ),
    GameEvent(
        description="A narrow shortcut splits off from the main path.",
        options=[
            EventOption("Take the shortcut", _risky_shortcut),
            EventOption("Stick to the main path", _safe_path),
        ],
    ),
    GameEvent(
        description="A quiet clearing offers a moment to catch your breath.",
        options=[
            EventOption("Rest here", _rest_briefly),
            EventOption("Press on", _press_on),
        ],
    ),
]


def random_event(rng: random.Random) -> GameEvent:
    return rng.choice(EVENT_POOL)
