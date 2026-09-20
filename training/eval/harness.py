"""Runs the real encounter-agent graph against a set of EvalContexts and
records what actually happened - not a reimplementation of its logic.

The one exception is cost: generate_enemy() calls with_structured_output()
without include_raw, which throws away token usage. measure_cost_samples()
makes a second, separate call per (tier, setting) with include_raw=True,
reusing _build_prompt() so the prompt text is identical to what production
sends - only the LangChain call shape differs, just enough to read usage.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.encounter_schema import EnemyProposal

from common.groq_backoff import RateLimitTooLong, call_with_backoff

from .testset import EvalContext

ModelFactory = Callable[[], Any]


@dataclass
class CallResult:
    context: EvalContext
    status: str  # "ok" | "budget_exhausted" | "error"
    attempts_used: int
    first_attempt_violation: bool | None
    latency_seconds: float
    proposal: EnemyProposal | None
    error_message: str | None


@dataclass
class CostSample:
    tier: str
    setting: str
    input_tokens: int
    output_tokens: int


def _initial_state(context: EvalContext) -> encounter_agent.EncounterState:
    return {
        "budget": context.budget,
        "setting": context.setting,
        "attempt": 0,
        "last_error": None,
        "proposal": None,
    }


def _run_one(context: EvalContext) -> CallResult:
    app = encounter_agent.build_graph()
    try:
        states, latency = call_with_backoff(
            lambda: list(app.stream(_initial_state(context), stream_mode="values"))
        )
    except RateLimitTooLong:
        # A near-exhausted quota isn't a model failure - let the caller stop
        # the run instead of miscounting it as an invalid response.
        raise
    except Exception as exc:  # noqa: BLE001 - deliberately broad, same boundary enemy_for_node uses
        return CallResult(
            context=context,
            status="error",
            attempts_used=0,
            first_attempt_violation=None,
            latency_seconds=float("nan"),
            proposal=None,
            error_message=str(exc),
        )

    final_state = states[-1]
    ok = final_state["last_error"] is None
    return CallResult(
        context=context,
        status="ok" if ok else "budget_exhausted",
        attempts_used=final_state["attempt"],
        first_attempt_violation=states[1]["last_error"] is not None,
        latency_seconds=latency,
        proposal=final_state["proposal"] if ok else None,
        error_message=None if ok else final_state["last_error"],
    )


def _run_all(contexts: list[EvalContext]) -> list[CallResult]:
    results: list[CallResult] = []
    for context in contexts:
        try:
            results.append(_run_one(context))
        except RateLimitTooLong as exc:
            print(
                f"Stopping early - quota exhausted after {len(results)}/{len(contexts)} "
                f"calls: {exc}",
                file=sys.stderr,
            )
            break
    return results


def run_harness(
    contexts: list[EvalContext], model_factory: ModelFactory | None = None
) -> list[CallResult]:
    """model_factory=None runs the real production `_model` (the Groq baseline).

    Passing a factory patches `encounter_agent._model` for the duration of the
    run - the same seam the existing tests use (see tests/test_encounter_agent.py)
    - so a fine-tuned model's wrapper can be evaluated with this same function.

    Stops early (returning whatever's collected so far) if the daily quota
    runs out mid-run, rather than letting the rest silently count as
    "invalid" model responses - see RateLimitTooLong in common.groq_backoff.
    """
    if model_factory is None:
        return _run_all(contexts)
    with patch.object(encounter_agent, "_model", side_effect=model_factory):
        return _run_all(contexts)


def measure_cost_samples(
    contexts: list[EvalContext], model_factory: ModelFactory | None = None
) -> list[CostSample]:
    """One probe call per distinct (tier, setting) - token usage doesn't vary
    meaningfully across repeats of the same context, so repeating it would
    only burn calls without sharpening the estimate."""
    seen: set[tuple[str, str]] = set()
    samples: list[CostSample] = []
    factory = model_factory or encounter_agent._model
    for context in contexts:
        key = (context.tier, context.setting)
        if key in seen:
            continue
        seen.add(key)

        model = factory().with_structured_output(EnemyProposal, include_raw=True)
        prompt = encounter_agent._build_prompt(_initial_state(context))
        try:
            result, _latency = call_with_backoff(lambda m=model, p=prompt: m.invoke(p))
        except RateLimitTooLong as exc:
            print(f"Cost probe stopping early - quota exhausted: {exc}", file=sys.stderr)
            break
        usage = result["raw"].usage_metadata
        samples.append(
            CostSample(
                tier=context.tier,
                setting=context.setting,
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
            )
        )
    return samples
