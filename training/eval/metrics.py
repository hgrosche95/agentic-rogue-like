"""Turns raw CallResult/CostSample lists into the four required metrics:
structural validity, budget compliance, diversity, cost/latency - per tier
and overall, so a report can show where a model struggles instead of
averaging the problem away.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

from .costs import estimate_cost_usd
from .harness import CallResult, CostSample


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
    )


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
