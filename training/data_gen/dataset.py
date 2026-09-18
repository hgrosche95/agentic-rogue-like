"""Builds the final train/val/test JSONL files and a data card from
raw_results.jsonl - the append-as-you-go log iter_examples() writes to.

Works directly off the raw JSON records (not GeneratedExample objects) on
purpose: raw_results.jsonl is the durable source of truth (survives a killed
process), so this can rebuild the dataset from whatever's on disk at any
point, including a partial run, without needing the Python objects that
produced it.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dataset"
RAW_RESULTS_PATH = DATASET_DIR / "raw_results.jsonl"


def read_raw_records(path: Path = RAW_RESULTS_PATH) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def to_training_record(record: dict) -> dict:
    """"messages" is what TRL's SFTTrainer expects; tier/setting ride along
    for later analysis and are ignored by training itself."""
    return {
        "messages": [
            {"role": "user", "content": record["prompt"]},
            {"role": "assistant", "content": json.dumps(record["proposal"])},
        ],
        "tier": record["tier"],
        "setting": record["setting"],
    }


def write_split_files(records: list[dict]) -> dict[str, Path]:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    accepted = [r for r in records if r["status"] == "accepted"]
    by_split: dict[str, list[dict]] = defaultdict(list)
    for record in accepted:
        by_split[record["split"]].append(record)

    paths: dict[str, Path] = {}
    for split, split_records in by_split.items():
        path = DATASET_DIR / f"{split}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for record in split_records:
                fh.write(json.dumps(to_training_record(record)) + "\n")
        paths[split] = path
    return paths


def _diversity_row(tier: str, records: list[dict]) -> str:
    n = len(records)
    names = [r["proposal"]["name"] for r in records]
    attack_names = [r["proposal"]["attack_name"] for r in records]
    hps = [r["proposal"]["hp"] for r in records]
    attacks = [r["proposal"]["attack"] for r in records]
    unique_names = len(set(names)) / n
    unique_attacks = len(set(attack_names)) / n
    hp_stdev = statistics.pstdev(hps) if len(hps) > 1 else 0.0
    attack_stdev = statistics.pstdev(attacks) if len(attacks) > 1 else 0.0
    return (
        f"| {tier} | {n} | {unique_names:.2f} | {unique_attacks:.2f} "
        f"| {hp_stdev:.2f} | {attack_stdev:.2f} |"
    )


def write_data_card(records: list[dict]) -> Path:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    accepted = [r for r in records if r["status"] == "accepted"]
    rejected = [r for r in records if r["status"] == "rejected"]
    total = len(records)

    by_split: dict[str, list[dict]] = defaultdict(list)
    for record in accepted:
        by_split[record["split"]].append(record)

    by_tier: dict[str, list[dict]] = defaultdict(list)
    for record in accepted:
        by_tier[record["tier"]].append(record)

    lines = [
        "# Training data card",
        "",
        f"Generated {total} candidates, kept {len(accepted)} "
        f"({(len(accepted) / total if total else 0):.1%}) after `validate_proposal` "
        f"filtering, rejected {len(rejected)}.",
        "",
        "## Splits",
        "",
    ]
    for split in ("train", "val", "test"):
        lines.append(f"- **{split}**: {len(by_split.get(split, []))} examples")

    lines += [
        "",
        "## Diversity by tier (accepted examples only)",
        "",
        "| Tier | N | Unique names | Unique attacks | HP stdev | Attack stdev |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for tier, tier_records in by_tier.items():
        lines.append(_diversity_row(tier, tier_records))

    if rejected:
        lines += ["", "## Rejected samples (first 10)", ""]
        for r in rejected[:10]:
            lines.append(f"- [{r['tier']}/{r['setting']}] {r['reason']}")

    path = DATASET_DIR / "data_card.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build_dataset_from_raw() -> tuple[dict[str, Path], Path]:
    """Rebuild train/val/test.jsonl + the data card from whatever's currently
    in raw_results.jsonl - safe to call on a partial (interrupted) run."""
    records = read_raw_records()
    split_paths = write_split_files(records)
    card_path = write_data_card(records)
    return split_paths, card_path
