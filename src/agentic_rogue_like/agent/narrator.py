"""One-line themed flavor text for non-combat rooms (Rest/Shop/Event).

Deliberately not a full agent like encounter_agent.py: there's no balance
budget to protect for flavor text, so no schema, no validation, no retry
loop - just one Groq call with the same fallback discipline as
enemy_for_node() (see agent/encounter_agent.py): disabled, unreachable, or
empty output all just mean "no flavor this time", never a broken run.

Callers always append their own mechanical text (heal amounts, gold
figures, ...) themselves - narrate() only ever supplies decoration, so a
hallucinated or dropped number here can't corrupt game state. That split is
the same "deterministic core vs. agent layer" boundary the whole project is
built around (see README).
"""

from __future__ import annotations

import logging
import os

from langchain_groq import ChatGroq

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10.0
MAX_LENGTH = 120


def _model() -> ChatGroq:
    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.9,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def narrate(setting: str, situation: str) -> str | None:
    """A short themed sentence describing `situation` in `setting`, or None
    if the encounter agent is disabled or the call fails for any reason -
    callers fall back to their own plain-English line in that case.
    """
    if os.environ.get("ENCOUNTER_AGENT_ENABLED") != "1":
        return None

    try:
        prompt = (
            f"Rewrite this roguelike moment to fit a {setting} setting, same "
            f"meaning, one vivid sentence, under {MAX_LENGTH} characters, no "
            f"quotes, no numbers: {situation}"
        )
        text = _model().invoke(prompt).content.strip()
        return text or None
    except Exception:
        logger.warning("narrator failed, using plain text", exc_info=True)
        return None
