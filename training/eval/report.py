"""Renders a Report to files under training/artifacts/eval_reports/ - never
just a console print, so a run's numbers survive past the terminal scrollback
and step 6 (baseline vs fine-tune) can diff the raw JSON instead of re-running
the baseline.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, fields
from pathlib import Path

from agentic_rogue_like.agent.encounter_schema import EnemyBudget, EnemyProposal

from .harness import CallResult
from .metrics import Report, TierMetrics
from .testset import EvalContext

REPORTS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "eval_reports"

_COLUMN_LABELS: dict[str, str] = {
    "tier": "Tier",
    "n": "N",
    "validity_rate": "Validity",
    "budget_compliance_first_attempt": "Budget OK (1st try)",
    "budget_compliance_final": "Budget OK (final)",
    "avg_attempts": "Avg attempts",
    "unique_name_ratio": "Unique names",
    "unique_attack_name_ratio": "Unique attacks",
    "hp_stdev": "HP stdev",
    "attack_stdev": "Attack stdev",
    "latency_p50_seconds": "Latency p50 (s)",
    "latency_p95_seconds": "Latency p95 (s)",
    "avg_input_tokens": "Avg input tok",
    "avg_output_tokens": "Avg output tok",
    "cost_per_call_usd": "$/call",
}


def _fmt(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if math.isnan(value):
            return "-"
        return f"{value:.4f}" if abs(value) < 1 else f"{value:.2f}"
    return str(value)


def _rows(report: Report) -> list[TierMetrics]:
    return [*report.by_tier, report.overall]


def render_markdown(report: Report) -> str:
    columns = [f.name for f in fields(TierMetrics)]
    header = "| " + " | ".join(_COLUMN_LABELS[c] for c in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [f"# Eval report: {report.label} ({report.model_name})", "", header, separator]
    for row in _rows(report):
        data = asdict(row)
        lines.append("| " + " | ".join(_fmt(data[c]) for c in columns) + " |")
    cost_per_call = report.overall.cost_per_call_usd
    if cost_per_call is not None:
        lines.append("")
        lines.append(f"Overall cost per 1000 calls: **${cost_per_call * 1000:.2f}**")
    else:
        lines.append("")
        lines.append("No known $/token price for this model - cost left blank rather than guessed.")
    return "\n".join(lines) + "\n"


def render_csv(report: Report, out_path: Path) -> None:
    columns = [f.name for f in fields(TierMetrics)]
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in _rows(report):
            data = asdict(row)
            writer.writerow([data[c] for c in columns])


def _result_to_jsonable(result: CallResult) -> dict:
    # context.budget and proposal are pydantic models (the runtime schema),
    # not dataclasses - asdict() only recurses into dataclass fields, so
    # those two need their own model_dump().
    data = asdict(result)
    data["context"] = asdict(result.context)
    data["context"]["budget"] = result.context.budget.model_dump()
    data["proposal"] = result.proposal.model_dump() if result.proposal is not None else None
    return data


def _jsonable_to_result(data: dict) -> CallResult:
    """Inverse of _result_to_jsonable - lets a rerun merge onto a previous
    report's raw results instead of a same-label run silently overwriting it
    (see load_previous_results)."""
    context_data = data["context"]
    context = EvalContext(
        tier=context_data["tier"],
        floor=context_data["floor"],
        num_floors=context_data["num_floors"],
        elite=context_data["elite"],
        boss=context_data["boss"],
        setting=context_data["setting"],
        budget=EnemyBudget(**context_data["budget"]),
    )
    proposal = EnemyProposal(**data["proposal"]) if data["proposal"] is not None else None
    return CallResult(
        context=context,
        status=data["status"],
        attempts_used=data["attempts_used"],
        first_attempt_violation=data["first_attempt_violation"],
        latency_seconds=data["latency_seconds"],
        proposal=proposal,
        error_message=data["error_message"],
    )


def load_previous_results(label: str) -> list[CallResult]:
    """Empty list if this label has no report yet - a first run for a label
    isn't a merge, just a save."""
    path = _report_path(label, ".json")
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [_jsonable_to_result(d) for d in data]


def _report_path(label: str, extension: str) -> Path:
    # Not Path.with_suffix(): a label like "temp0.2" would have its ".2"
    # mistaken for a file extension and silently truncated.
    return REPORTS_DIR / f"{label}{extension}"


def save_report(report: Report, raw_results: list[CallResult]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    _report_path(report.label, ".md").write_text(render_markdown(report), encoding="utf-8")
    render_csv(report, _report_path(report.label, ".csv"))
    _report_path(report.label, ".json").write_text(
        json.dumps([_result_to_jsonable(r) for r in raw_results], indent=2), encoding="utf-8"
    )
    return _report_path(report.label, ".md")
