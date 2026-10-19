"""Balance simulator - `uv run balance-sim`.

Plays thousands of fights and full runs with a bot, no LLM and no network,
and prints win rate, turns per fight and HP lost per enemy tier. Enemies are
drawn uniformly from agent/budgets.py's envelopes - exactly the range the
encounter agent is allowed to generate in - so the numbers describe what a
real run can throw at the player.

Two ways to use it:
- `balance-sim` on its own: how the current cards/budgets play out;
- `balance-sim --compare variant.json`: the same seeds against a variant
  (changed budgets, player stats, card values or extra cards), side by side,
  so a card tweak or a new card is judged on numbers instead of a feeling.

A variant file only lists what changes, e.g.:

    {
      "budgets": {"early": {"min_hp": 45, "max_hp": 60}},
      "player": {"hp": 50, "attack": 5},
      "cards": {"Exploit": {"value": 5}},
      "extra_cards": [{"name": "Rootkit", "type": "attack", "value": 12}],
      "remove_cards": ["Prefetch"],
      "rewards": false,
      "artifacts": false
    }

`extra_cards` entries take every Card field (hits, exhaust, scaling, ...).
`"rewards": false` plays runs without the after-fight card reward, i.e.
with the starter deck only, `"artifacts": false` without artifacts.

`balance-sim --pool` fights the static enemy pool (enemies.py, what the game
uses whenever the encounter agent is off) instead of random enemies inside
the budgets - so a change to the pool shows up in the numbers.

`balance-sim --calibrate-threat` instead fits threat.py's model: it fights
a few hundred random move sets and searches for the parameters whose
threat() best predicts the damage those fights dealt (see calibrate_threat).
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .agent.budgets import _BUDGETS
from .agent.encounter_schema import EnemyBudget
from .artifacts import ARTIFACT_EVERY_STEPS, gain_artifact, heal, roll_artifact_offer, total
from .cards import (
    START_CARD_WEIGHTS,
    can_upgrade,
    reward_card,
    roll_card_reward,
    starter_deck,
    upgrade_card,
)
from .combat import (
    ATTACKING_INTENTS,
    MAX_AUTO_PLAYS_PER_TURN,
    MAX_AUTO_TURNS,
    CombatState,
    end_turn,
    play_card,
    start_combat,
)
from .enemies import ENEMY_POOL, escalate, pick_enemy, tier_floor
from .engine import ACT_HEAL_PERCENT, NUM_ACTS, boss_phases
from .events import random_event
from .map_gen import NUM_FLOORS, generate_map
from .models import (
    PERMANENT_CARD_TYPES,
    Card,
    CardType,
    Enemy,
    EnemyMove,
    MoveKind,
    NodeType,
    PlayerState,
    Rarity,
)
from .threat import DEFAULT_MODEL, ThreatModel, threat

TIERS = ("early", "mid", "elite", "boss")
REST_HEAL = 15  # mirrors engine.resolve_node's REST branch


# --------------------------------------------------------------------------- config


@dataclass
class SimConfig:
    name: str = "aktuell"
    budgets: dict[str, EnemyBudget] = field(default_factory=lambda: dict(_BUDGETS))
    player_hp: int = 45  # mirrors engine.PLAYER_HP
    player_attack: int = 2  # mirrors engine.PLAYER_ATTACK
    deck_factory: Callable[[], list[Card]] = starter_deck
    rewards: bool = True
    artifacts: bool = True
    # Fight enemies.py's static pool instead of random enemies in the budgets.
    pool: bool = False
    # Let bots upgrade a card at rest sites (see rest_choice) instead of
    # always healing.
    rest_upgrades: bool = True

    def new_player(self) -> PlayerState:
        return PlayerState(
            hp=self.player_hp,
            max_hp=self.player_hp,
            attack=self.player_attack,
            deck=self.deck_factory(),
        )


def load_variant(path: Path) -> SimConfig:
    raw = json.loads(path.read_text())
    base = SimConfig(name=path.stem)

    for tier, overrides in raw.get("budgets", {}).items():
        if tier not in TIERS:
            raise ValueError(f"unknown tier {tier!r}, expected one of {TIERS}")
        base.budgets[tier] = base.budgets[tier].model_copy(update=overrides)

    player = raw.get("player", {})
    base.player_hp = player.get("hp", base.player_hp)
    base.player_attack = player.get("attack", base.player_attack)
    base.rewards = raw.get("rewards", base.rewards)
    base.artifacts = raw.get("artifacts", base.artifacts)
    base.rest_upgrades = raw.get("rest_upgrades", base.rest_upgrades)

    card_overrides: dict[str, dict] = raw.get("cards", {})
    extra: list[dict] = raw.get("extra_cards", [])
    removed: list[str] = list(raw.get("remove_cards", []))

    def deck() -> list[Card]:
        cards = starter_deck()
        for name in removed:
            idx = next((i for i, c in enumerate(cards) if c.name == name), None)
            if idx is None:
                raise ValueError(f"remove_cards: no card named {name!r} in the deck")
            cards.pop(idx)
        cards = [c.model_copy(update=card_overrides.get(c.name, {})) for c in cards]
        for i, spec in enumerate(extra):
            cards.append(Card(**{"id": f"extra-{i}", "description": "", **spec}))
        return cards

    base.deck_factory = deck
    return base


def random_enemy(budget: EnemyBudget, tier: str, rng: random.Random) -> Enemy:
    return Enemy(
        id=f"sim-{tier}",
        name=tier,
        hp=rng.randint(budget.min_hp, budget.max_hp),
        attack=rng.randint(budget.min_attack, budget.max_attack),
        attack_name="Hit",
    )


# The floor a tier's enemies are scaled for (enemies.escalate) when fought on
# their own: mid and boss always sit in the timeline's second half, and an
# elite is measured there too - its harder case.
_TIER_FLOOR = {"early": 0, "mid": NUM_FLOORS // 2, "elite": NUM_FLOORS // 2, "boss": NUM_FLOORS - 1}


def tier_for(floor: int, node_type: NodeType, act: int = 1) -> str:
    if node_type is NodeType.BOSS:
        return "boss"
    if node_type is NodeType.ELITE:
        return "elite"
    return "early" if tier_floor(floor, NUM_FLOORS, act) < NUM_FLOORS // 2 else "mid"


# --------------------------------------------------------------------------- bots

Bot = Callable[[CombatState, PlayerState, random.Random], None]


def naive_bot(state: CombatState, player: PlayerState, rng: random.Random) -> None:
    """combat.auto_resolve_combat's policy: hand card 0 into the first free slot."""
    for _ in range(MAX_AUTO_PLAYS_PER_TURN):
        if not state.hand or state.enemy_hp <= 0:
            return
        slot = next((i for i, c in enumerate(state.field) if c is None), None)
        if slot is None:
            return
        play_card(state, 0, slot, player, rng)


def _empty_slots(state: CombatState) -> list[int]:
    return [i for i, c in enumerate(state.field) if c is None]


def _best_action_slot(state: CombatState) -> int | None:
    """Free slot with the most Amplifiers to its left."""
    best, best_score = None, -1
    for i in _empty_slots(state):
        amps = sum(
            1 for j, c in enumerate(state.field) if c and c.type is CardType.AMPLIFIER and j < i
        )
        if amps > best_score:
            best, best_score = i, amps
    return best


def _permanent_slot(state: CombatState, card: Card) -> int | None:
    """Amplifiers go far left, the rest fill from the right but always leave
    at least one slot free for action cards."""
    empty = _empty_slots(state)
    if len(empty) <= 1:
        return None
    if card.type is CardType.AMPLIFIER:
        return empty[0]
    return empty[-1]


def smart_bot(state: CombatState, player: PlayerState, rng: random.Random) -> None:
    """A reasonable human-ish policy: set up permanents, block only against an
    attack intent, heal only when hurt, fire Final Strike when it kills or the
    field is clogged, otherwise hit as hard as possible."""
    for _ in range(MAX_AUTO_PLAYS_PER_TURN):
        if not state.hand or state.enemy_hp <= 0:
            return
        played = False
        # 1. permanents first - they pay off for the rest of the fight.
        for idx, card in enumerate(state.hand):
            if card.type in PERMANENT_CARD_TYPES:
                slot = _permanent_slot(state, card)
                if slot is not None:
                    play_card(state, idx, slot, player, rng)
                    played = True
                    break
        if played:
            continue

        slot = _best_action_slot(state)
        if slot is None:
            return  # can't happen with _permanent_slot keeping one slot free

        permanents = sum(1 for c in state.field if c is not None)
        # card flow first - it only makes the rest of the turn better
        order: list[CardType] = [CardType.DRAW]
        if state.discard_pile:
            order.append(CardType.RETRIEVE)
        if state.banished_pile:
            order.append(CardType.RESTORE)
        order.append(CardType.ATTACK)
        if state.enemy_intent in ATTACKING_INTENTS:
            order.append(CardType.BLOCK)
        if player.hp < player.max_hp:
            order.append(CardType.HEAL)
        for idx, card in enumerate(state.hand):
            if card.type is CardType.FINAL_STRIKE:
                dmg = card.value * permanents
                if permanents and (
                    dmg >= state.enemy_hp + state.enemy_block or len(_empty_slots(state)) <= 1
                ):
                    play_card(state, idx, slot, player, rng)
                    played = True
                    break
        if played:
            continue
        # System Restore pays with the field, so only when the banished pile
        # holds more than the field would lose.
        for idx, card in enumerate(state.hand):
            if card.type is CardType.REBOOT:
                back = sum(
                    1
                    for c in state.banished_pile
                    if c.type not in (CardType.RESTORE, CardType.REBOOT)
                )
                if back >= 2 and back > permanents:
                    play_card(state, idx, slot, player, rng)
                    played = True
                    break
        if played:
            continue
        for wanted in order:
            idx = next((i for i, c in enumerate(state.hand) if c.type is wanted), None)
            if idx is not None:
                play_card(state, idx, slot, player, rng)
                played = True
                break
        if not played:
            # Unplayed cards stay in hand, but the hand is capped at the
            # end of the turn, so a Firewall is played rather than
            # hoarded - one-shot cards are kept for when they matter.
            idx = next(
                (
                    i
                    for i, c in enumerate(state.hand)
                    if c.type is not CardType.FINAL_STRIKE and not c.exhaust
                ),
                None,
            )
            if idx is None:
                return
            play_card(state, idx, slot, player, rng)


BOTS: dict[str, Bot] = {"smart": smart_bot, "naive": naive_bot}

_RARITY_RANK = {Rarity.RARE: 3, Rarity.UNCOMMON: 2, Rarity.COMMON: 1, Rarity.STARTER: 0}


def pick_reward(offer: list[Card], bot_name: str, rng: random.Random) -> int:
    """Smart takes the rarest card on offer, naive a random one."""
    if bot_name == "naive":
        return rng.randrange(len(offer))
    best = max(_RARITY_RANK[c.rarity] for c in offer)
    return rng.choice([i for i, c in enumerate(offer) if _RARITY_RANK[c.rarity] == best])


# Below this share of max HP the smart bot heals at a rest site; above it, it
# upgrades a card instead.
REST_HEAL_BELOW = 0.65
# Which cards the smart bot upgrades first: what it plays most and what
# scales hardest. Everything else upgradable comes after, in deck order.
_UPGRADE_PRIORITY = ("Exploit", "Kernel Panic", "Overclock", "Firewall", "Encryption")


def rest_choice(player: PlayerState, heal_amount: int, bot_name: str) -> int | None:
    """Deck index to upgrade at a rest site, or None to heal.

    Naive always heals - the old rest site. Smart heals when hurt, else
    upgrades by _UPGRADE_PRIORITY.
    """
    if bot_name == "naive" or player.hp < player.max_hp * REST_HEAL_BELOW:
        return None
    upgradable = [i for i, c in enumerate(player.deck) if can_upgrade(c)]
    if not upgradable:
        return None

    def rank(i: int) -> int:
        name = player.deck[i].name
        return (
            _UPGRADE_PRIORITY.index(name) if name in _UPGRADE_PRIORITY else len(_UPGRADE_PRIORITY)
        )

    return min(upgradable, key=rank)


# --------------------------------------------------------------------------- simulation


@dataclass
class FightResult:
    tier: str
    won: bool
    turns: int
    hp_lost: int


def fight(
    player: PlayerState, enemy: Enemy, tier: str, bot: Bot, rng: random.Random, act: int = 1
) -> FightResult:
    hp_before = player.hp
    state, _ = start_combat(
        player.deck,
        enemy,
        rng,
        player.artifacts,
        boss=tier == "boss",
        boss_phases=boss_phases(act),
    )
    turns = 0
    while turns < MAX_AUTO_TURNS and state.enemy_hp > 0 and player.hp > 0:
        turns += 1
        bot(state, player, rng)
        if state.enemy_hp <= 0:
            break
        end_turn(state, player, rng)
    return FightResult(tier, state.enemy_hp <= 0, turns, max(hp_before - player.hp, 0))


def fresh_fights(cfg: SimConfig, bot: Bot, n: int, seed: int) -> dict[str, list[FightResult]]:
    """Each tier against a full-HP starter player - isolates enemy strength."""
    results: dict[str, list[FightResult]] = {t: [] for t in TIERS}
    for tier in TIERS:
        rng = random.Random(f"{seed}-{tier}")
        for _ in range(n):
            player = cfg.new_player()
            base = (
                rng.choice(ENEMY_POOL[tier]).model_copy(deep=True)
                if cfg.pool
                else random_enemy(cfg.budgets[tier], tier, rng)
            )
            enemy = escalate(base, _TIER_FLOOR[tier], NUM_FLOORS)
            results[tier].append(fight(player, enemy, tier, bot, rng))
    return results


@dataclass
class RunResult:
    won: bool
    floor_reached: int
    fights: list[FightResult]
    act_reached: int = 1


def simulate_run(cfg: SimConfig, bot: Bot, seed: int, bot_name: str = "smart") -> RunResult:
    """A full run on a real generated map, picking a random path forward.

    Both bots pick artifacts at random - there's no obvious "best" one to
    hard-code, and a random pick keeps the numbers an average over all of them.
    """
    rng = random.Random(seed)
    act = 1
    nodes = generate_map(seed)
    player = cfg.new_player()
    node = nodes["0-0"]
    fights: list[FightResult] = []
    steps = 0
    if cfg.rewards:  # mirrors engine.new_run's starting card pick
        offer = roll_card_reward(random.Random(f"{seed}-start-cards"), weights=START_CARD_WEIGHTS)
        player.deck.append(reward_card(offer[pick_reward(offer, bot_name, rng)], player.deck))

    while True:
        if cfg.artifacts and steps % ARTIFACT_EVERY_STEPS == 0:
            offer = roll_artifact_offer(rng, player.artifacts)
            if offer:
                gain_artifact(player, rng.choice(offer))
        if node.type in (NodeType.COMBAT, NodeType.ELITE, NodeType.BOSS):
            tier = tier_for(node.floor, node.type, act)
            if cfg.pool:
                base = pick_enemy(
                    floor=node.floor,
                    num_floors=NUM_FLOORS,
                    elite=node.type is NodeType.ELITE,
                    boss=node.type is NodeType.BOSS,
                    rng=rng,
                    act=act,
                )
            else:
                base = random_enemy(cfg.budgets[tier], tier, rng)
            enemy = escalate(base, node.floor, NUM_FLOORS, act)
            result = fight(player, enemy, tier, bot, rng, act)
            fights.append(result)
            if not result.won:
                return RunResult(False, node.floor, fights, act)
            if node.type is NodeType.BOSS and act >= NUM_ACTS:
                return RunResult(True, node.floor, fights, act)
            heal(player, total(player.artifacts, "heal_after_combat"))
            if cfg.rewards:
                offer = roll_card_reward(rng, elite=node.type is not NodeType.COMBAT)
                pick = offer[pick_reward(offer, bot_name, rng)]
                player.deck.append(reward_card(pick, player.deck))
            if node.type is NodeType.BOSS:
                # mirrors engine.advance_act - the new act starts on its camp
                act += 1
                nodes = generate_map(seed, act)
                node = nodes["0-0"]
                heal(player, player.max_hp * ACT_HEAL_PERCENT // 100)
        elif node.type is NodeType.REST:
            amount = REST_HEAL + total(player.artifacts, "rest_heal")
            index = rest_choice(player, amount, bot_name) if cfg.rest_upgrades else None
            if index is None:
                heal(player, amount)
            else:
                player.deck[index] = upgrade_card(player.deck[index])
        elif node.type is NodeType.EVENT:
            rng.choice(random_event(rng).options).effect(player, rng)
            if player.hp <= 0:
                return RunResult(False, node.floor, fights, act)
        node = nodes[rng.choice(node.connections)]
        steps += 1


# --------------------------------------------------------------------------- threat calibration

# Power ranges random move sets are drawn from - wider than anything sensible,
# so the fit also covers the odd move sets an LLM might come up with.
_POWER_RANGES = {
    MoveKind.ATTACK: (60, 150),
    MoveKind.DEFEND: (50, 150),
    MoveKind.BARRAGE: (15, 50),
    MoveKind.CHARGE: (100, 220),
    MoveKind.PURGE: (30, 90),
}
# Search grid for calibrate_threat; `scale` is solved for, not searched.
_THREAT_GRID = {
    "player_damage": (16.0, 20.0, 24.0, 28.0, 32.0, 40.0, 50.0),
    "armor": (0.0, 0.5, 1.0, 1.5),
    "player_block": (4.0, 5.0, 6.0, 7.0, 8.0),
    "purge_damage": (0.0, 3.0, 6.0, 9.0),
}
# Calibration fights give the player this much HP, so a fight's damage is
# never cut short by the player dying - what is measured is the enemy's
# full damage output.
_CALIBRATION_HP = 1000


def random_move_set(rng: random.Random) -> list[EnemyMove]:
    """1-4 random moves with random weights and powers, at least one attack or barrage."""
    always = EnemyMove(kind=rng.choice([MoveKind.ATTACK, MoveKind.BARRAGE]))
    moves = [always] + [
        EnemyMove(kind=rng.choice(list(MoveKind))) for _ in range(rng.randint(0, 3))
    ]
    for move in moves:
        move.weight = rng.randint(1, 5)
        move.power = rng.randint(*_POWER_RANGES[move.kind])
        if move.kind is MoveKind.BARRAGE:
            move.hits = rng.randint(2, 4)
    rng.shuffle(moves)
    return moves


def mean_damage_taken(enemy: Enemy, bot: Bot, fights: int, seed: int | str) -> float:
    """Average HP a fresh starter player loses to `enemy` - with HP to spare,
    so the enemy's full output counts."""
    rng = random.Random(seed)
    cfg = SimConfig(player_hp=_CALIBRATION_HP)
    return statistics.mean(
        fight(cfg.new_player(), enemy, "mid", bot, rng).hp_lost for _ in range(fights)
    )


def threat_samples(bot: Bot, enemies: int, fights: int, seed: int) -> list[tuple[Enemy, float]]:
    """Random enemies (one in seven with the default move set) and the damage they dealt."""
    rng = random.Random(f"{seed}-threat")
    samples = []
    for i in range(enemies):
        moves = {} if rng.random() < 1 / 7 else {"moves": random_move_set(rng)}
        enemy = Enemy(
            id=f"calib-{i}",
            name="calib",
            hp=rng.randint(30, 110),
            attack=rng.randint(6, 15),
            attack_name="Hit",
            **moves,
        )
        samples.append((enemy, mean_damage_taken(enemy, bot, fights, f"{seed}-{i}")))
    return samples


@dataclass
class ThreatFit:
    model: ThreatModel
    r2: float  # share of the variance in damage taken that threat explains
    median_error: float  # typical relative error of a single prediction


def evaluate_threat(model: ThreatModel, samples: list[tuple[Enemy, float]]) -> ThreatFit:
    predicted = [threat(e, model) for e, _ in samples]
    actual = [y for _, y in samples]
    mean = statistics.mean(actual)
    residual = sum((p - y) ** 2 for p, y in zip(predicted, actual, strict=True))
    spread = sum((y - mean) ** 2 for y in actual)
    errors = [abs(p - y) / max(y, 1.0) for p, y in zip(predicted, actual, strict=True)]
    return ThreatFit(model, 1 - residual / spread, statistics.median(errors))


def calibrate_threat(samples: list[tuple[Enemy, float]]) -> ThreatFit:
    """Grid-search ThreatModel on `samples`; for each grid point the scale is
    the least-squares fit, so threat comes out in HP actually taken."""
    best: ThreatFit | None = None
    actual = [y for _, y in samples]
    for player_damage in _THREAT_GRID["player_damage"]:
        for armor in _THREAT_GRID["armor"]:
            for player_block in _THREAT_GRID["player_block"]:
                for purge_damage in _THREAT_GRID["purge_damage"]:
                    raw = ThreatModel(player_damage, armor, player_block, purge_damage)
                    xs = [threat(e, raw) for e, _ in samples]
                    xx = sum(x * x for x in xs)
                    scale = sum(x * y for x, y in zip(xs, actual, strict=True)) / xx if xx else 1.0
                    fit = evaluate_threat(
                        ThreatModel(player_damage, armor, player_block, purge_damage, scale),
                        samples,
                    )
                    if best is None or fit.r2 > best.r2:
                        best = fit
    assert best is not None
    return best


def print_threat_calibration(bot: Bot, enemies: int, fights: int, seed: int) -> None:
    samples = threat_samples(bot, enemies, fights, seed)
    # Fit on two thirds, judge on the rest - a fit is only as good as its
    # predictions for move sets it has not seen.
    cut = len(samples) * 2 // 3
    fit = calibrate_threat(samples[:cut])
    held_out = evaluate_threat(fit.model, samples[cut:])
    current = evaluate_threat(DEFAULT_MODEL, samples[cut:])
    m = fit.model
    print(f"\n{enemies} zufällige Movesets x {fights} Kämpfe, Fit auf {cut}, Test auf dem Rest")
    print(
        f"Gefittet: player_damage={m.player_damage} armor={m.armor} "
        f"player_block={m.player_block} purge_damage={m.purge_damage} scale={m.scale:.3f}"
    )
    print(f"  Fit-Daten:  R² {fit.r2:.3f}, Median-Fehler {fit.median_error:.1%}")
    print(f"  Test-Daten: R² {held_out.r2:.3f}, Median-Fehler {held_out.median_error:.1%}")
    print(
        f"Aktuelles DEFAULT_MODEL auf den Test-Daten: R² {current.r2:.3f}, "
        f"Median-Fehler {current.median_error:.1%}"
    )


# --------------------------------------------------------------------------- report


@dataclass
class TierStats:
    n: int
    win_rate: float
    turns: float
    hp_lost: float

    @classmethod
    def of(cls, results: list[FightResult]) -> TierStats | None:
        if not results:
            return None
        won = [r for r in results if r.won]
        return cls(
            n=len(results),
            win_rate=len(won) / len(results),
            turns=statistics.mean(r.turns for r in results),
            hp_lost=statistics.mean(r.hp_lost for r in results),
        )


@dataclass
class Report:
    name: str
    fresh: dict[str, TierStats | None]
    in_run: dict[str, TierStats | None]
    run_win_rate: float
    # keyed by (act, floor)
    death_floors: dict[tuple[int, int], int]


def build_report(
    cfg: SimConfig, bot: Bot, fights: int, runs: int, seed: int, bot_name: str = "smart"
) -> Report:
    fresh = {t: TierStats.of(r) for t, r in fresh_fights(cfg, bot, fights, seed).items()}
    run_results = [simulate_run(cfg, bot, seed * 100_003 + i, bot_name) for i in range(runs)]
    in_run = {
        t: TierStats.of([f for r in run_results for f in r.fights if f.tier == t]) for t in TIERS
    }
    death_floors: dict[tuple[int, int], int] = {}
    for r in run_results:
        if not r.won:
            key = (r.act_reached, r.floor_reached)
            death_floors[key] = death_floors.get(key, 0) + 1
    return Report(
        name=cfg.name,
        fresh=fresh,
        in_run=in_run,
        run_win_rate=sum(r.won for r in run_results) / max(runs, 1),
        death_floors=dict(sorted(death_floors.items())),
    )


def _fmt(s: TierStats | None) -> str:
    if s is None:
        return f"{'-':>7} {'-':>6} {'-':>8}"
    return f"{s.win_rate:>6.0%} {s.turns:>6.1f} {s.hp_lost:>8.1f}"


def print_reports(reports: list[Report], cfgs: list[SimConfig]) -> None:
    head = f"{'':<8}" + "".join(f"| {r.name:<22}" for r in reports)
    sub = f"{'Stufe':<8}" + "| Sieg  Züge  HP-Verl. " * len(reports)
    for title, attr in (("Einzelkampf mit vollen HP", "fresh"), ("Im Run", "in_run")):
        print(f"\n{title}")
        print(head)
        print(sub)
        for tier in TIERS:
            print(f"{tier:<8}" + "".join(f"| {_fmt(getattr(r, attr)[tier])} " for r in reports))
    print("\nRun-Siegquote: " + "  ".join(f"{r.name}: {r.run_win_rate:.0%}" for r in reports))
    for r in reports:
        if r.death_floors:
            floors = ", ".join(f"Akt {a} Etage {f}: {n}" for (a, f), n in r.death_floors.items())
            print(f"Tode ({r.name}): {floors}")
    for cfg in cfgs:
        b = cfg.budgets
        budgets = "  ".join(
            f"{t} {b[t].min_hp}-{b[t].max_hp}HP/{b[t].min_attack}-{b[t].max_attack}ATK"
            for t in TIERS
        )
        print(f"Budgets ({cfg.name}): {budgets}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--fights", type=int, default=2000, help="Einzelkämpfe pro Stufe")
    parser.add_argument("--runs", type=int, default=2000, help="komplette Runs")
    parser.add_argument("--bot", choices=sorted(BOTS), default="smart")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--variant", type=Path, help="statt der aktuellen Werte diese Variante")
    parser.add_argument(
        "--no-rewards",
        action="store_true",
        help="Runs ohne Kartenbelohnung nach Kämpfen (nur Starterdeck)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        action="append",
        default=[],
        help="Variante(n) neben die aktuellen Werte stellen (mehrfach möglich)",
    )
    parser.add_argument("--no-artifacts", action="store_true", help="Runs ohne Artefakte")
    parser.add_argument(
        "--pool",
        action="store_true",
        help="Gegner aus dem statischen Pool (enemies.py) statt zufällig in den Budgets",
    )
    parser.add_argument(
        "--calibrate-threat",
        action="store_true",
        help="statt des Reports die Parameter von threat.py fitten",
    )
    parser.add_argument("--threat-enemies", type=int, default=600, help="Movesets fürs Fitten")
    parser.add_argument("--threat-fights", type=int, default=100, help="Kämpfe pro Moveset")
    args = parser.parse_args(argv)

    if args.calibrate_threat:
        print_threat_calibration(BOTS[args.bot], args.threat_enemies, args.threat_fights, args.seed)
        return

    base = load_variant(args.variant) if args.variant else SimConfig()
    if args.no_rewards:
        base.rewards = False
    if args.no_artifacts:
        base.artifacts = False
    cfgs = [base, *(load_variant(p) for p in args.compare)]
    for cfg in cfgs:
        cfg.pool = args.pool
    bot = BOTS[args.bot]
    print(f"Bot: {args.bot}, {args.fights} Kämpfe/Stufe, {args.runs} Runs, Seed {args.seed}")
    reports = [build_report(c, bot, args.fights, args.runs, args.seed, args.bot) for c in cfgs]
    print_reports(reports, cfgs)


if __name__ == "__main__":
    main()
