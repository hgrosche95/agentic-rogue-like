"""Artifacts - passive, run-long bonuses.

The player picks one of three at the start of a run and another one every
ARTIFACT_EVERY_STEPS steps on the map. Unlike cards they never have to be
drawn or played: each one is a bag of numbers (see models.Artifact) that the
engine and combat.py add up at fixed hook points - opening hand, every turn
end, after a fight, at a rest site, ... So a new artifact is a new entry in
ARTIFACT_POOL, not new code, as long as it only combines existing hooks.

They are there to help the player: a few trade a drawback for a bigger
upside (Overclocked CPU, Glass Cannon, ...), but none is a net loss.

VIBE_CODER_ARTIFACT_POOL holds the Vibe-Coder's own artifacts - they work on
his context window, so only he is offered them (CharacterProfile.artifact_pool).
"""

from __future__ import annotations

import random

from .models import Artifact, PlayerState

ARTIFACT_EVERY_STEPS = 3
ARTIFACT_CHOICES = 3

ARTIFACT_POOL: list[Artifact] = [
    Artifact(
        id="cache-line",
        name="Cache Line",
        description="Every 2nd turn, draw 1 extra card.",
        extra_draw=1,
        extra_draw_every=2,
    ),
    Artifact(
        id="self-healing-script",
        name="Self-Healing Script",
        description="Heal 6 HP after every won fight.",
        heal_after_combat=6,
    ),
    Artifact(
        id="overclocked-cpu",
        name="Overclocked CPU",
        description="Draw 1 extra card every turn, but enemy attacks deal 1 more damage.",
        extra_draw=1,
        enemy_attack=1,
    ),
    Artifact(
        id="tunnel-vision",
        name="Tunnel Vision",
        description="+4 ATK, but draw 1 card less every 2nd turn.",
        attack=4,
        extra_draw=-1,
        extra_draw_every=2,
    ),
    Artifact(
        id="heat-sink",
        name="Heat Sink",
        description="Start every fight with 8 block.",
        start_block=8,
    ),
    Artifact(
        id="extra-ram",
        name="Extra RAM",
        description="Hand limit +2, and every 3rd turn draw 1 extra card.",
        max_hand=2,
        extra_draw=1,
        extra_draw_every=3,
    ),
    Artifact(
        id="backdoor",
        name="Backdoor",
        description="At the start of every fight, deal 10 damage to the enemy.",
        opening_damage=10,
    ),
    Artifact(
        id="tarpit",
        name="Tarpit",
        description="Whenever an enemy attacks you, it takes 4 damage.",
        thorns=4,
    ),
    Artifact(
        id="titanium-chassis",
        name="Titanium Chassis",
        description="+15 max HP.",
        max_hp=15,
    ),
    Artifact(
        id="firmware-patch",
        name="Firmware Patch",
        description="Your block cards give 2 more block.",
        block_bonus=2,
    ),
    Artifact(
        id="medkit-exe",
        name="Medkit.exe",
        description="Your heal cards heal 4 more HP.",
        heal_bonus=4,
    ),
    Artifact(
        id="sharpened-payloads",
        name="Sharpened Payloads",
        description="+2 ATK.",
        attack=2,
    ),
    Artifact(
        id="hardened-kernel",
        name="Hardened Kernel",
        description="Reduce all incoming attack damage by 2.",
        armor=2,
    ),
    Artifact(
        id="sleep-mode",
        name="Sleep Mode",
        description="Rest sites heal 15 more HP, and heal 3 HP after every won fight.",
        rest_heal=15,
        heal_after_combat=3,
    ),
    Artifact(
        id="glass-cannon",
        name="Glass Cannon",
        description="+4 ATK, but -12 max HP.",
        attack=4,
        max_hp=-12,
    ),
    Artifact(
        id="lag-spike",
        name="Lag Spike",
        description="Enemies start every fight with 15% less HP.",
        enemy_hp_percent=-15,
    ),
    Artifact(
        id="watchdog-timer",
        name="Watchdog Timer",
        description="Every 2nd turn, gain 5 block before the enemy acts.",
        turn_block=5,
        turn_block_every=2,
    ),
    Artifact(
        id="quick-boot",
        name="Quick Boot",
        description="Your opening hand has 2 more cards.",
        opening_hand=2,
    ),
    Artifact(
        id="rate-limiter",
        name="Rate Limiter",
        description="Enemy attacks deal 3 less damage, but -1 ATK.",
        enemy_attack=-3,
        attack=-1,
    ),
    Artifact(
        id="vampire-process",
        name="Vampire Process",
        description="Every attack card you play heals you 1 HP.",
        lifesteal=1,
    ),
]


VIBE_CODER_ARTIFACT_POOL: list[Artifact] = [
    Artifact(
        id="pro-plan",
        name="Pro Plan",
        description="Your context window holds 1 more token.",
        token_window=1,
    ),
    Artifact(
        id="mechanical-keyboard",
        name="Mechanical Keyboard",
        description="The first card you play in every fight costs no tokens.",
        opening_free_plays=1,
    ),
    Artifact(
        id="lo-fi-beats",
        name="Lo-fi Beats",
        description=(
            "1 more token frees up at the end of every turn. Heal 3 HP after every won fight."
        ),
        token_regen=1,
        heal_after_combat=3,
    ),
    Artifact(
        id="system-prompt",
        name="System Prompt",
        description="Cards past your context window hallucinate half as often.",
        hallucination_percent=-50,
    ),
    Artifact(
        id="max-mode",
        name="Max Mode",
        description="+3 ATK, but 1 token less frees up at the end of every turn.",
        attack=3,
        token_regen=-1,
    ),
]


# Offered only in program-mode runs (RunState.program_mode), on top of the
# character's pool: they reward where things sit in a program and what runs
# next to what, never plain stats - see combat.run_program.
PROGRAM_ARTIFACT_POOL: list[Artifact] = [
    Artifact(
        id="hot-path",
        name="Hot Path",
        description=(
            "The card in line 2 of your program runs as its upgraded version, but "
            "enemies have 10% more HP."
        ),
        hot_path=2,
        enemy_hp_percent=10,
    ),
    Artifact(
        id="branch-predictor",
        name="Branch Predictor",
        description=(
            "Once the enemy is at half HP or less, every further action in your program gets +3."
        ),
        wounded_bonus=3,
    ),
    Artifact(
        id="tail-call",
        name="Tail Call",
        description="Every 2nd turn, the action in the last line of your program runs once more.",
        tail_call=1,
        tail_call_every=2,
    ),
    Artifact(
        id="pipeline",
        name="Pipeline",
        description="The action right after a control flow card gets +3.",
        pipeline=3,
    ),
    Artifact(
        id="compiler",
        name="Compiler",
        description=(
            "The action in the last line of your program gets +1 for every other card type "
            "that ran before it."
        ),
        compiler_bonus=1,
    ),
    Artifact(
        id="extra-line",
        name="Extra Line",
        description=(
            "Your program gets a 6th line, with no permanent under it. Every 2nd turn, "
            "draw 1 extra card."
        ),
        extra_lines=1,
        extra_draw=1,
        extra_draw_every=2,
    ),
]


def total(artifacts: list[Artifact], field: str) -> int:
    """Sum of one bonus field over all artifacts."""
    return sum(getattr(a, field) for a in artifacts)


def every_nth_turn(artifacts: list[Artifact], field: str, every_field: str, turn: int) -> int:
    """Sum of `field` over the artifacts whose every-N-turns interval hits `turn`."""
    return sum(getattr(a, field) for a in artifacts if turn % max(getattr(a, every_field), 1) == 0)


def roll_artifact_offer(
    rng: random.Random,
    owned: list[Artifact],
    count: int = ARTIFACT_CHOICES,
    pool: list[Artifact] | None = None,
) -> list[Artifact]:
    """`count` distinct artifacts from `pool` (ARTIFACT_POOL by default, see
    CharacterProfile.artifact_pool) the player doesn't own yet - fewer if the
    pool runs dry."""
    owned_ids = {a.id for a in owned}
    options = [a for a in (ARTIFACT_POOL if pool is None else pool) if a.id not in owned_ids]
    return rng.sample(options, min(count, len(options)))


def gain_artifact(player: PlayerState, artifact: Artifact) -> None:
    """Add `artifact` and apply its one-time stat changes (ATK, max HP)."""
    player.artifacts.append(artifact.model_copy(deep=True))
    player.attack += artifact.attack
    player.max_hp = max(player.max_hp + artifact.max_hp, 1)
    # More max HP comes filled, less max HP caps the current HP.
    player.hp = min(player.hp + max(artifact.max_hp, 0), player.max_hp)


def heal(player: PlayerState, amount: int) -> int:
    healed = max(0, min(amount, player.max_hp - player.hp))
    player.hp += healed
    return healed
