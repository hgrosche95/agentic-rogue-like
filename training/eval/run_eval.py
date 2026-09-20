"""CLI entry point: run the harness against a model and save a report.

    uv run python -m eval.run_eval --label groq-baseline --repeats 5

With no --label, defaults to the Groq baseline (encounter_agent's real
_model, unpatched) - this is what step 6 will diff the fine-tuned run
against.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from .harness import measure_cost_samples, run_harness
from .metrics import compute_report
from .report import load_previous_results, save_report
from .testset import build_test_contexts

BASELINE_MODEL_NAME = "openai/gpt-oss-20b"
# Same .env the main app's cli.py/api.py load - one repo-wide GROQ_API_KEY.
_ROOT_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def main() -> None:
    load_dotenv(_ROOT_ENV_FILE)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="groq-baseline")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    previous_results = load_previous_results(args.label)
    if previous_results:
        print(
            f"Found {len(previous_results)} previous results for '{args.label}' - "
            f"merging instead of overwriting.",
            file=sys.stderr,
        )

    contexts = build_test_contexts(repeats=args.repeats)
    print(
        f"Running {len(contexts)} calls against {BASELINE_MODEL_NAME} ({args.label})...",
        file=sys.stderr,
    )
    results = run_harness(contexts)
    combined_results = previous_results + results

    print("Measuring token usage/cost (one probe per tier x setting)...", file=sys.stderr)
    cost_samples = measure_cost_samples(contexts)

    report = compute_report(args.label, BASELINE_MODEL_NAME, combined_results, cost_samples)
    path = save_report(report, combined_results)
    print(
        f"Report written to {path} (.md/.csv/.json) - {len(combined_results)} results total",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
