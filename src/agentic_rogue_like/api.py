"""HTTP entry point for the React frontend - `uvicorn agentic_rogue_like.api:app`.

Mirrors what `cli.py` does (drive `engine.py`'s functions to play a run) but
over stateless HTTP requests instead of a blocking input()/print() loop, so
state has to live in `sessions.py` between requests instead of on the stack.

Route handlers are plain `def`, not `async def`, on purpose: `resolve_node`
can call the encounter agent, which makes a *synchronous* Groq call that can
take several seconds (see agent/encounter_agent.py). FastAPI runs sync route
functions in a worker thread, so a slow generation only blocks the request
that triggered it, not the whole server's event loop.
"""

from __future__ import annotations

import os
import random

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .engine import apply_event_choice, available_choices, new_run, resolve_node, start_event
from .models import MapNode, NodeType, PlayerState, RunStatus
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


class RunView(BaseModel):
    run_id: str
    status: RunStatus
    floor: int
    player: PlayerState
    history: list[str]
    current_node: MapNode
    node_resolved: bool
    available_choices: list[MapNode]
    pending_event: PendingEventView | None


class NewRunRequest(BaseModel):
    seed: int | None = None


class EventChoiceRequest(BaseModel):
    option_index: int


class ChooseNodeRequest(BaseModel):
    node_id: str


def _run_view(run_id: str, session: RunSession) -> RunView:
    run = session.run
    node = run.nodes[run.current_node_id]
    node_resolved = node.visited and session.pending_event is None

    pending_event = None
    if session.pending_event is not None:
        pending_event = PendingEventView(
            description=session.pending_event.description,
            options=[
                EventOptionView(index=i, label=option.label)
                for i, option in enumerate(session.pending_event.options)
            ],
        )

    choices = []
    if node_resolved and run.status is RunStatus.ONGOING:
        choices = [run.nodes[node_id] for node_id in available_choices(run)]

    return RunView(
        run_id=run_id,
        status=run.status,
        floor=run.floor,
        player=run.player,
        history=run.history,
        current_node=node,
        node_resolved=node_resolved,
        available_choices=choices,
        pending_event=pending_event,
    )


def _get_session_or_404(run_id: str) -> RunSession:
    session = get_session(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="run not found")
    return session


@app.post("/runs")
def create_run(request: NewRunRequest) -> RunView:
    seed = request.seed if request.seed is not None else random.randint(0, 1_000_000)
    run = new_run(seed)
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

    if node.visited and session.pending_event is None:
        raise HTTPException(status_code=409, detail="node already resolved")

    if node.type is NodeType.EVENT:
        session.pending_event = start_event(run, session.rng)
    else:
        resolve_node(run, session.rng)

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

    if not node.visited or session.pending_event is not None:
        raise HTTPException(status_code=409, detail="current node is not resolved yet")
    if request.node_id not in available_choices(run):
        raise HTTPException(status_code=400, detail="node_id is not reachable from here")

    run.current_node_id = request.node_id
    return _run_view(run_id, session)
