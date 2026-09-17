"""Generates one candidate EnemyProposal per DataContext and filters it
through validate_proposal() - the same function that guards production, now
doing data quality control instead of a runtime retry decision.

Deliberately single-shot: unlike the production graph, a rejected proposal
here is discarded, not corrected. The point is training data for a model that
should get this right zero-shot, not a delivered enemy.

iter_examples() yields one RawRecord per context as soon as it's done, rather
than collecting a list to return at the end - a ~300-call run can take well
over an hour under Groq's free-tier rate limit, and a return-at-the-end
design loses all of it if the process dies before the last call finishes.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from agentic_rogue_like.agent import encounter_agent
from agentic_rogue_like.agent.encounter_schema import (
    BudgetViolation,
    EnemyProposal,
    validate_proposal,
)

from common.groq_backoff import RateLimitTooLong, call_with_backoff

from .contexts import DataContext, to_encounter_state


@dataclass
class RawRecord:
    tier: str
    setting: str
    split: str
    repeat_index: int
    status: str  # "accepted" | "rejected"
    prompt: str
    proposal: dict | None
    reason: str | None

    @staticmethod
    def from_context(
        context: DataContext,
        prompt: str,
        status: str,
        proposal: EnemyProposal | None,
        reason: str | None,
    ) -> RawRecord:
        return RawRecord(
            tier=context.tier,
            setting=context.setting,
            split=context.split,
            repeat_index=context.repeat_index,
            status=status,
            prompt=prompt,
            proposal=proposal.model_dump() if proposal is not None else None,
            reason=reason,
        )


def iter_examples(contexts: list[DataContext]) -> Iterator[RawRecord]:
    model = encounter_agent._model().with_structured_output(EnemyProposal)

    for context in contexts:
        prompt = encounter_agent._build_prompt(to_encounter_state(context))
        try:
            proposal, _latency = call_with_backoff(lambda p=prompt: model.invoke(p))
        except RateLimitTooLong:
            # A near-exhausted quota affects every remaining context equally -
            # let the caller decide to stop the run, instead of burning
            # through the rest as instant, uninformative rejections.
            raise
        except Exception as exc:  # noqa: BLE001 - same broad boundary as the eval harness
            yield RawRecord.from_context(context, prompt, "rejected", None, str(exc))
            continue

        try:
            validate_proposal(proposal, context.budget)
        except BudgetViolation as exc:
            yield RawRecord.from_context(context, prompt, "rejected", proposal, str(exc))
            continue

        yield RawRecord.from_context(context, prompt, "accepted", proposal, None)
