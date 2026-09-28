"""Terminal entry point - `uv run agentic-rogue-like`."""

from __future__ import annotations

import random

from dotenv import load_dotenv

from .engine import available_choices, new_run, resolve_node
from .events import EventOption, GameEvent
from .models import Card, RunState, RunStatus


def _prompt_index(count: int) -> int:
    while True:
        raw = input("> ").strip()
        if raw.isdigit() and 1 <= int(raw) <= count:
            return int(raw) - 1
        print(f"Enter a number between 1 and {count}.")


def _choose_event_option(event: GameEvent) -> EventOption:
    print(f"\n{event.description}")
    for i, option in enumerate(event.options, start=1):
        print(f"  {i}. {option.label}")
    return event.options[_prompt_index(len(event.options))]


def _choose_card(offer: list[Card]) -> int | None:
    print("\nChoose a card to add to your deck:")
    for i, card in enumerate(offer, start=1):
        print(f"  {i}. {card.name} ({card.rarity.value}) - {card.description}")
    print(f"  {len(offer) + 1}. Skip")
    choice = _prompt_index(len(offer) + 1)
    return None if choice == len(offer) else choice


def _choose_next_node(run: RunState, choices: list[str]) -> str:
    print("\nPaths ahead:")
    for i, node_id in enumerate(choices, start=1):
        node = run.nodes[node_id]
        print(f"  {i}. {node.type.value} (floor {node.floor})")
    return choices[_prompt_index(len(choices))]


def main() -> None:
    load_dotenv()

    seed = random.randint(0, 1_000_000)
    print(f"agentic-rogue-like - seed {seed}\n")

    run = new_run(seed)
    rng = random.Random(seed)
    last_printed = 0

    try:
        while run.status is RunStatus.ONGOING:
            resolve_node(
                run, rng, choose_event_option=_choose_event_option, choose_card=_choose_card
            )
            for line in run.history[last_printed:]:
                print(line)
            last_printed = len(run.history)

            if run.status is not RunStatus.ONGOING:
                break

            run.current_node_id = _choose_next_node(run, available_choices(run))
    except (EOFError, KeyboardInterrupt):
        print("\nRun abandoned.")
        return

    print("\n--- Run over ---")
    print(f"Result: {run.status.value}")
    print(f"Reached floor {run.floor}")
    print(f"Gold collected: {run.player.gold}")
