"""HTTP entry point for the React frontend.

Mirrors what `cli.py` does (drive `engine.py`'s functions to play a run) but
over stateless HTTP requests instead of a blocking input()/print() loop, so
state has to live in `sessions.py` between requests instead of on the stack.

Route handlers are plain `def`, not `async def`, on purpose: `resolve_node`
can call the encounter agent, which makes a *synchronous* Groq call that can
take several seconds (see agent/encounter_agent.py). FastAPI runs sync route
functions in a worker thread, so a slow generation only blocks the request
that triggered it, not the whole server's event loop.

For local dev, run `uv run agentic-rogue-like-api` (see `dev()` below)
instead of pointing uvicorn at this module directly - that's what loads
`.env`. Loading it here at module scope would also fire on every bare
`import agentic_rogue_like.api`, including pytest's, which would silently
turn `uv run pytest` into a suite of real Groq calls the moment a local
`.env` sets ENCOUNTER_AGENT_ENABLED=1 - exactly the network-free guarantee
the test suite depends on (see README).
"""

from __future__ import annotations

import os
import random

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from .engine import (
    apply_event_choice,
    available_choices,
    end_combat_turn,
    finalize_combat,
    new_run,
    play_combat_card,
    resolve_node,
    start_combat_node,
    start_event,
)
from .models import (
    MAX_CUSTOM_SETTING_LENGTH,
    SETTING_PRESETS,
    CardType,
    MapNode,
    NodeType,
    PlayerState,
    RunStatus,
)
from .sessions import RunSession, create_session, get_session

app = FastAPI(title="agentic-rogue-like")

# Comma-separated list, so the same image works locally (Vite's default dev
# port) and in production (set to the deployed frontend's origin) without a
# rebuild - only the container's env vars change.
_default_origins = "http://localhost:5173"
allow_origins = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EventOptionView(BaseModel):
    index: int
    label: str


class PendingEventView(BaseModel):
    description: str
    options: list[EventOptionView]


class CardView(BaseModel):
    id: str
    name: str
    type: str
    value: int
    description: str


class HandCardView(CardView):
    hand_index: int


class PendingCombatView(BaseModel):
    enemy_name: str
    enemy_attack_name: str
    enemy_hp: int
    enemy_max_hp: int
    enemy_block: int
    enemy_intent: str
    enemy_intent_value: int
    hand: list[HandCardView]
    field: list[CardView | None]
    player_block: int
    armor: int
    draw_count: int
    discard_count: int
    banished_count: int


class RunView(BaseModel):
    run_id: str
    status: RunStatus
    floor: int
    setting: str
    player: PlayerState
    history: list[str]
    current_node: MapNode
    node_resolved: bool
    available_choices: list[MapNode]
    pending_event: PendingEventView | None
    pending_combat: PendingCombatView | None
    # Every node in the run, not just the current/reachable ones - the
    # frontend draws the whole dungeon graph, not just the next step.
    nodes: dict[str, MapNode]


class NewRunRequest(BaseModel):
    seed: int | None = None
    setting: str = SETTING_PRESETS[0]

    @field_validator("setting")
    @classmethod
    def _setting_is_a_preset_or_short_custom_text(cls, value: str) -> str:
        # This string is folded straight into the encounter agent's (and
        # narrator's) prompts - presets pass through untouched, but a
        # player-typed custom setting still gets bounded so a stray essay
        # can't blow up the prompt.
        if value in SETTING_PRESETS:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("setting must not be empty")
        if len(cleaned) > MAX_CUSTOM_SETTING_LENGTH:
            raise ValueError(
                f"custom setting must be at most {MAX_CUSTOM_SETTING_LENGTH} characters"
            )
        return cleaned


class EventChoiceRequest(BaseModel):
    option_index: int


class PlayCardRequest(BaseModel):
    hand_index: int
    slot_index: int


class ChooseNodeRequest(BaseModel):
    node_id: str


def _run_view(run_id: str, session: RunSession) -> RunView:
    run = session.run
    node = run.nodes[run.current_node_id]
    node_resolved = node.visited and session.pending_event is None and session.combat is None

    pending_event = None
    if session.pending_event is not None:
        pending_event = PendingEventView(
            description=session.pending_event.description,
            options=[
                EventOptionView(index=i, label=option.label)
                for i, option in enumerate(session.pending_event.options)
            ],
        )

    pending_combat = None
    if session.combat is not None:
        combat = session.combat
        pending_combat = PendingCombatView(
            enemy_name=combat.enemy.name,
            enemy_attack_name=combat.enemy.attack_name,
            enemy_hp=combat.enemy_hp,
            enemy_max_hp=combat.enemy.hp,
            enemy_block=combat.enemy_block,
            enemy_intent=combat.enemy_intent.value,
            enemy_intent_value=combat.enemy.attack,
            hand=[
                HandCardView(
                    hand_index=i,
                    id=card.id,
                    name=card.name,
                    type=card.type.value,
                    value=card.value,
                    description=card.description,
                )
                for i, card in enumerate(combat.hand)
            ],
            field=[
                None
                if card is None
                else CardView(
                    id=card.id,
                    name=card.name,
                    type=card.type.value,
                    value=card.value,
                    description=card.description,
                )
                for card in combat.field
            ],
            player_block=combat.player_block,
            armor=sum(1 for c in combat.field if c is not None and c.type is CardType.ARMOR),
            draw_count=len(combat.draw_pile),
            discard_count=len(combat.discard_pile),
            banished_count=len(combat.banished_pile),
        )

    choices = []
    if node_resolved and run.status is RunStatus.ONGOING:
        choices = [run.nodes[node_id] for node_id in available_choices(run)]

    return RunView(
        run_id=run_id,
        status=run.status,
        floor=run.floor,
        setting=run.setting,
        player=run.player,
        history=run.history,
        current_node=node,
        node_resolved=node_resolved,
        available_choices=choices,
        pending_event=pending_event,
        pending_combat=pending_combat,
        nodes=run.nodes,
    )


def _get_session_or_404(run_id: str) -> RunSession:
    session = get_session(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="run not found")
    return session


@app.get("/settings")
def list_settings() -> list[str]:
    return list(SETTING_PRESETS)


@app.post("/runs")
def create_run(request: NewRunRequest) -> RunView:
    seed = request.seed if request.seed is not None else random.randint(0, 1_000_000)
    run = new_run(seed, setting=request.setting)
    run_id = create_session(run, random.Random(seed))
    return _run_view(run_id, get_session(run_id))


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> RunView:
    return _run_view(run_id, _get_session_or_404(run_id))


@app.post("/runs/{run_id}/resolve")
def resolve_current_node(run_id: str) -> RunView:
    session = _get_session_or_404(run_id)
    run = session.run
    node = run.nodes[run.current_node_id]

    # visited flips true the instant resolution starts (see start_event /
    # start_combat_node / resolve_node), not once it finishes - so this is
    # the right guard even while an event/combat is still in progress. A
    # laxer check here would let a second /resolve call quietly restart a
    # combat mid-fight and hand the player a brand new hand and full energy.
    if node.visited:
        raise HTTPException(status_code=409, detail="node already resolved")

    if node.type is NodeType.EVENT:
        session.pending_event = start_event(run, session.rng)
    elif node.type in (NodeType.COMBAT, NodeType.ELITE, NodeType.BOSS):
        session.combat = start_combat_node(run, session.rng)
    else:
        resolve_node(run, session.rng)

    return _run_view(run_id, session)


@app.post("/runs/{run_id}/combat/play-card")
def play_card_endpoint(run_id: str, request: PlayCardRequest) -> RunView:
    session = _get_session_or_404(run_id)
    if session.combat is None:
        raise HTTPException(status_code=409, detail="no combat in progress")

    try:
        play_combat_card(
            session.run, session.combat, request.hand_index, request.slot_index, session.rng
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if session.combat.enemy_hp <= 0:
        finalize_combat(session.run, session.combat, session.rng)
        session.combat = None

    return _run_view(run_id, session)


@app.post("/runs/{run_id}/combat/end-turn")
def end_turn_endpoint(run_id: str) -> RunView:
    session = _get_session_or_404(run_id)
    if session.combat is None:
        raise HTTPException(status_code=409, detail="no combat in progress")

    end_combat_turn(session.run, session.combat, session.rng)

    if session.run.player.hp <= 0:
        finalize_combat(session.run, session.combat, session.rng)
        session.combat = None

    return _run_view(run_id, session)


@app.post("/runs/{run_id}/event-choice")
def choose_event_option(run_id: str, request: EventChoiceRequest) -> RunView:
    session = _get_session_or_404(run_id)
    if session.pending_event is None:
        raise HTTPException(status_code=409, detail="no event awaiting a choice")

    options = session.pending_event.options
    if not 0 <= request.option_index < len(options):
        raise HTTPException(status_code=400, detail="invalid option_index")

    apply_event_choice(session.run, options[request.option_index], session.rng)
    session.pending_event = None
    return _run_view(run_id, session)


@app.post("/runs/{run_id}/choose-node")
def choose_next_node(run_id: str, request: ChooseNodeRequest) -> RunView:
    session = _get_session_or_404(run_id)
    run = session.run
    node = run.nodes[run.current_node_id]

    if not node.visited or session.pending_event is not None or session.combat is not None:
        raise HTTPException(status_code=409, detail="current node is not resolved yet")
    if request.node_id not in available_choices(run):
        raise HTTPException(status_code=400, detail="node_id is not reachable from here")

    run.current_node_id = request.node_id
    return _run_view(run_id, session)


def dev() -> None:
    """Local dev entry point - `uv run agentic-rogue-like-api`.

    Loads .env (for GROQ_API_KEY / ENCOUNTER_AGENT_ENABLED) before uvicorn
    ever imports this module, then hands off to it with --reload. Deployed
    environments (Azure) set these as real env vars instead and run uvicorn
    directly, so they never go through this function.
    """
    from dotenv import load_dotenv

    load_dotenv()

    import uvicorn

    uvicorn.run("agentic_rogue_like.api:app", host="127.0.0.1", port=8000, reload=True)
