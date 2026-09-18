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

from .harness import CallResult
from .metrics import Report, TierMetrics

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


def save_report(report: Report, raw_results: list[CallResult]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    base = REPORTS_DIR / report.label

    base.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    render_csv(report, base.with_suffix(".csv"))
    base.with_suffix(".json").write_text(
        json.dumps([_result_to_jsonable(r) for r in raw_results], indent=2), encoding="utf-8"
    )
    return base.with_suffix(".md")
