from src.diagnosis.classifier import DiagnosisPrediction
from src.guardrails.config import MAX_ATTEMPTS, MAX_CONTACT_ATTEMPTS
from src.guardrails.guardrails import enforce
from src.policy.engine import PolicyDecision
from tests.factories import make_case


def test_retry_rejected_after_max_attempts():
    """The deliberate-failure scenario: something upstream proposes RETRY
    after the policy has already exhausted allowed attempts. The guardrail
    must reject it regardless of why it was proposed."""
    case = make_case(subscription_state="pending")
    decision, violation = enforce(
        case, PolicyDecision.RETRY, attempt_count=MAX_ATTEMPTS, contact_attempts_used=0, diagnosis_confidence=0.9
    )
    assert decision == PolicyDecision.STOP
    assert violation is not None
    assert "MAX_ATTEMPTS" in violation.reason
    assert violation.original_decision == "retry"


def test_retry_allowed_below_max_attempts():
    case = make_case(subscription_state="pending")
    decision, violation = enforce(
        case, PolicyDecision.RETRY, attempt_count=0, contact_attempts_used=0, diagnosis_confidence=0.9
    )
    assert decision == PolicyDecision.RETRY
    assert violation is None


def test_retry_rejected_on_halted_subscription():
    case = make_case(subscription_state="halted")
    decision, violation = enforce(
        case, PolicyDecision.RETRY, attempt_count=0, contact_attempts_used=0, diagnosis_confidence=0.9
    )
    assert decision == PolicyDecision.STOP
    assert violation is not None


def test_escalate_rejected_after_max_contact_attempts():
    case = make_case()
    decision, violation = enforce(
        case,
        PolicyDecision.ESCALATE,
        attempt_count=0,
        contact_attempts_used=MAX_CONTACT_ATTEMPTS,
        diagnosis_confidence=0.9,
    )
    assert decision == PolicyDecision.STOP
    assert violation is not None
    assert "MAX_CONTACT_ATTEMPTS" in violation.reason


def test_low_confidence_forces_clarify_even_if_action_proposed():
    case = make_case()
    decision, violation = enforce(
        case, PolicyDecision.RETRY, attempt_count=0, contact_attempts_used=0, diagnosis_confidence=0.05
    )
    assert decision == PolicyDecision.CLARIFY
    assert violation is not None


def test_stop_and_clarify_pass_through_unchanged():
    case = make_case()
    decision, violation = enforce(
        case, PolicyDecision.STOP, attempt_count=0, contact_attempts_used=0, diagnosis_confidence=0.9
    )
    assert decision == PolicyDecision.STOP
    assert violation is None
