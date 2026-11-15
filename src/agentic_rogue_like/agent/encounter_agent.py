"""LangGraph agent that generates a balanced Enemy via constrained tool-calling.

Wires together the schema and budgets built earlier: generate_enemy asks Groq
for an EnemyProposal, validate_budget checks it with the already-tested
validate_proposal(); a budget violation loops back to generate_enemy (capped)
instead of ever handing engine.py an out-of-budget Enemy.

Two layers, on purpose: generate_balanced_enemy() is strict and raises when the
agent can't deliver, which is what the tests pin down; enemy_for_node() wraps it
with the fallback to the static pool and is what the game loop should call.

Regular enemies from Groq come with their own move set (MovesetProposal) and
are held to the floor's threat range; bosses (fixed move set) and the
fine-tuned Ollama model (trained on the plain schema and prompt, see
training/) use the plain EnemyProposal and HP/attack ranges - see
encounter_schema.py.
"""

from __future__ import annotations

import logging
import os
import random
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NotRequired, TypedDict

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

    from .act_pack import ActPack

from ..enemies import pick_enemy, tier_floor
from ..models import DEFAULT_SETTING, Card, Enemy
from ..style import COUNTER_WEIGHT, PlayStyle, agent_hint, answers
from . import usage
from .budgets import budget_for
from .encounter_schema import (
    BudgetViolation,
    EnemyBudget,
    EnemyProposal,
    MovesetProposal,
    ThreatViolation,
    proposal_moves,
    validate_proposal,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 20.0


class EncounterState(TypedDict):
    budget: EnemyBudget
    setting: str
    attempt: int
    last_error: str | None
    proposal: EnemyProposal | None
    # Ask for a move set? Unset means _with_moves()' default; the training
    # pipeline pins it to False so its prompts and evals stay comparable.
    with_moves: NotRequired[bool]
    # A sentence steering the move set against the player's style (style.agent_hint).
    counter_hint: NotRequired[str | None]


def _model() -> Any:
    # Return type is Any on purpose: ChatGroq and OllamaChatModel share no
    # common base class, only the duck-typed with_structured_output(schema,
    # include_raw=...).invoke(prompt) interface that generate_enemy() (through
    # usage.invoke_structured) and the eval harness actually call.
    #
    # ENCOUNTER_AGENT_MODEL_SOURCE picks the source - "groq" (default) or
    # "ollama", the fine-tuned model served locally (see training/RESULTS.md
    # for how it compares). ENCOUNTER_AGENT_OLLAMA_MODEL overrides which
    # imported Ollama model tag to use, since training produced more than one
    # candidate (see OllamaChatModel's DEFAULT_MODEL_NAME for the current pick).
    if os.environ.get("ENCOUNTER_AGENT_MODEL_SOURCE") == "ollama":
        # Lazy for the same reason as the langchain_groq import below: this
        # module pulls in httpx, and the agent is off in the common case.
        from .ollama_model import DEFAULT_MODEL_NAME, OllamaChatModel

        # constrain_output=True on purpose: the default model needs it to be
        # schema-valid at all, and for models that don't it costs nothing
        # measurable (same latency in eval) while ruling out a whole failure
        # mode. So it stays on whichever model is configured.
        model_name = os.environ.get("ENCOUNTER_AGENT_OLLAMA_MODEL") or DEFAULT_MODEL_NAME
        return OllamaChatModel(model_name, constrain_output=True)

    # Imported lazily: langchain_groq is only needed once the encounter
    # agent actually runs (see enemy_for_node's ENCOUNTER_AGENT_ENABLED
    # check) - importing it at module scope would pull it into every
    # process that imports this module, agent disabled or not.
    from langchain_groq import ChatGroq

    # max_retries=0: the graph's own retry loop already caps attempts, and
    # stacking the client's retries on top would multiply the wait before
    # enemy_for_node() can fall back to the static pool.
    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.9,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _with_moves(state: EncounterState) -> bool:
    """Whether this call asks for a move set - not for bosses, whose moves are
    fixed, and not from the fine-tuned Ollama model, which was trained on the
    plain schema and prompt and has never seen a move set."""
    if state["budget"].boss:
        return False
    if "with_moves" in state:
        return state["with_moves"]
    return os.environ.get("ENCOUNTER_AGENT_MODEL_SOURCE") != "ollama"


def _build_prompt(state: EncounterState) -> str:
    if _with_moves(state):
        prompt = _moveset_prompt(state)
    else:
        prompt = _plain_prompt(state)
    if state["last_error"]:
        prompt += f" Your previous attempt was rejected: {state['last_error']}. Fix it."
    return prompt


# The move set prompt's pieces, shared with act_pack.py so a whole act's
# enemies are asked for under exactly the rules a single one is.
MOVESET_MOVE_RULES = (
    "Give it 2 to 4 moves that show how it fights - "
    "a hulking brute might slam and charge up, a swarm might barrage, a guardian might "
    "defend and purge, a plague bearer might infect, a saboteur might lock or corrupt. "
    "Every move set needs at least one attack or barrage. "
)
MOVESET_NAME_RULES = (
    "attack_name is its signature attack. "
    "Keep the description under 150 characters and every name under 40 characters."
)


def moveset_budget_rules(budget: EnemyBudget) -> str:
    """The prompt's attack, HP and threat rules for one budget."""
    low_hp, high_hp = budget.hp_bounds()
    return (
        f"attack is its base strength and must be between {budget.min_attack} and "
        f"{budget.max_attack}; each move's power is a percentage of it. "
        f"The whole enemy's danger is checked against this floor's budget: with plain "
        f"attack and defend moves at power 100, hp between {budget.min_hp} and {budget.max_hp} "
        f"fits. Stronger moves (high power, barrages, charges, purges, infections, locks, "
        f"corruptions) need less hp, "
        f"defensive ones allow more - hp must stay between {low_hp} and {high_hp}. "
    )


def _moveset_prompt(state: EncounterState) -> str:
    setting = state.get("setting") or DEFAULT_SETTING
    return (
        f"Invent an enemy for a {setting}-themed roguelike encounter. "
        f"Its name, description, attack_name and move names must fit the {setting} setting "
        f"instead of generic dungeon fantasy. "
        + MOVESET_MOVE_RULES
        + moveset_budget_rules(state["budget"])
        + MOVESET_NAME_RULES
        + (f" {hint}" if (hint := state.get("counter_hint")) else "")
    )


def _plain_prompt(state: EncounterState) -> str:
    # The fine-tuned Ollama model was trained on exactly this wording (see
    # training/data_gen) - change it and its evals no longer apply.
    setting = state.get("setting") or DEFAULT_SETTING
    prompt = (
        f"Invent an enemy for a {setting}-themed roguelike encounter. "
        f"Its name, description and attack_name must fit the {setting} setting "
        f"instead of generic dungeon fantasy. attack_name is what the enemy's "
        f"attack is called (e.g. 'Tusk Charge', not just 'Attack') and shows up "
        f"in the combat log as '<name> uses <attack_name> for N damage'. "
        f"It must have hp between {state['budget'].min_hp} and {state['budget'].max_hp}, "
        f"and attack between {state['budget'].min_attack} and {state['budget'].max_attack}. "
        f"Keep the description under 150 characters and attack_name under 40 characters."
    )
    return prompt


def generate_enemy(state: EncounterState) -> EncounterState:
    schema = MovesetProposal if _with_moves(state) else EnemyProposal
    # usage.invoke_structured(): the call is accounted for (see agent/usage.py),
    # and the proposal comes back exactly as a plain invoke() handed it out.
    proposal = usage.invoke_structured(_model(), schema, _build_prompt(state), "encounter")
    return {**state, "proposal": proposal, "attempt": state["attempt"] + 1}


def fit_to_budget(proposal: EnemyProposal, budget: EnemyBudget) -> EnemyProposal:
    """The proposal inside its budget - itself, or with its HP retuned - or the
    BudgetViolation that keeps it out.

    A ThreatViolation - everything inside its budget except the threat - is
    retuned without another model call: threat is proportional to HP, so the
    fitting HP the violation carries is the proposal's own HP rescaled onto the
    middle of the threat range. It is applied only when it sits inside the HP
    this budget allows at all (hp_bounds). Every other violation, and a threat
    no allowed HP prices right, is raised with its original message.
    """
    try:
        validate_proposal(proposal, budget)
        return proposal
    except ThreatViolation as exc:
        low_hp, high_hp = budget.hp_bounds()
        if not (low_hp <= exc.fitting_hp <= high_hp):
            # No HP this budget allows prices the threat right - the retry's
            # real job is the move set, so it goes back as the original error.
            raise
        # The one correction attempt: rescaled onto the middle of the threat
        # range, and checked through the normal validation path.
        corrected = proposal.model_copy(update={"hp": exc.fitting_hp})
        try:
            validate_proposal(corrected, budget)
        except BudgetViolation:
            # Where threat is not exactly proportional to HP - an infect move
            # set prices its Malware by how long the fight lasts, which its own
            # HP decides - even an allowed HP can miss. Checked once, never
            # iterated: that one goes back as the original error.
            raise exc from None
        return corrected


def validate_budget(state: EncounterState) -> EncounterState:
    """Check the proposal against its budget, fixing what can be fixed here
    (fit_to_budget); what can't goes to the retry loop with its message."""
    try:
        proposal = fit_to_budget(state["proposal"], state["budget"])
    except BudgetViolation as exc:
        return {**state, "last_error": str(exc)}
    # From here on the (possibly corrected) proposal is what the graph works with.
    return {**state, "last_error": None, "proposal": proposal}


def _route_after_validation(state: EncounterState) -> str:
    if state["last_error"] is None:
        return "done"
    if state["attempt"] >= MAX_ATTEMPTS:
        return "give_up"
    return "retry"


def build_graph() -> CompiledStateGraph:
    # Same lazy-import reasoning as _model() above, for langgraph.
    from langgraph.graph import END, StateGraph

    graph = StateGraph(EncounterState)
    graph.add_node("generate_enemy", generate_enemy)
    graph.add_node("validate_budget", validate_budget)
    graph.set_entry_point("generate_enemy")
    graph.add_edge("generate_enemy", "validate_budget")
    graph.add_conditional_edges(
        "validate_budget",
        _route_after_validation,
        {"done": END, "retry": "generate_enemy", "give_up": END},
    )
    return graph.compile()


def generate_balanced_enemy(
    enemy_id: str,
    floor: int,
    num_floors: int,
    elite: bool,
    boss: bool,
    setting: str = DEFAULT_SETTING,
    counter_hint: str | None = None,
) -> Enemy:
    budget = budget_for(floor=floor, num_floors=num_floors, elite=elite, boss=boss)
    app = build_graph()
    result: EncounterState = app.invoke(
        {
            "budget": budget,
            "setting": setting,
            "attempt": 0,
            "last_error": None,
            "proposal": None,
            "counter_hint": counter_hint,
        }
    )

    if result["last_error"] is not None:
        raise BudgetViolation(f"agent failed after {MAX_ATTEMPTS} attempts: {result['last_error']}")

    proposal = result["proposal"]
    moves = None if budget.boss else proposal_moves(proposal)
    return Enemy(
        id=enemy_id,
        name=proposal.name,
        description=proposal.description,
        hp=proposal.hp,
        attack=proposal.attack,
        attack_name=proposal.attack_name,
        **({} if moves is None else {"moves": moves}),
    )


def enemy_for_node(
    enemy_id: str,
    floor: int,
    num_floors: int,
    elite: bool,
    boss: bool,
    rng: random.Random,
    setting: str = DEFAULT_SETTING,
    prefetched: Callable[[], Enemy] | None = None,
    act: int = 1,
    style: PlayStyle | None = None,
    final: bool = False,
    deck: list[Card] | None = None,
    act_pack: Callable[[], ActPack | None] | None = None,
    pack_rng: random.Random | None = None,
) -> Enemy:
    """Agent-generated enemy, degrading to the static pool if the agent can't deliver.

    This is the boundary the game loop calls: a dead API key, a rate limit or a
    model that never lands inside its budget must cost the player an interesting
    enemy, never the run. The catch is deliberately broad - anything escaping the
    LLM path lands here rather than on the player's terminal - and logged with a
    traceback, so a run that quietly plays on the static pool is still traceable.

    The static pool ignores `setting` - it's a fixed, pre-balanced fallback,
    not something worth theming - so a disabled or failed agent still means
    generic dungeon enemies regardless of what the player picked.

    `prefetched`, if given, stands in for the live agent call: the web API
    starts generation in the background while the player is still on the map
    (see prefetch.py) and hands the result in here, so its errors land in the
    same fallback as a live call's. Its placeholder id is swapped for
    `enemy_id` so ids still come from `rng` exactly as before.

    `act` > 1 only shifts which tier is picked (see enemies.tier_floor) -
    the extra strength of later acts is enemies.escalate()'s job.

    `style` is the player's play style (style.py): the agent is asked for a
    move set that answers it, the static pool weights its answers up.
    `deck` lets the agent hear the cards the style rests on (style.agent_hint).

    `final` (with `boss`) is the last act's boss: always the AGI itself
    from the static pool (enemies.ENEMY_POOL["final"]), never generated -
    the run ends on the same character every time, and no LLM call waits
    in front of it.

    `act_pack`, if given, is where regular and elite enemies come from instead
    of a call per room: the web API generates the whole act's enemies in one
    background call (prefetch.py, agent/act_pack.py) and hands in a getter
    that returns the pack once it is done, None while it isn't. An enemy of
    the room's tier is drawn from it - the ones answering `style`
    COUNTER_WEIGHT times as likely, like the static pool - and removed, so
    no two rooms get the same one. The draw uses `pack_rng`, seeded per room
    by the caller, so it never shifts `rng`'s other draws. A pack that is
    not done yet, failed, or has run out of the tier means the static pool,
    never a live call. Bosses ignore it.
    """
    if boss and final:
        return pick_enemy(
            floor=floor,
            num_floors=num_floors,
            elite=elite,
            boss=boss,
            rng=rng,
            act=act,
            final=True,
        )
    if os.environ.get("ENCOUNTER_AGENT_ENABLED") != "1":
        return pick_enemy(
            floor=floor,
            num_floors=num_floors,
            elite=elite,
            boss=boss,
            rng=rng,
            act=act,
            style=style,
        )

    if act_pack is not None and not boss:
        tier = "elite" if elite else _regular_tier(floor, num_floors, act)
        drawn = _draw_from_pack(
            act_pack,
            tier,
            enemy_id,
            style,
            pack_rng if pack_rng is not None else random.Random(enemy_id),
        )
        if drawn is not None:
            return drawn
        return pick_enemy(
            floor=floor,
            num_floors=num_floors,
            elite=elite,
            boss=boss,
            rng=rng,
            act=act,
            style=style,
        )

    try:
        if prefetched is not None:
            return prefetched().model_copy(update={"id": enemy_id})
        return generate_balanced_enemy(
            enemy_id=enemy_id,
            floor=tier_floor(floor, num_floors, act),
            num_floors=num_floors,
            elite=elite,
            boss=boss,
            setting=setting,
            counter_hint=agent_hint(style, deck),
        )
    except Exception:
        logger.warning("encounter agent failed, using static pool", exc_info=True)
        return pick_enemy(
            floor=floor,
            num_floors=num_floors,
            elite=elite,
            boss=boss,
            rng=rng,
            act=act,
            style=style,
        )


def _regular_tier(floor: int, num_floors: int, act: int) -> str:
    """A regular room's tier in an act pack - the same split pick_enemy and
    budget_for make (act 2 on has no early tier, see enemies.tier_floor)."""
    return "early" if tier_floor(floor, num_floors, act) < num_floors // 2 else "mid"


def _draw_from_pack(
    act_pack: Callable[[], ActPack | None],
    tier: str,
    enemy_id: str,
    style: PlayStyle | None,
    rng: random.Random,
) -> Enemy | None:
    """One enemy of `tier` out of the pack, removed from it - None if the pack
    isn't there (not done, failed) or holds no enemy of that tier any more."""
    try:
        pack = act_pack()
    except Exception:
        logger.warning("act pack failed, using static pool", exc_info=True)
        return None
    if pack is None:
        return None
    enemies: list[Enemy] = getattr(pack, tier)
    if not enemies:
        return None
    weights = [COUNTER_WEIGHT if answers(e, style) else 1 for e in enemies]
    (index,) = rng.choices(range(len(enemies)), weights=weights)
    return enemies.pop(index).model_copy(update={"id": enemy_id}, deep=True)
