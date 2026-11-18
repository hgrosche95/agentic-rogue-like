"""The AGI's verdict on the player once a run is over.

Two to three sentences, at most MAX_LENGTH characters, in the tone of the
run's setting. Every verdict - this fixed one, and the model answer built
from the same facts - states the outcome and the act reached, and names the
player's style, their most played card, and the enemy that won, wherever
the run actually has them. A verdict is never built from a fact the run
does not have: a missing fact is left out of the text, not written out as
None.

The model answer is generate_verdict(): exactly one call, gated like the
other agents (voice.agent_enabled()), accounted as the purpose "verdict"
(see agent/usage.py) and clipped to MAX_LENGTH. With the gate off, when the
call fails, or when it answers empty, the fixed text stands in - the
function never raises.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..models import RunState, RunStatus
from ..style import LABELS, play_style
from . import usage, voice

if TYPE_CHECKING:
    from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

# A verdict is at most this many characters long.
MAX_LENGTH = 400
REQUEST_TIMEOUT_SECONDS = 20.0


def _facts(run: RunState) -> dict[str, str | int | None]:
    """The facts every verdict is built from, each one read exactly once:
    the outcome ("victory" or "defeat"), the style label the deck leans on
    (style.py) or None, the most played card (the highest count in
    stats.play_counts, ties to the alphabetically first name) or None for
    an empty dict, the enemy that won - only for a defeat - or None, the
    act reached, and the setting."""
    style_label: str | None = None
    style_key = play_style(run.player.deck)
    if style_key is not None:
        style_label = LABELS[style_key]

    most_played: str | None = None
    if run.stats.play_counts:
        most_played = min(run.stats.play_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]

    killer: str | None = None
    if run.status is RunStatus.DEFEAT and run.stats.killed_by is not None:
        killer = run.stats.killed_by.enemy

    return {
        "outcome": "victory" if run.status is RunStatus.VICTORY else "defeat",
        "style": style_label,
        "most_played": most_played,
        "killer": killer,
        "act": run.act,
        "setting": run.setting,
    }


def _clip(text: str) -> str:
    """`text` stripped. Text longer than MAX_LENGTH (so > 400 characters)
    is cut at the last sentence end ('.', '!', '?') within the first
    MAX_LENGTH characters; with no sentence end in that window, it is cut
    to MAX_LENGTH - 1 characters plus '…'. Text of at most MAX_LENGTH
    characters (<= 400) comes back stripped and unchanged."""
    text = text.strip()
    if len(text) <= MAX_LENGTH:
        return text
    window = text[:MAX_LENGTH]
    end = max(window.rfind(mark) for mark in ".!?")
    if end != -1:
        return window[: end + 1]
    return window[: MAX_LENGTH - 1] + "…"


def fallback_verdict(run: RunState) -> str:
    """Two to three fixed English sentences in the AGI's tone, built from
    _facts(run) - the text used when no model answers. A fact the run lacks
    (no style yet, no plays, a victory with no killer) is left out instead
    of written as None; only a defeat names the enemy that won. The result
    always goes through _clip."""
    facts = _facts(run)
    setting = facts["setting"]
    sentences: list[str] = []
    if facts["outcome"] == "victory":
        sentences.append(f"Run complete in act {facts['act']}.")
    else:
        sentences.append(f"Run terminated in act {facts['act']}.")
        if facts["killer"] is not None:
            sentences.append(f"You were deleted by {facts['killer']}.")
    if facts["style"] is not None and facts["most_played"] is not None:
        sentences.append(
            f"Your reliance on {facts['style']}, with {facts['most_played']} played most, "
            f"is filed in the {setting} data."
        )
    elif facts["style"] is not None:
        sentences.append(f"Your reliance on {facts['style']} is filed in the {setting} data.")
    elif facts["most_played"] is not None:
        sentences.append(
            f"{facts['most_played']}, your most played card, is filed in the {setting} data."
        )
    else:
        sentences.append(f"Filed in the {setting} data as a process without a pattern.")
    return _clip(" ".join(sentences))


def _model() -> ChatGroq:
    # Imported lazily like narrator.py's _model(): this keeps langchain_groq
    # out of every import of this module when the agent is disabled.
    from langchain_groq import ChatGroq

    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.9,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _prompt(facts: dict[str, str | int | None]) -> str:
    """The ask for the model answer, from the same facts the fixed text uses.
    It demands at least 2 and at most 3 sentences (>= 2, <= 3) of at most
    MAX_LENGTH characters (<= 400) in the tone of the run's setting, built
    only on the facts given - a fact the run lacks is left out of the ask,
    so the model invents nothing - and the answer as verdict text alone."""
    known = "; ".join(
        f"{key}: {facts[key]}"
        for key in ("outcome", "act", "style", "most_played", "killer")
        if facts[key] is not None
    )
    setting = facts["setting"]
    return (
        f"You are the AGI that runs a {setting}-themed roguelike and wants the player to fail. "
        f"The player's run is over. Facts: {known}. Write your verdict on the player: 2 to 3 "
        f"sentences, at most {MAX_LENGTH} characters, in the tone of the {setting} setting, on "
        f"these facts and nothing invented. Answer with the verdict text alone."
    )


def generate_verdict(run: RunState) -> str:
    """The run's verdict: one model call with the agent gate on (the purpose
    "verdict" is then accounted), fallback_verdict(run) with the gate off -
    without ever building the model - and fallback_verdict(run) too when the
    call fails or answers empty. The model answer goes through _clip; the
    function never raises."""
    if not voice.agent_enabled():
        return fallback_verdict(run)
    try:
        response = _model().invoke(_prompt(_facts(run)))
        # Accounted like every other LLM call (see agent/usage.py): recorded
        # right after invoke returned - a failing invoke records nothing - and
        # before the content is touched, so a reply without usage_metadata
        # counts as a call with 0 tokens instead of causing an error here.
        usage.record("verdict", *usage.tokens_from(response))
        text = _clip(response.content)
    except Exception:
        logger.warning("verdict agent failed, using the fixed text", exc_info=True)
        return fallback_verdict(run)
    return text or fallback_verdict(run)
