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
