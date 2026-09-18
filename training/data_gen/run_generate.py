"""CLI entry point: generate the fine-tuning dataset.

    uv run python -m data_gen.run_generate --repeats 5

Resumable: every result is appended to raw_results.jsonl immediately, and a
rerun skips (tier, setting, repeat_index) combinations already present there
- so killing this mid-run (Ctrl+C, shutdown, a crash) only ever costs the one
call in flight, not the whole run.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from common.groq_backoff import RateLimitTooLong

from .contexts import build_data_contexts
from .dataset import RAW_RESULTS_PATH, build_dataset_from_raw, read_raw_records
from .generate import iter_examples

_ROOT_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
_PROGRESS_EVERY = 10


def _already_done() -> set[tuple[str, str, int]]:
    return {(r["tier"], r["setting"], r["repeat_index"]) for r in read_raw_records()}


def main() -> None:
    load_dotenv(_ROOT_ENV_FILE)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    all_contexts = build_data_contexts(repeats=args.repeats)
    done = _already_done()
    remaining = [c for c in all_contexts if (c.tier, c.setting, c.repeat_index) not in done]

    if done:
        print(f"Resuming: {len(done)} already done, {len(remaining)} remaining.", file=sys.stderr)
    else:
        print(f"Generating {len(remaining)} candidates...", file=sys.stderr)

    RAW_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    stopped_early = False
    with RAW_RESULTS_PATH.open("a", encoding="utf-8") as fh:
        try:
            for i, record in enumerate(iter_examples(remaining), start=1):
                fh.write(json.dumps(dataclasses.asdict(record)) + "\n")
                fh.flush()
                if i % _PROGRESS_EVERY == 0 or i == len(remaining):
                    print(f"  {i}/{len(remaining)} done", file=sys.stderr)
        except RateLimitTooLong as exc:
            stopped_early = True
            print(f"Stopping early - quota exhausted: {exc}", file=sys.stderr)
            print("Progress so far is saved; rerun this command later to resume.", file=sys.stderr)

    paths, card_path = build_dataset_from_raw()
    if stopped_early:
        print("(partial dataset - rerun later to fill in the rest)", file=sys.stderr)
    for split, path in sorted(paths.items()):
        print(f"{split}: {path}", file=sys.stderr)
    print(f"Data card: {card_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
