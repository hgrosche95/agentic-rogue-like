"""Background generation of the next rooms' LLM content for the web API.

Without this, every /resolve call that lands on a combat room waits for the
encounter agent (up to MAX_ATTEMPTS Groq calls) and every event/rest/shop
room waits for the narrator - the player stares at a disabled button for
seconds. Both only depend on things already known while the player is still
looking at the map (floor, room type, setting), so they can start as soon as
a room becomes reachable and are usually done by the time it is entered.

Only active with ENCOUNTER_AGENT_ENABLED=1, same switch as the agents
themselves - with it unset nothing is submitted and the game plays exactly as
before, which keeps the test suite network-free. The trade-off is extra LLM
calls: rooms the player could have picked but didn't were generated for
nothing.

Nothing here decides a fallback: a prefetched enemy is handed to
enemy_for_node() as a callable, so a failed generation lands in the same
static-pool fallback as a live one, and a prefetched narration is whatever
narrate() returned (None on any failure).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from .agent.encounter_agent import generate_balanced_enemy
from .agent.narrator import narrate
from .engine import REST_SITUATION, SHOP_SITUATION
from .events import EVENT_POOL
from .map_gen import NUM_FLOORS
from .models import Enemy, NodeType, RunState, RunStatus

_COMBAT_TYPES = (NodeType.COMBAT, NodeType.ELITE, NodeType.BOSS)

# Shared by all runs. The work is waiting on HTTP, not CPU, so a handful of
# threads is plenty for a hobby deployment.
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="prefetch")


def _situations(node_type: NodeType) -> list[str]:
    if node_type is NodeType.REST:
        return [REST_SITUATION]
    if node_type is NodeType.SHOP:
        return [SHOP_SITUATION]
    if node_type is NodeType.EVENT:
        # Which event an EVENT room holds is only drawn from the run's rng
        # once it is entered, so narrate the whole (small) pool up front.
        return [event.description for event in EVENT_POOL]
    return []


@dataclass
class Prefetch:
    # Keyed by node id: each combat room gets its own enemy.
    enemies: dict[str, Future[Enemy]] = field(default_factory=dict)
    # Keyed by situation text: the setting is fixed for a run, so a
    # narration is interchangeable between rooms of the same kind.
    flavors: dict[str, Future[str | None]] = field(default_factory=dict)

    def warm(self, run: RunState) -> None:
        """Start generating content for the current room and every room reachable from it."""
        if os.environ.get("ENCOUNTER_AGENT_ENABLED") != "1" or run.status is not RunStatus.ONGOING:
            return

        upcoming = [run.current_node_id, *run.nodes[run.current_node_id].connections]

        # Enemies for rooms the player walked past are dead weight. cancel()
        # only stops ones still queued; a running call just finishes unused.
        for node_id in list(self.enemies):
            if node_id not in upcoming:
                self.enemies.pop(node_id).cancel()

        for node in (run.nodes[node_id] for node_id in upcoming):
            if node.visited:
                continue
            if node.type in _COMBAT_TYPES and node.id not in self.enemies:
                self.enemies[node.id] = _executor.submit(
                    generate_balanced_enemy,
                    # Placeholder - enemy_for_node() swaps in the rng-drawn id.
                    enemy_id="prefetched",
                    floor=node.floor,
                    num_floors=NUM_FLOORS,
                    elite=node.type is NodeType.ELITE,
                    boss=node.type is NodeType.BOSS,
                    setting=run.setting,
                )
            for situation in _situations(node.type):
                if situation not in self.flavors:
                    self.flavors[situation] = _executor.submit(narrate, run.setting, situation)

    def take_enemy(self, node_id: str) -> Callable[[], Enemy] | None:
        """The prefetched enemy for `node_id` as a blocking getter, or None if none was started."""
        future = self.enemies.pop(node_id, None)
        return None if future is None else future.result

    def narrator(self, setting: str, situation: str) -> str | None:
        """Drop-in for narrate(): uses (and uses up) a prefetched line, else calls live."""
        future = self.flavors.pop(situation, None)
        if future is None:
            return narrate(setting, situation)
        return future.result()
