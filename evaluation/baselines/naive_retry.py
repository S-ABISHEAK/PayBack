"""Naive baseline (spec §10): retry every eligible failed payment blindly,
on one fixed rule, up to the same MAX_ATTEMPTS ceiling the real system
respects — but with no diagnosis-awareness and, crucially, no escalation
channel at all. This is the floor the full system's uplift is measured
against.

Deliberately given the same multi-attempt budget as the system (rather than
a single attempt) so the comparison isolates what the system actually adds —
diagnosis-aware routing and an escalation channel — rather than an
artifact of the system getting more tries than the baseline. Both run over
the identical held-out population (evaluation/experiments/run_baseline.py /
run_system_eval.py).
"""

from __future__ import annotations

from data.generators.failure_generator import RETRY_DECAY_FACTOR, decayed_prob, stable_rng
from data.schemas.case_schema import PaymentCase, SubscriptionState
from evaluation.metrics.schema import CaseResult
from src.guardrails.config import MAX_ATTEMPTS


def run_naive_baseline(cases: list[PaymentCase], seed: int) -> list[CaseResult]:
    # Each (case, attempt) draw is keyed independently rather than pulled from
    # one shared sequential RNG across the case list — otherwise the result
    # would silently depend on case processing order (e.g. `set` iteration
    # order for str case_ids varies per-process). See
    # data.generators.failure_generator.stable_rng for the full rationale.
    results = []
    for case in cases:
        # "eligible" is the ₹-at-risk population definition — any intervention
        # (retry OR escalation) is structurally possible — kept identical to
        # how the full system defines it (src/detection/detector.py) so the
        # two reports' denominators match, even though this baseline never
        # actually uses the escalation channel.
        eligible = case.context.is_retry_eligible or case.context.is_escalation_eligible

        attempt_count = case.context.attempt_count
        halted = case.context.subscription_state == SubscriptionState.HALTED
        recovered = False
        attempts_used = 0
        channel = None

        while not halted and attempt_count < MAX_ATTEMPTS and not recovered:
            prob = decayed_prob(
                case.ground_truth.retry_success_prob_untargeted,
                n_prior_attempts=attempt_count,
                decay_factor=RETRY_DECAY_FACTOR,
            )
            attempts_used += 1
            attempt_count += 1
            rng = stable_rng(seed, case.case_id, attempt_count)
            if rng.random() < prob:
                recovered = True
                channel = "retry"

        results.append(
            CaseResult(
                case_id=case.case_id,
                amount_inr=case.context.amount_inr,
                eligible=eligible,
                recovered=recovered,
                recovery_channel=channel,
                attempts_used=attempts_used,
                escalated=False,
            )
        )
    return results
