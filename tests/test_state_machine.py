from src.audit.db import get_engine
from src.audit.logger import AuditLogger
from src.diagnosis.classifier import DiagnosisClassifier
from src.escalation.agent import EscalationOutcome, StubEscalationAgent
from src.orchestration.state_machine import process_case
from src.retry.executor import StubRetryExecutor
from tests.factories import make_case


def _harness(tmp_path, seed=1):
    classifier = DiagnosisClassifier(random_state=seed)
    classifier.fit([make_case(f"train_{i}", seed=100 + i) for i in range(60)])
    retry_executor = StubRetryExecutor(seed=seed)
    escalation_agent = StubEscalationAgent(seed=seed)
    audit_logger = AuditLogger(get_engine(tmp_path / "test.db"))
    return classifier, retry_executor, escalation_agent, audit_logger


def test_single_case_replay_produces_full_audit_trail(tmp_path):
    classifier, retry_executor, escalation_agent, audit_logger = _harness(tmp_path)
    case = make_case("case_replay", seed=5, subscription_state="pending")

    result = process_case(case, classifier, retry_executor, escalation_agent, audit_logger)

    events = audit_logger.get_events(case.case_id)
    event_types = [e["event_type"] for e in events]
    assert "detected" in event_types
    assert "diagnosis" in event_types
    assert "policy_decision" in event_types
    assert event_types[-1] == "final_outcome"
    assert result.case_id == case.case_id


def test_ineligible_case_stops_without_diagnosis(tmp_path):
    classifier, retry_executor, escalation_agent, audit_logger = _harness(tmp_path)
    case = make_case("case_ineligible", seed=6)
    case = case.model_copy(
        update={
            "context": case.context.model_copy(
                update={"is_retry_eligible": False, "is_escalation_eligible": False}
            )
        }
    )
    result = process_case(case, classifier, retry_executor, escalation_agent, audit_logger)
    assert result.eligible is False
    assert result.recovered is False
    event_types = [e["event_type"] for e in audit_logger.get_events(case.case_id)]
    assert "diagnosis" not in event_types


def test_halted_subscription_never_retries_and_guardrail_never_fires_from_policy_engine(tmp_path):
    """The policy engine itself already refuses to propose RETRY on a halted
    subscription (src/policy/engine.py), so under normal operation the
    guardrail layer shouldn't need to intervene here — this test documents
    that division of responsibility."""
    classifier, retry_executor, escalation_agent, audit_logger = _harness(tmp_path)
    case = make_case("case_halted", seed=7, subscription_state="halted")

    result = process_case(case, classifier, retry_executor, escalation_agent, audit_logger)

    assert result.attempts_used == 0
    events = audit_logger.get_events(case.case_id)
    assert not any(e["event_type"] == "retry_attempt" for e in events)


def test_promise_extraction_runs_when_escalation_yields_a_conversation(tmp_path):
    """When an escalation agent returns a real transcript (as
    PromptedEscalationAgent will, once Ollama is available), the orchestrator
    must run promise extraction over it and audit-log the result. StubEscalationAgent
    returns conversation=None, so this uses a small fake agent to exercise the path."""

    class FakeConversationalEscalationAgent:
        def escalate(self, case, attempt_number=1):
            return EscalationOutcome(
                resolved=True,
                promise_made=True,
                conversation=[{"role": "customer", "text": "Haan bilkul, main aaj 500 rupees pay kar dunga."}],
            )

    classifier = DiagnosisClassifier(random_state=1)
    classifier.fit([make_case(f"train_{i}", seed=100 + i) for i in range(60)])
    retry_executor = StubRetryExecutor(seed=1)
    audit_logger = AuditLogger(get_engine(tmp_path / "test.db"))

    case = make_case("case_conv", seed=11, subscription_state="halted")
    case = case.model_copy(update={"context": case.context.model_copy(update={"is_escalation_eligible": True})})
    result = process_case(case, classifier, retry_executor, FakeConversationalEscalationAgent(), audit_logger)

    events = audit_logger.get_events(case.case_id)
    extraction_events = [e for e in events if e["event_type"] == "promise_extraction"]
    assert len(extraction_events) >= 1
    assert extraction_events[0]["payload"]["has_promise"] is True
    assert result.recovered is True


def test_bounded_number_of_cycles(tmp_path):
    """Regardless of outcome, a case can never generate more policy_decision
    events than the state machine's MAX_CYCLES safety cap."""
    from src.orchestration.state_machine import MAX_CYCLES

    classifier, retry_executor, escalation_agent, audit_logger = _harness(tmp_path)
    case = make_case("case_bounded", seed=8, subscription_state="pending")
    process_case(case, classifier, retry_executor, escalation_agent, audit_logger)
    events = audit_logger.get_events(case.case_id)
    n_decisions = sum(1 for e in events if e["event_type"] == "policy_decision")
    assert n_decisions <= MAX_CYCLES
