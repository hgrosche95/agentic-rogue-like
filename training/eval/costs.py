"""Known $/token pricing, used to turn measured token counts into a $ figure.

Groq doesn't return a dollar amount anywhere in its API - only token counts.
The prices below are the documented rate, so "measured tokens x documented
price" stays an honest, reproducible number instead of a guess at either
factor. Re-check before quoting these in a final report; Groq can reprice.
"""

from __future__ import annotations

# Source: https://www.cloudzero.com/blog/groq-pricing/ and
# https://www.eesel.ai/blog/groq-pricing, cross-checked, as of 2026-09-17.
GROQ_PRICING_PER_MILLION_TOKENS: dict[str, dict[str, float]] = {
    "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
}


def estimate_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """None when `model_name` has no known price - e.g. a local model, where
    the honest answer is "no per-call $ cost", not a fabricated number."""
    pricing = GROQ_PRICING_PER_MILLION_TOKENS.get(model_name)
    if pricing is None:
        return None
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
