"""Deterministic policy engine — a pure function, no model calls, no I/O,
no randomness. This is the one place in the system authorized to decide a
financial action. The diagnosis classifier's output is only ever a
structured advisory input (predicted_cause, confidence); this module is what
turns it into a decision, and src/guardrails/guardrails.py independently
re-validates that decision before it becomes an action (spec §8D).
"""

from __future__ import annotations

from enum import Enum

from data.schemas.case_schema import FailureCause, PaymentCase, SubscriptionState
from src.diagnosis.classifier import DiagnosisPrediction
from src.guardrails.config import LOW_CONFIDENCE_THRESHOLD, MAX_ATTEMPTS, MAX_CONTACT_ATTEMPTS


class PolicyDecision(str, Enum):
    RETRY = "retry"
    ESCALATE = "escalate"
    CLARIFY = "clarify"
    STOP = "stop"


# Causes where the synthetic recovery model (data/generators/failure_generator.py
# RECOVERY_PARAMS) says retry rarely helps even when correctly timed — the
# right channel is escalation, not another blind retry.
LOW_RETRY_VALUE_CAUSES = {
    FailureCause.MANDATE_LIMIT_RELATED,
    FailureCause.EXPIRED_INVALID_INSTRUMENT,
    FailureCause.CUSTOMER_DECLINED_INTENTIONAL,
}


def decide(
    case: PaymentCase,
    diagnosis: DiagnosisPrediction,
    attempt_count: int,
    contact_attempts_used: int,
) -> tuple[PolicyDecision, str]:
    """Returns (decision, human-readable reason)."""
    retry_allowed = attempt_count < MAX_ATTEMPTS and case.context.subscription_state != SubscriptionState.HALTED
    escalation_allowed = case.context.is_escalation_eligible and contact_attempts_used < MAX_CONTACT_ATTEMPTS

    if not retry_allowed and not escalation_allowed:
        return PolicyDecision.STOP, "no eligible actions remaining (retries and escalation both exhausted or ineligible)"

    if diagnosis.confidence < LOW_CONFIDENCE_THRESHOLD:
        return (
            PolicyDecision.CLARIFY,
            f"diagnosis confidence {diagnosis.confidence:.2f} below business threshold {LOW_CONFIDENCE_THRESHOLD}",
        )

    low_value_retry = diagnosis.predicted_cause in LOW_RETRY_VALUE_CAUSES and attempt_count >= 1

    if retry_allowed and not low_value_retry:
        return PolicyDecision.RETRY, f"diagnosis-aware retry (predicted cause: {diagnosis.predicted_cause.value})"

    if escalation_allowed:
        reason = (
            f"predicted cause {diagnosis.predicted_cause.value} unlikely to resolve via further retry "
            f"after {attempt_count} attempt(s); escalating"
            if low_value_retry
            else "retry not viable/exhausted; escalating"
        )
        return PolicyDecision.ESCALATE, reason

    return PolicyDecision.STOP, "retry not viable for predicted cause and escalation unavailable"
