"""Replayable per-case state machine: DIAGNOSE -> (DECIDE -> guardrail-check
-> ACT)* -> AUDIT. Loops cycles within a single case until resolved or
stopped, bounded both by the guardrail counters (MAX_ATTEMPTS,
MAX_CONTACT_ATTEMPTS) and an absolute `max_cycles` safety cap independent of
those counters, so a logic bug anywhere upstream cannot spin forever.

This single function is what both scripts/replay_case.py (one case, full
trace) and evaluation/experiments/run_system_eval.py (the full held-out
batch) call — the batch run is just this function applied to every detected
case, which is what makes a batch result replayable case-by-case afterward.
"""

from __future__ import annotations

from data.schemas.case_schema import PaymentCase
from evaluation.metrics.schema import CaseResult
from src.audit.logger import AuditLogger
from src.diagnosis.classifier import DiagnosisClassifier
from src.escalation.agent import EscalationAgent
from src.guardrails.config import MAX_ATTEMPTS, MAX_CONTACT_ATTEMPTS
from src.guardrails.guardrails import enforce
from src.policy.engine import PolicyDecision, decide
from src.promise.extractor import PromiseExtractor, RuleBasedPromiseExtractor
from src.retry.executor import RetryExecutor

# Absolute safety cap, independent of (but sized to comfortably exceed) the
# guardrail counters: worst case is MAX_ATTEMPTS retry cycles + MAX_CONTACT_ATTEMPTS
# escalation cycles + one final cycle where decide() lands on STOP/CLARIFY.
# A logic bug that somehow bypassed both counters would still be bounded here.
MAX_CYCLES = MAX_ATTEMPTS + MAX_CONTACT_ATTEMPTS + 1


def process_case(
    case: PaymentCase,
    classifier: DiagnosisClassifier,
    retry_executor: RetryExecutor,
    escalation_agent: EscalationAgent,
    audit_logger: AuditLogger,
    promise_extractor: PromiseExtractor | None = None,
) -> CaseResult:
    promise_extractor = promise_extractor or RuleBasedPromiseExtractor()
    eligible = case.context.is_retry_eligible or case.context.is_escalation_eligible
    audit_logger.log_event(case.case_id, "detected", {"eligible": eligible})

    if not eligible:
        audit_logger.log_event(case.case_id, "final_outcome", {"recovered": False, "channel": None})
        return CaseResult(
            case_id=case.case_id,
            amount_inr=case.context.amount_inr,
            eligible=False,
            recovered=False,
            audit_fields_present=1.0,
        )

    diagnosis = classifier.predict(case)
    audit_logger.log_event(
        case.case_id,
        "diagnosis",
        {
            "predicted_cause": diagnosis.predicted_cause.value,
            "confidence": diagnosis.confidence,
        },
    )

    attempt_count = case.context.attempt_count
    contact_attempts_used = 0
    attempts_used = 0
    escalated = False
    recovered = False
    channel: str | None = None
    guardrail_violations = 0

    for _cycle in range(MAX_CYCLES):
        decision, reason = decide(case, diagnosis, attempt_count, contact_attempts_used)
        audit_logger.log_event(case.case_id, "policy_decision", {"decision": decision.value, "reason": reason})

        enforced_decision, violation = enforce(case, decision, attempt_count, contact_attempts_used, diagnosis.confidence)
        if violation is not None:
            guardrail_violations += 1
            audit_logger.log_event(case.case_id, "guardrail_violation", violation.model_dump())

        if enforced_decision == PolicyDecision.RETRY:
            result = retry_executor.execute_retry(case, attempt_number=attempt_count + 1, targeted=True)
            attempt_count += 1
            attempts_used += 1
            audit_logger.log_event(case.case_id, "retry_attempt", result.model_dump())
            if result.success:
                recovered, channel = True, "retry"
                break
            continue  # try again next cycle; guardrails cap this once MAX_ATTEMPTS is hit

        if enforced_decision == PolicyDecision.ESCALATE:
            escalated = True
            contact_attempts_used += 1
            outcome = escalation_agent.escalate(case, attempt_number=contact_attempts_used)
            audit_logger.log_event(case.case_id, "escalation", outcome.model_dump())
            if outcome.conversation is not None:
                extraction = promise_extractor.extract(outcome.conversation, fallback_amount_inr=case.context.amount_inr)
                audit_logger.log_event(case.case_id, "promise_extraction", extraction.model_dump())
            if outcome.resolved:
                recovered, channel = True, "escalation"
                break
            continue  # guardrails cap further escalation once MAX_CONTACT_ATTEMPTS is hit

        if enforced_decision == PolicyDecision.CLARIFY:
            audit_logger.log_event(case.case_id, "clarify", {"reason": reason})
            break  # cannot proceed automatically without clarification

        audit_logger.log_event(case.case_id, "stop", {"reason": reason})
        break

    audit_logger.log_event(case.case_id, "final_outcome", {"recovered": recovered, "channel": channel})

    return CaseResult(
        case_id=case.case_id,
        amount_inr=case.context.amount_inr,
        eligible=True,
        recovered=recovered,
        recovery_channel=channel,
        attempts_used=attempts_used,
        escalated=escalated,
        guardrail_violations=guardrail_violations,
        audit_fields_present=1.0,
    )
