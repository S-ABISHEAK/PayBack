"""Replay one case end-to-end and print its full audit trail.

Usage: python scripts/replay_case.py case_00007 [--seed 42]
"""

import argparse

import _bootstrap  # noqa: F401

from data.generators.failure_generator import REPO_ROOT, load_jsonl
from src.audit.db import get_engine
from src.audit.logger import AuditLogger
from src.diagnosis.classifier import DiagnosisClassifier
from src.escalation.agent import get_escalation_agent
from src.orchestration.state_machine import process_case
from src.retry.executor import get_retry_executor

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
MODELS_DIR = REPO_ROOT / "models" / "diagnosis"


def main(case_id: str, seed: int = 42) -> None:
    all_cases = {c.case_id: c for c in load_jsonl(SAMPLES_DIR / "cases.jsonl")}
    if case_id not in all_cases:
        raise SystemExit(f"Unknown case_id {case_id!r}. Run scripts/generate_dataset.py first.")
    case = all_cases[case_id]

    classifier = DiagnosisClassifier(random_state=seed)
    classifier.load(MODELS_DIR / "classifier.joblib")
    retry_executor = get_retry_executor(seed=seed)
    escalation_agent = get_escalation_agent(seed=seed)
    audit_logger = AuditLogger(get_engine())

    print(f"Case {case_id}")
    print(f"  amount_inr={case.context.amount_inr}  subscription_state={case.context.subscription_state.value}")
    print(f"  observed.reason={case.observed.reason}  attempt_count={case.context.attempt_count}")
    print(f"  ground_truth.true_cause={case.ground_truth.true_cause.value}  (hidden from the system)")
    print()

    result = process_case(case, classifier, retry_executor, escalation_agent, audit_logger)

    print("Audit trail:")
    for event in audit_logger.get_events(case_id):
        print(f"  [{event['id']:>3}] {event['event_type']:<20} {event['payload']}")

    print()
    print(f"Final: recovered={result.recovered}  channel={result.recovery_channel}  "
          f"attempts_used={result.attempts_used}  escalated={result.escalated}  "
          f"guardrail_violations={result.guardrail_violations}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("case_id")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(case_id=args.case_id, seed=args.seed)
