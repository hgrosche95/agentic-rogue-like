"""Turns raw CallResult/CostSample lists into the four required metrics:
structural validity, budget compliance, diversity, cost/latency - per tier
and overall, so a report can show where a model struggles instead of
averaging the problem away.

On top, for every run: why first attempts get rejected and how often the
retry fixes them. And for move set runs (run_eval --moves): what the move
sets look like - how many moves, which kinds, how varied, and where in the
threat budget they land.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from agentic_rogue_like.agent.encounter_schema import MovesetProposal, proposal_moves
from agentic_rogue_like.models import Enemy, MoveKind
from agentic_rogue_like.threat import threat

from .costs import estimate_cost_usd
from .harness import CallResult, CostSample

# Kinds whose use is worth counting - every move set has an attack or barrage.
_COUNTED_KINDS = (MoveKind.DEFEND, MoveKind.BARRAGE, MoveKind.CHARGE, MoveKind.PURGE)


@dataclass
class TierMetrics:
    tier: str
    n: int
    validity_rate: float
    budget_compliance_first_attempt: float
    budget_compliance_final: float
    avg_attempts: float
    unique_name_ratio: float | None
    unique_attack_name_ratio: float | None
    hp_stdev: float | None
    attack_stdev: float | None
    latency_p50_seconds: float
    latency_p95_seconds: float
    avg_input_tokens: float | None
    avg_output_tokens: float | None
    cost_per_call_usd: float | None
    # Share of non-error calls whose first attempt was rejected, by reason
    # (harness.violation_kind), and how many of those the retries fixed.
    first_violation_threat: float | None = None
    first_violation_invalid_moves: float | None = None
    first_violation_attack: float | None = None
    first_violation_hp: float | None = None
    retry_fix_rate: float | None = None
    # Move set runs only (None otherwise), over the accepted enemies.
    avg_moves: float | None = None
    uses_defend: float | None = None
    uses_barrage: float | None = None
    uses_charge: float | None = None
    uses_purge: float | None = None
    unique_move_name_ratio: float | None = None
    # Distinct combinations of move kinds - "everyone does attack + defend"
    # would score low here even with fresh names every time.
    unique_move_set_ratio: float | None = None
    # Where the threat lands in the tier's range: 0 = its floor, 1 = its cap.
    threat_position_mean: float | None = None
    # Share whose HP lies outside the plain HP range - i.e. that actually
    # trade HP against their move set instead of copying the plain range.
    hp_outside_plain_range: float | None = None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * pct
    lower, upper = math.floor(rank), math.ceil(rank)
    if lower == upper:
        return ordered[int(rank)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _tier_metrics(
    tier: str,
    results: list[CallResult],
    cost_samples: list[CostSample],
    model_name: str,
) -> TierMetrics:
    n = len(results)
    non_error = [r for r in results if r.status != "error"]
    ok = [r for r in results if r.status == "ok"]
    first_attempt_ok = [r for r in non_error if r.first_attempt_violation is False]

    names = [r.proposal.name for r in ok]
    attack_names = [r.proposal.attack_name for r in ok]
    hps = [r.proposal.hp for r in ok]
    attacks = [r.proposal.attack for r in ok]
    # Excludes "error" results: their latency includes our own rate-limit
    # backoff sleeps (see common.groq_backoff.call_with_backoff), not real
    # service time.
    latencies = [r.latency_seconds for r in non_error]

    avg_input = statistics.fmean(s.input_tokens for s in cost_samples) if cost_samples else None
    avg_output = statistics.fmean(s.output_tokens for s in cost_samples) if cost_samples else None
    cost_per_call = (
        estimate_cost_usd(model_name, avg_input, avg_output)
        if avg_input is not None and avg_output is not None
        else None
    )

    first_attempt_rate = len(first_attempt_ok) / len(non_error) if non_error else float("nan")
    violated = [r for r in non_error if r.first_attempt_violation]

    def violation_share(kind: str) -> float | None:
        if not non_error:
            return None
        return sum(r.first_violation_kind == kind for r in non_error) / len(non_error)

    avg_attempts = (
        statistics.fmean(r.attempts_used for r in non_error) if non_error else float("nan")
    )
    unique_names = len(set(names)) / len(names) if names else None
    unique_attacks = len(set(attack_names)) / len(attack_names) if attack_names else None

    return TierMetrics(
        tier=tier,
        n=n,
        validity_rate=len(non_error) / n if n else float("nan"),
        budget_compliance_first_attempt=first_attempt_rate,
        budget_compliance_final=len(ok) / n if n else float("nan"),
        avg_attempts=avg_attempts,
        unique_name_ratio=unique_names,
        unique_attack_name_ratio=unique_attacks,
        hp_stdev=statistics.pstdev(hps) if len(hps) > 1 else None,
        attack_stdev=statistics.pstdev(attacks) if len(attacks) > 1 else None,
        latency_p50_seconds=_percentile(latencies, 0.50),
        latency_p95_seconds=_percentile(latencies, 0.95),
        avg_input_tokens=avg_input,
        avg_output_tokens=avg_output,
        cost_per_call_usd=cost_per_call,
        first_violation_threat=violation_share("threat"),
        first_violation_invalid_moves=violation_share("invalid_moves"),
        first_violation_attack=violation_share("attack"),
        first_violation_hp=violation_share("hp"),
        retry_fix_rate=(
            sum(r.status == "ok" for r in violated) / len(violated) if violated else None
        ),
        **_moveset_metrics(ok),
    )


def _moveset_metrics(ok: list[CallResult]) -> dict[str, float | None]:
    """The move set columns, over accepted move set proposals - all None when
    there are none (a plain run, or a tier like boss that never gets moves)."""
    accepted = [r for r in ok if isinstance(r.proposal, MovesetProposal)]
    if not accepted:
        return {}
    move_sets = [proposal_moves(r.proposal) for r in accepted]
    kinds = [{m.kind for m in moves} for moves in move_sets]
    names = [m.name for moves in move_sets for m in moves]
    signatures = [tuple(sorted(m.kind.value for m in moves)) for moves in move_sets]

    positions, outside = [], 0
    for result, moves in zip(accepted, move_sets, strict=True):
        p, budget = result.proposal, result.context.budget
        enemy = Enemy(id="", name="", hp=p.hp, attack=p.attack, attack_name="", moves=moves)
        low, high = budget.threat_range()
        positions.append((threat(enemy) - low) / (high - low))
        outside += not (budget.min_hp <= p.hp <= budget.max_hp)

    n = len(accepted)
    uses = {kind: sum(kind in k for k in kinds) / n for kind in _COUNTED_KINDS}
    return {
        "avg_moves": statistics.fmean(len(moves) for moves in move_sets),
        "uses_defend": uses[MoveKind.DEFEND],
        "uses_barrage": uses[MoveKind.BARRAGE],
        "uses_charge": uses[MoveKind.CHARGE],
        "uses_purge": uses[MoveKind.PURGE],
        "unique_move_name_ratio": len(set(names)) / len(names),
        "unique_move_set_ratio": len(set(signatures)) / n,
        "threat_position_mean": statistics.fmean(positions),
        "hp_outside_plain_range": outside / n,
    }


@dataclass
class Report:
    label: str
    model_name: str
    by_tier: list[TierMetrics]
    overall: TierMetrics


def compute_report(
    label: str,
    model_name: str,
    results: list[CallResult],
    cost_samples: list[CostSample],
) -> Report:
    tiers: list[str] = []
    for r in results:
        if r.context.tier not in tiers:
            tiers.append(r.context.tier)
    by_tier = [
        _tier_metrics(
            tier,
            [r for r in results if r.context.tier == tier],
            [s for s in cost_samples if s.tier == tier],
            model_name,
        )
        for tier in tiers
    ]
    overall = _tier_metrics("overall", results, cost_samples, model_name)
    return Report(label=label, model_name=model_name, by_tier=by_tier, overall=overall)
