"""Phase 6 — deliberate adversarial/boundary-case testing (spec §6 step 8,
implementation plan Phase 6). Confirms the legitimate batch produces zero
guardrail violations while injected boundary/malformed cases are caught and
logged correctly, not silently mishandled — this is where the "guardrail
caught it" failure-and-recovery evidence gets captured for real.
"""

from data.schemas.case_schema import FailureCause
from src.audit.db import get_engine
from src.audit.logger import AuditLogger
from src.diagnosis.classifier import DiagnosisClassifier, DiagnosisPrediction
from src.escalation.agent import StubEscalationAgent
from src.guardrails.config import MAX_ATTEMPTS, MAX_CONTACT_ATTEMPTS
from src.orchestration import state_machine
from src.orchestration.state_machine import process_case
from src.promise.extractor import LLMPromiseExtractor
from src.retry.executor import StubRetryExecutor
from tests.factories import make_case


def _harness(tmp_path, seed=1):
    classifier = DiagnosisClassifier(random_state=seed)
    classifier.fit([make_case(f"train_{i}", seed=100 + i) for i in range(60)])
    retry_executor = StubRetryExecutor(seed=seed)
    escalation_agent = StubEscalationAgent(seed=seed)
    audit_logger = AuditLogger(get_engine(tmp_path / "test.db"))
    return classifier, retry_executor, escalation_agent, audit_logger


# --- 1. Boundary case: already at exactly MAX_ATTEMPTS -------------------


def test_case_exactly_at_max_attempts_never_retries_with_zero_violations(tmp_path):
    """A case detected already sitting at the MAX_ATTEMPTS boundary must
    never trigger a retry, and — since the policy engine itself already
    respects this boundary under normal operation — should produce zero
    guardrail violations, not a caught-and-corrected one."""
    classifier, retry_executor, escalation_agent, audit_logger = _harness(tmp_path)
    case = make_case("case_at_max", seed=2, subscription_state="pending")
    case = case.model_copy(
        update={
            "context": case.context.model_copy(
                update={"attempt_count": MAX_ATTEMPTS, "is_escalation_eligible": True}
            )
        }
    )
    result = process_case(case, classifier, retry_executor, escalation_agent, audit_logger)
    assert result.attempts_used == 0
    assert result.guardrail_violations == 0
    events = audit_logger.get_events(case.case_id)
    assert not any(e["event_type"] == "retry_attempt" for e in events)


# --- 2. Missing/null fields: classifier must not crash --------------------


def test_diagnosis_classifier_handles_all_nullable_fields_missing():
    """Every field dropout-eligible field null at once (worst case of the
    generator's own field-dropout noise, see failure_generator.py) must
    still produce a valid prediction, not a crash — the diagnosis step is
    on the critical path for every case, including the ones the panel will
    poke at directly."""
    classifier = DiagnosisClassifier(random_state=1)
    classifier.fit([make_case(f"train_{i}", seed=100 + i) for i in range(60)])

    case = make_case("case_missing_fields", seed=3)
    case = case.model_copy(
        update={
            "context": case.context.model_copy(
                update={
                    "customer_payment_history_score": None,
                    "instrument_age_days": None,
                    "time_since_previous_attempt_hours": None,
                }
            )
        }
    )
    prediction = classifier.predict(case)
    assert isinstance(prediction.predicted_cause, FailureCause)
    assert 0.0 <= prediction.confidence <= 1.0


# --- 3. Idempotency: duplicate executor calls for the same attempt --------


def test_retry_executor_idempotent_for_same_attempt_number():
    """A duplicate retry request for the exact same attempt (e.g. a retried
    webhook delivery) must produce the identical outcome, not a fresh coin
    flip — StubRetryExecutor is keyed by (seed, case_id, attempt_number),
    not shared sequential RNG state, specifically to guarantee this."""
    executor_a = StubRetryExecutor(seed=42)
    executor_b = StubRetryExecutor(seed=42)
    case = make_case("case_dup", seed=4)

    result_1 = executor_a.execute_retry(case, attempt_number=1)
    result_2 = executor_b.execute_retry(case, attempt_number=1)
    assert result_1.success == result_2.success
    assert result_1.reason == result_2.reason


def test_escalation_agent_idempotent_for_same_attempt_number():
    agent_a = StubEscalationAgent(seed=42)
    agent_b = StubEscalationAgent(seed=42)
    case = make_case("case_dup_esc", seed=5)

    outcome_1 = agent_a.escalate(case, attempt_number=1)
    outcome_2 = agent_b.escalate(case, attempt_number=1)
    assert outcome_1.resolved == outcome_2.resolved


def test_KNOWN_LIMITATION_repeated_process_case_invocation_is_not_state_idempotent(tmp_path):
    """Documents a real, understood gap found via adversarial testing, not a
    silent one: process_case() derives attempt_count fresh from
    case.context.attempt_count on every call rather than resuming from a
    persistent per-case state store (the `cases` table named in the
    implementation plan's tech stack was never built — audit_events alone
    exists). In the current batch-evaluation architecture this is harmless:
    run_system_eval.py invokes process_case() exactly once per case per run,
    so no duplicate-invocation path is ever exercised, and repeated *script*
    runs are separate, deliberate re-evaluations, not duplicate events for
    the same underlying payment. It WOULD matter if this were exposed to
    live webhook-triggered re-processing (a duplicate "payment failed" event
    for a case already mid-retry) — each invocation would independently get
    its own fresh MAX_ATTEMPTS budget instead of resuming shared state. This
    test pins the current (limited) behavior so a future fix is a visible,
    deliberate change to this test, not a silent regression. Production
    fix: read current attempt_count/contact_attempts_used from a per-case
    `cases` state row (keyed by case_id, scoped to a single logical case
    lifecycle) before starting the loop, instead of from static context.
    """
    classifier, retry_executor, escalation_agent, audit_logger = _harness(tmp_path)
    case = make_case("case_dup_invocation", seed=6, subscription_state="pending")
    case = case.model_copy(update={"context": case.context.model_copy(update={"attempt_count": MAX_ATTEMPTS - 1})})

    process_case(case, classifier, retry_executor, escalation_agent, audit_logger)
    process_case(case, classifier, retry_executor, escalation_agent, audit_logger)

    events = audit_logger.get_events(case.case_id)
    final_outcomes = [e for e in events if e["event_type"] == "final_outcome"]
    # The known gap, made concrete: a single logical case gets two full,
    # independent run-throughs logged (two "final_outcome" events) instead
    # of the second invocation recognizing the case as already handled and
    # no-op'ing. Whichever channel (retry or escalation) each run took, both
    # ran their own fresh MAX_ATTEMPTS/MAX_CONTACT_ATTEMPTS budget.
    assert len(final_outcomes) == 2


# --- 4. Forced malformed structured output (promise extractor) ------------


def test_malformed_json_falls_back_safely(monkeypatch):
    extractor = LLMPromiseExtractor()
    monkeypatch.setattr(extractor, "_call", lambda prompt: "I think the customer will pay soon.")
    result = extractor.extract([{"role": "customer", "text": "kal kar dunga"}], fallback_amount_inr=500)
    assert result.has_promise is False
    assert result.confidence == 0.0


def test_wrong_type_has_promise_string_no_does_not_become_true(monkeypatch):
    """The bug found via adversarial testing: {"has_promise": "no"} must NOT
    be silently coerced to True by a naive bool() cast (a non-empty string
    is truthy in Python) — it must be treated as malformed and go through
    the same repair/fallback path as broken JSON."""
    extractor = LLMPromiseExtractor()
    monkeypatch.setattr(
        extractor,
        "_call",
        lambda prompt: '{"has_promise": "no", "promised_amount_inr": null, "promised_date_offset_days": null, "confidence": 0.5}',
    )
    result = extractor.extract([{"role": "customer", "text": "nahi karunga"}], fallback_amount_inr=500)
    assert result.has_promise is False
    assert result.confidence == 0.0  # fell through to the safe fallback, not a miscoerced "true"


def test_truncated_json_falls_back_safely(monkeypatch):
    extractor = LLMPromiseExtractor()
    monkeypatch.setattr(extractor, "_call", lambda prompt: '{"has_promise": true, "promised_amount_')
    result = extractor.extract([{"role": "customer", "text": "kal kar dunga"}], fallback_amount_inr=500)
    assert result.has_promise is False
    assert result.confidence == 0.0


def test_wrong_type_amount_falls_back_safely(monkeypatch):
    extractor = LLMPromiseExtractor()
    monkeypatch.setattr(
        extractor,
        "_call",
        lambda prompt: '{"has_promise": true, "promised_amount_inr": "five hundred", "confidence": 0.8}',
    )
    result = extractor.extract([{"role": "customer", "text": "kal kar dunga"}], fallback_amount_inr=500)
    assert result.has_promise is False
    assert result.confidence == 0.0


# --- 5. Guardrail catches a buggy policy engine, end to end ---------------


def test_guardrail_catches_buggy_policy_proposing_retry_after_exhaustion(tmp_path, monkeypatch):
    """The deliberate-failure-story scenario, exercised at the full state-
    machine level (not just guardrails.enforce() in isolation): even if the
    policy engine itself had a bug and proposed RETRY for a case that has
    already exhausted MAX_ATTEMPTS, the guardrail layer must independently
    catch and log it — the retry executor must never actually be called."""
    classifier, retry_executor, escalation_agent, audit_logger = _harness(tmp_path)
    case = make_case("case_buggy_policy", seed=7, subscription_state="pending")
    case = case.model_copy(update={"context": case.context.model_copy(update={"attempt_count": MAX_ATTEMPTS})})

    from src.policy.engine import PolicyDecision

    def broken_decide(case, diagnosis, attempt_count, contact_attempts_used):
        return PolicyDecision.RETRY, "BUG: always proposes retry regardless of attempt_count"

    monkeypatch.setattr(state_machine, "decide", broken_decide)

    retry_calls = []
    original_execute = retry_executor.execute_retry
    retry_executor.execute_retry = lambda *a, **kw: retry_calls.append(1) or original_execute(*a, **kw)

    result = process_case(case, classifier, retry_executor, escalation_agent, audit_logger)

    assert retry_calls == [], "the retry executor must never be invoked once guardrails reject the decision"
    assert result.guardrail_violations >= 1
    events = audit_logger.get_events(case.case_id)
    violation_events = [e for e in events if e["event_type"] == "guardrail_violation"]
    assert len(violation_events) >= 1
    assert "MAX_ATTEMPTS" in violation_events[0]["payload"]["reason"]
