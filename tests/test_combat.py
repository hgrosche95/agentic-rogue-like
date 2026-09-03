import random

from agentic_rogue_like.combat import resolve_combat
from agentic_rogue_like.models import Enemy, PlayerState


def test_strong_player_wins() -> None:
    player = PlayerState(hp=50, max_hp=50, attack=20)
    enemy = Enemy(id="weak", name="Weak Thing", hp=5, attack=1)

    result = resolve_combat(player, enemy, random.Random(1))

    assert result.victory
    assert player.hp > 0


def test_weak_player_loses() -> None:
    player = PlayerState(hp=5, max_hp=5, attack=1)
    enemy = Enemy(id="strong", name="Strong Thing", hp=50, attack=20)

    result = resolve_combat(player, enemy, random.Random(1))

    assert not result.victory
    assert player.hp == 0


def test_combat_is_deterministic_for_a_given_rng_seed() -> None:
    player_a = PlayerState(hp=30, max_hp=30, attack=5)
    player_b = PlayerState(hp=30, max_hp=30, attack=5)
    enemy_a = Enemy(id="foe", name="Foe", hp=25, attack=4)
    enemy_b = Enemy(id="foe", name="Foe", hp=25, attack=4)

    result_a = resolve_combat(player_a, enemy_a, random.Random(99))
    result_b = resolve_combat(player_b, enemy_b, random.Random(99))

    assert result_a.log == result_b.log
    assert player_a.hp == player_b.hp
