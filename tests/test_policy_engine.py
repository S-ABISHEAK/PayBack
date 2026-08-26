from data.schemas.case_schema import FailureCause
from src.diagnosis.classifier import DiagnosisPrediction
from src.policy.engine import PolicyDecision, decide
from tests.factories import make_case


def _diagnosis(cause: FailureCause, confidence: float) -> DiagnosisPrediction:
    return DiagnosisPrediction(predicted_cause=cause, confidence=confidence, probabilities={cause.value: confidence})


def test_retry_for_high_value_cause_with_high_confidence():
    case = make_case(subscription_state="pending")
    diagnosis = _diagnosis(FailureCause.INSUFFICIENT_FUNDS, 0.8)
    decision, reason = decide(case, diagnosis, attempt_count=0, contact_attempts_used=0)
    assert decision == PolicyDecision.RETRY


def test_low_confidence_routes_to_clarify():
    case = make_case(subscription_state="pending")
    diagnosis = _diagnosis(FailureCause.INSUFFICIENT_FUNDS, 0.1)
    decision, reason = decide(case, diagnosis, attempt_count=0, contact_attempts_used=0)
    assert decision == PolicyDecision.CLARIFY


def test_low_retry_value_cause_after_one_attempt_escalates_instead_of_retrying():
    case = make_case(subscription_state="pending")
    diagnosis = _diagnosis(FailureCause.EXPIRED_INVALID_INSTRUMENT, 0.8)
    decision, reason = decide(case, diagnosis, attempt_count=1, contact_attempts_used=0)
    assert decision == PolicyDecision.ESCALATE


def test_low_retry_value_cause_on_first_attempt_still_retries_once():
    """attempt_count == 0: give retry one shot even for a low-retry-value
    cause, since diagnosis confidence isn't proof — matches the naive
    baseline's own first-attempt behavior, so the system's edge shows up in
    what happens *after* that first attempt, not in skipping it."""
    case = make_case(subscription_state="pending")
    diagnosis = _diagnosis(FailureCause.EXPIRED_INVALID_INSTRUMENT, 0.8)
    decision, reason = decide(case, diagnosis, attempt_count=0, contact_attempts_used=0)
    assert decision == PolicyDecision.RETRY


def test_nothing_eligible_stops():
    case = make_case(subscription_state="halted")
    case = case.model_copy(update={"context": case.context.model_copy(update={"is_escalation_eligible": False})})
    diagnosis = _diagnosis(FailureCause.INSUFFICIENT_FUNDS, 0.9)
    decision, reason = decide(case, diagnosis, attempt_count=4, contact_attempts_used=0)
    assert decision == PolicyDecision.STOP


def test_retry_exhausted_but_escalation_eligible_escalates():
    case = make_case(subscription_state="pending")
    diagnosis = _diagnosis(FailureCause.INSUFFICIENT_FUNDS, 0.9)
    decision, reason = decide(case, diagnosis, attempt_count=4, contact_attempts_used=0)
    assert decision == PolicyDecision.ESCALATE
