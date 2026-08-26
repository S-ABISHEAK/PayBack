"""Independent hard-stop validation layer.

Re-derives allowed/not-allowed directly from the case and the current
attempt/contact counters, regardless of how a decision was produced. This is
deliberately redundant with policy/engine.py's own eligibility checks — the
redundancy is the safety property: a bug or a bad advisory signal upstream
(the diagnosis classifier today; the escalation agent from Phase 3 onward)
can propose an out-of-bounds action, but it can never silently become one,
because this layer re-checks the hard numeric/state limits from scratch and
never trusts the caller's reasoning. Every rejection is returned as a
GuardrailViolation for the orchestrator to audit-log.
"""

from __future__ import annotations

from pydantic import BaseModel

from data.schemas.case_schema import PaymentCase, SubscriptionState
from src.guardrails.config import LOW_CONFIDENCE_FLOOR, MAX_ATTEMPTS, MAX_CONTACT_ATTEMPTS
from src.policy.engine import PolicyDecision


class GuardrailViolation(BaseModel):
    reason: str
    original_decision: str


def enforce(
    case: PaymentCase,
    decision: PolicyDecision,
    attempt_count: int,
    contact_attempts_used: int,
    diagnosis_confidence: float,
) -> tuple[PolicyDecision, GuardrailViolation | None]:
    if decision == PolicyDecision.RETRY:
        if attempt_count >= MAX_ATTEMPTS:
            return PolicyDecision.STOP, GuardrailViolation(
                reason=f"retry proposed at attempt_count={attempt_count} >= MAX_ATTEMPTS={MAX_ATTEMPTS}",
                original_decision=decision.value,
            )
        if case.context.subscription_state == SubscriptionState.HALTED:
            return PolicyDecision.STOP, GuardrailViolation(
                reason="retry proposed on a halted subscription", original_decision=decision.value
            )

    if decision == PolicyDecision.ESCALATE:
        if contact_attempts_used >= MAX_CONTACT_ATTEMPTS:
            return PolicyDecision.STOP, GuardrailViolation(
                reason=(
                    f"escalation proposed at contact_attempts_used={contact_attempts_used} "
                    f">= MAX_CONTACT_ATTEMPTS={MAX_CONTACT_ATTEMPTS}"
                ),
                original_decision=decision.value,
            )
        if not case.context.is_escalation_eligible:
            return PolicyDecision.STOP, GuardrailViolation(
                reason="escalation proposed on a contact-ineligible case", original_decision=decision.value
            )

    if decision in (PolicyDecision.RETRY, PolicyDecision.ESCALATE) and diagnosis_confidence < LOW_CONFIDENCE_FLOOR:
        return PolicyDecision.CLARIFY, GuardrailViolation(
            reason=f"action proposed at confidence {diagnosis_confidence:.2f} below hard floor {LOW_CONFIDENCE_FLOOR}",
            original_decision=decision.value,
        )

    return decision, None
