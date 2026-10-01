import random

from agentic_rogue_like.engine import available_choices, new_run, resolve_node
from agentic_rogue_like.models import RunStatus


def _play_full_run(seed: int) -> None:
    run = new_run(seed)
    rng = random.Random(seed)
    steps = 0

    while run.status is RunStatus.ONGOING:
        resolve_node(run, rng)
        if run.status is not RunStatus.ONGOING:
            break

        run.current_node_id = available_choices(run)[0]

        steps += 1
        assert steps < 100, "run did not terminate - possible infinite loop in the map"

    assert run.status in (RunStatus.VICTORY, RunStatus.DEFEAT)


def test_run_always_terminates_in_victory_or_defeat() -> None:
    for seed in range(20):
        _play_full_run(seed)


def test_history_is_recorded_as_the_run_progresses() -> None:
    run = new_run(seed=42)
    rng = random.Random(42)

    resolve_node(run, rng)

    assert run.history


def _win_boss(run, rng) -> None:
    from agentic_rogue_like.engine import NUM_FLOORS

    run.current_node_id = f"{NUM_FLOORS - 1}-0"
    run.player.hp = run.player.max_hp = 10_000
    run.player.attack = 200
    resolve_node(run, rng)


def test_beating_the_first_boss_opens_act_two() -> None:
    run = new_run(seed=5)
    rng = random.Random(5)
    deck_size = len(run.player.deck)

    _win_boss(run, rng)

    assert run.status is RunStatus.ONGOING
    assert run.act == 2
    assert run.current_node_id == "0-0"
    assert run.nodes["0-0"].visited
    assert available_choices(run)
    assert len(run.player.deck) == deck_size + 1  # the boss's card reward


def test_beating_the_last_boss_wins_the_run() -> None:
    run = new_run(seed=5)
    rng = random.Random(5)
    _win_boss(run, rng)

    _win_boss(run, rng)

    assert run.status is RunStatus.VICTORY
