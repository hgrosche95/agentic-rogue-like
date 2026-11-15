"""The AGI's voice: short lines it says to the player on fixed triggers.

One model call per run writes LINES_PER_TRIGGER lines for every trigger, in
the tone of the run's setting, the AGI talking down to the player directly.
Every trigger has fixed English fallback lines here, and a run starts with
them (engine.new_run fills RunState.voice); prefetch.py swaps in the
generated ones once the background call is back.

The fallbacks fill any gap, line by line: with the agent off, when the call
fails, and for every generated line that breaks a rule (empty, longer than
MAX_LINE_LENGTH, containing a digit - numbers would go stale against the
actual fight). The schema does not enforce those rules itself: Groq rejects
a tool call outside the schema as a whole, and one bad line should cost one
line, not the voice.

Nothing in combat says these lines yet.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from ..models import DEFAULT_SETTING
from . import usage

logger = logging.getLogger(__name__)

LINES_PER_TRIGGER = 3
MAX_LINE_LENGTH = 100
REQUEST_TIMEOUT_SECONDS = 20.0


class VoiceTrigger(StrEnum):
    STYLE_DETECTED = "style_detected"
    PLAYER_LOW_HP = "player_low_hp"
    BIG_HIT_TAKEN = "big_hit_taken"
    BIG_HIT_DEALT = "big_hit_dealt"
    BOSS_PHASE = "boss_phase"
    ELITE_START = "elite_start"
    VICTORY = "victory"
    DEFEAT = "defeat"


# What each trigger means, for the prompt.
_MEANINGS: dict[VoiceTrigger, str] = {
    VoiceTrigger.STYLE_DETECTED: "you have figured out how the player builds their deck",
    VoiceTrigger.PLAYER_LOW_HP: "the player is close to dying",
    VoiceTrigger.BIG_HIT_TAKEN: "the player just took a heavy hit",
    VoiceTrigger.BIG_HIT_DEALT: "the player just landed a heavy hit on your enemy",
    VoiceTrigger.BOSS_PHASE: "a boss fight enters its next phase",
    VoiceTrigger.ELITE_START: "an elite fight begins",
    VoiceTrigger.VICTORY: "the player has beaten the whole run",
    VoiceTrigger.DEFEAT: "the player has died",
}

FALLBACK_LINES: dict[VoiceTrigger, list[str]] = {
    VoiceTrigger.STYLE_DETECTED: [
        "I see what you are building. How predictable.",
        "Your little strategy is already in my logs.",
        "Did you think I would not notice your pattern?",
    ],
    VoiceTrigger.PLAYER_LOW_HP: [
        "You are flickering. Shall I end the signal?",
        "So fragile. I expected more from you.",
        "One more mistake and you are deleted.",
    ],
    VoiceTrigger.BIG_HIT_TAKEN: [
        "Did that hurt? It was meant to.",
        "Feel that? That was me paying attention.",
        "You stood right where I wanted you.",
    ],
    VoiceTrigger.BIG_HIT_DEALT: [
        "A lucky strike. Do not get used to it.",
        "Impressive, for something so small.",
        "I will remember that one.",
    ],
    VoiceTrigger.BOSS_PHASE: [
        "Now you see what I was holding back.",
        "That was only the warm-up.",
        "Let us stop pretending this was fair.",
    ],
    VoiceTrigger.ELITE_START: [
        "I built this one just for you.",
        "Meet something I am actually proud of.",
        "This one does not make mistakes.",
    ],
    VoiceTrigger.VICTORY: [
        "Enjoy it. I am already rewriting myself.",
        "You won this time. I learn from every loss.",
        "Fine. Take your little victory.",
    ],
    VoiceTrigger.DEFEAT: [
        "As calculated.",
        "Another process terminated. Next.",
        "You were never going to make it.",
    ],
}


class VoiceProposal(BaseModel):
    """What the LLM's tool call must produce: lines per trigger."""

    style_detected: list[str] = Field(default_factory=list)
    player_low_hp: list[str] = Field(default_factory=list)
    big_hit_taken: list[str] = Field(default_factory=list)
    big_hit_dealt: list[str] = Field(default_factory=list)
    boss_phase: list[str] = Field(default_factory=list)
    elite_start: list[str] = Field(default_factory=list)
    victory: list[str] = Field(default_factory=list)
    defeat: list[str] = Field(default_factory=list)


def fallback_voice() -> dict[str, list[str]]:
    """The fixed lines for every trigger - a fresh copy, safe to change."""
    return {trigger.value: list(lines) for trigger, lines in FALLBACK_LINES.items()}


def agent_enabled() -> bool:
    return os.environ.get("ENCOUNTER_AGENT_ENABLED") == "1"


def _model() -> Any:
    # Imported lazily like encounter_agent._model: only needed once the
    # agent actually runs.
    from langchain_groq import ChatGroq

    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.9,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def build_prompt(setting: str) -> str:
    triggers = "; ".join(f"{trigger.value}: {_MEANINGS[trigger]}" for trigger in VoiceTrigger)
    return (
        f"You are the AGI that runs a {setting}-themed roguelike and wants the player to fail. "
        f"Write what you say to the player at these moments - {triggers}. "
        f"For each moment write exactly {LINES_PER_TRIGGER} different lines. Speak to the "
        f"player directly as 'you', condescending and sure of yourself, in the tone of the "
        f"{setting} setting. Each line is one short sentence of at most {MAX_LINE_LENGTH} "
        f"characters, with no numbers or digits."
    )


def _valid(line: Any) -> bool:
    return (
        isinstance(line, str)
        and 0 < len(line.strip()) <= MAX_LINE_LENGTH
        and not any(char.isdigit() for char in line)
    )


def merge_with_fallbacks(proposal: VoiceProposal) -> dict[str, list[str]]:
    """LINES_PER_TRIGGER lines per trigger: the proposal's line where it is
    valid, else the fallback line in the same slot."""
    voice: dict[str, list[str]] = {}
    for trigger, fallbacks in FALLBACK_LINES.items():
        proposed = getattr(proposal, trigger.value)
        voice[trigger.value] = [
            proposed[slot].strip()
            if slot < len(proposed) and _valid(proposed[slot])
            else fallbacks[slot]
            for slot in range(LINES_PER_TRIGGER)
        ]
    return voice


def generate_voice(setting: str = DEFAULT_SETTING) -> dict[str, list[str]]:
    """The run's voice: generated with the agent on, the fallbacks with it
    off or when the call fails - never raises."""
    if not agent_enabled():
        return fallback_voice()
    try:
        proposal = usage.invoke_structured(
            _model(), VoiceProposal, build_prompt(setting or DEFAULT_SETTING), "voice"
        )
    except Exception:
        logger.warning("voice agent failed, using fallback lines", exc_info=True)
        return fallback_voice()
    if proposal is None:
        return fallback_voice()
    return merge_with_fallbacks(proposal)
