"""CLI entry point: run the harness against a model and save a report.

    uv run python -m eval.run_eval --model groq --repeats 15
    uv run python -m eval.run_eval --model ollama --settings presets --repeats 15
    uv run python -m eval.run_eval --model ollama --settings heldout --repeats 38

--settings presets is what the Groq baseline was measured on. For the
fine-tuned model those settings all sit in the training split, so "presets"
scores prompts it saw verbatim; "heldout" (the test-split settings it never
trained on) is the honest generalization number. Each combination gets its
own report label so the two never get mixed.
"""

from __future__ import annotations

import argparse
import sys
from functools import partial
from pathlib import Path

import httpx
from agentic_rogue_like.models import SETTING_PRESETS
from dotenv import load_dotenv

from data_gen.contexts import TEST_SETTINGS
from serving.ollama_model import DEFAULT_MODEL_NAME, OLLAMA_BASE_URL, OllamaChatModel

from .harness import measure_cost_samples, run_harness
from .metrics import compute_report
from .report import load_previous_results, save_report
from .testset import build_test_contexts

GROQ_MODEL_NAME = "openai/gpt-oss-20b"
# Same .env the main app's cli.py/api.py load - one repo-wide GROQ_API_KEY.
_ROOT_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def _default_label(model: str, settings: str) -> str:
    if model == "groq":
        return "groq-baseline" if settings == "presets" else "groq-heldout"
    return "finetuned-seen" if settings == "presets" else "finetuned-heldout"


def _warm_up_ollama(model_name: str) -> None:
    """Load the model into memory before timing anything: Ollama's first
    request pays a one-off ~3s load, which would otherwise land in the first
    call's latency and skew p95 for what's really a cold-start artifact."""
    print(f"Warming up {model_name}...", file=sys.stderr)
    httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json={"model": model_name}, timeout=180)


def main() -> None:
    load_dotenv(_ROOT_ENV_FILE)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=["groq", "ollama"], default="groq")
    parser.add_argument("--settings", choices=["presets", "heldout"], default="presets")
    parser.add_argument("--label", default=None)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--ollama-model",
        default=DEFAULT_MODEL_NAME,
        help="which imported Ollama model to evaluate, e.g. a different quantization",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="override the Ollama model's own temperature for this run",
    )
    parser.add_argument(
        "--tiers",
        nargs="+",
        choices=["early", "mid", "elite", "boss"],
        default=None,
        help="only run these budget tiers (results still merge into the label's report)",
    )
    parser.add_argument(
        "--constrained",
        action="store_true",
        help="schema-constrained decoding via Ollama's `format` parameter",
    )
    args = parser.parse_args()

    label = args.label or _default_label(args.model, args.settings)
    model_name = GROQ_MODEL_NAME if args.model == "groq" else args.ollama_model
    model_factory = None
    if args.model == "ollama":
        model_factory = partial(
            OllamaChatModel, args.ollama_model, args.temperature, args.constrained
        )
    settings = TEST_SETTINGS if args.settings == "heldout" else SETTING_PRESETS

    previous_results = load_previous_results(label)
    if previous_results:
        print(
            f"Found {len(previous_results)} previous results for '{label}' - "
            f"merging instead of overwriting.",
            file=sys.stderr,
        )

    contexts = build_test_contexts(
        repeats=args.repeats,
        settings=settings,
        tiers=tuple(args.tiers) if args.tiers else None,
    )
    print(f"Running {len(contexts)} calls against {model_name} ({label})...", file=sys.stderr)

    if args.model == "ollama":
        _warm_up_ollama(args.ollama_model)
    results = run_harness(contexts, model_factory=model_factory)
    combined_results = previous_results + results

    # The cost probe exists to turn Groq's token counts into dollars. A local
    # model has no per-call price, and its probe would crash the run whenever
    # the model happens to return an invalid reply - so skip it there.
    cost_samples = []
    if args.model == "groq":
        print("Measuring token usage/cost (one probe per tier x setting)...", file=sys.stderr)
        cost_samples = measure_cost_samples(contexts)

    report = compute_report(label, model_name, combined_results, cost_samples)
    path = save_report(report, combined_results)
    print(
        f"Report written to {path} (.md/.csv/.json) - {len(combined_results)} results total",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
