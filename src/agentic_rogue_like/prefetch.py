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

Regular and elite enemies are not generated per room: the first warm() of
an act starts one generate_act_pack call (agent/act_pack.py) for all of the
act's enemies, and enemy_for_node() draws each room's enemy out of that pack.
Only bosses (other than the fixed final one) still get a call of their own.

Nothing here decides a fallback: a prefetched enemy - or the act pack - is
handed to enemy_for_node() as a callable, so a failed generation lands in the
same static-pool fallback as a live one, and a prefetched narration is
whatever narrate() returned (None on any failure).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field

from .agent.act_pack import ActPack, generate_act_pack
from .agent.encounter_agent import generate_balanced_enemy
from .agent.event_agent import agent_enabled as event_agent_enabled
from .agent.event_agent import generate_valid_event
from .agent.narrator import narrate
from .agent.voice import generate_voice
from .enemies import tier_floor
from .engine import REST_SITUATION, SHOP_SITUATION, is_final_boss, switch_choices
from .events import EVENT_POOL, GameEvent
from .map_gen import NUM_FLOORS
from .models import Enemy, NodeType, RunState, RunStatus
from .style import agent_hint

# Shared by all runs. The work is waiting on HTTP, not CPU, so a handful of
# threads is plenty for a hobby deployment.
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="prefetch")


def _situations(node_type: NodeType) -> list[str]:
    if node_type is NodeType.REST:
        return [REST_SITUATION]
    if node_type is NodeType.SHOP:
        return [SHOP_SITUATION]
    if node_type is NodeType.EVENT and not event_agent_enabled():
        # Which static event a room holds is only drawn from the run's rng
        # once it is entered, so narrate the whole (small) pool up front.
        return [event.description for event in EVENT_POOL]
    return []


@dataclass
class Prefetch:
    # Keyed by node id: each boss room gets its own enemy.
    enemies: dict[str, Future[Enemy]] = field(default_factory=dict)
    # Keyed by act: one pack holds all of an act's regular and elite enemies.
    act_packs: dict[int, Future[ActPack]] = field(default_factory=dict)
    # Keyed by situation text: the setting is fixed for a run, so a
    # narration is interchangeable between rooms of the same kind.
    flavors: dict[str, Future[str | None]] = field(default_factory=dict)
    # Keyed by node id: each event room gets its own agent-written event.
    events: dict[str, Future[GameEvent]] = field(default_factory=dict)
    # The AGI's lines for the whole run (agent/voice.py): one call, started
    # on the run's first warm(), and copied onto the run by the first warm()
    # after it is back.
    voice: Future[dict[str, list[str]]] | None = None
    voice_applied: bool = False

    def warm(self, run: RunState) -> None:
        """Start generating content for the current room and every room reachable from it."""
        if os.environ.get("ENCOUNTER_AGENT_ENABLED") != "1":
            return
        self._warm_voice(run)
        if run.status is not RunStatus.ONGOING:
            return

        # The rooms the player can still switch to stay warm too, until the
        # one they jumped into is entered.
        upcoming = [
            run.current_node_id,
            *run.nodes[run.current_node_id].connections,
            *switch_choices(run),
        ]

        # Enemies for rooms the player walked past are dead weight. cancel()
        # only stops ones still queued; a running call just finishes unused.
        for pending in (self.enemies, self.events):
            for node_id in list(pending):
                if node_id not in upcoming:
                    pending.pop(node_id).cancel()

        # Exactly one pack call per act, on its first warm(); a finished act's
        # pack is dead weight like a room walked past.
        for act in list(self.act_packs):
            if act != run.act:
                self.act_packs.pop(act).cancel()
        if run.act not in self.act_packs:
            self.act_packs[run.act] = _executor.submit(generate_act_pack, run.setting, run.act)

        for node in (run.nodes[node_id] for node_id in upcoming):
            if node.visited:
                continue
            # Regular and elite rooms draw from the act pack; the final boss
            # is fixed (engine.is_final_boss) - nothing to generate.
            if (
                node.type is NodeType.BOSS
                and node.id not in self.enemies
                and not is_final_boss(run, node)
            ):
                self.enemies[node.id] = _executor.submit(
                    generate_balanced_enemy,
                    # Placeholder - enemy_for_node() swaps in the rng-drawn id.
                    enemy_id="prefetched",
                    floor=tier_floor(node.floor, NUM_FLOORS, run.act),
                    num_floors=NUM_FLOORS,
                    elite=False,
                    boss=True,
                    setting=run.setting,
                    # Bosses' moves are fixed, so they answer no style.
                    counter_hint=agent_hint(None, run.player.deck),
                )
            if node.type is NodeType.EVENT and event_agent_enabled() and node.id not in self.events:
                self.events[node.id] = _executor.submit(generate_valid_event, run.setting)
            for situation in _situations(node.type):
                if situation not in self.flavors:
                    self.flavors[situation] = _executor.submit(narrate, run.setting, situation)

    def _warm_voice(self, run: RunState) -> None:
        """Start the run's voice call once; once it is back, swap it in for
        the fallback lines - on the request thread, never from the worker,
        so the run is only ever changed where everything else changes it."""
        if self.voice is None:
            self.voice = _executor.submit(generate_voice, run.setting)
            return
        if self.voice_applied or not self.voice.done() or self.voice.cancelled():
            return
        self.voice_applied = True
        # generate_voice never raises - it falls back by itself.
        run.voice = self.voice.result()

    def cancel_all(self) -> None:
        """Drop everything still queued, e.g. when the run's session is evicted."""
        if self.voice is not None:
            self.voice.cancel()
        for future in [
            *self.enemies.values(),
            *self.act_packs.values(),
            *self.flavors.values(),
            *self.events.values(),
        ]:
            future.cancel()
        self.enemies.clear()
        self.act_packs.clear()
        self.flavors.clear()
        self.events.clear()

    def take_event(self, node_id: str) -> Callable[[], GameEvent] | None:
        """The prefetched event for `node_id` as a blocking getter, or None if none was started."""
        future = self.events.pop(node_id, None)
        return None if future is None else future.result

    def take_enemy(self, node_id: str) -> Callable[[], Enemy] | None:
        """The prefetched enemy for `node_id` as a blocking getter, or None if none was started."""
        future = self.enemies.pop(node_id, None)
        return None if future is None else future.result

    def act_pack(self, act: int) -> Callable[[], ActPack | None] | None:
        """The act's pack as a getter that never waits: the pack once its call
        is done (raising what the call raised), None while it is still
        running - or None instead of a getter if no pack was started."""
        future = self.act_packs.get(act)
        if future is None:
            return None

        def ready() -> ActPack | None:
            return future.result() if future.done() else None

        return ready

    def narrator(self, setting: str, situation: str) -> str | None:
        """Drop-in for narrate(): uses (and uses up) a prefetched line, else calls live."""
        future = self.flavors.pop(situation, None)
        if future is None:
            return narrate(setting, situation)
        return future.result()
