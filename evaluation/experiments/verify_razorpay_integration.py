"""Live integration check for RazorpayTestModeRetryExecutor against Razorpay's
real test-mode API — NOT a re-freeze of the frozen headline metrics.

The frozen 242-case held-out evaluation (evaluation/reports/system_report.json)
intentionally runs on StubRetryExecutor (deterministic, offline, reproducible
byte-for-byte across reruns — see docs/failure_story.md for why that
reproducibility property matters). Running the full held-out batch against a
live API would mean up to MAX_ATTEMPTS real orders per case, hundreds of real
API calls, and a result that's no longer exactly reproducible — none of which
is needed to prove the real executor actually works. Per the original plan's
own design: "if a full live run is impractical, run the full batch on the
stub and a smaller live-verified subsample — report both explicitly, never
silently substitute."

This script runs a small, deterministic subsample of real held-out cases
through the FULL orchestrator (detection -> diagnosis -> policy -> guardrails
-> retry/escalate -> audit) with the real Razorpay executor, against a
separate audit DB (data/razorpay_integration_check.db) so it never touches
the main recovery.db the frozen reports depend on. Escalation uses the stub
agent (deterministic, no Ollama needed) so this check isolates the Razorpay
integration specifically.

Usage: python scripts/verify_razorpay_integration.py [--n-cases 8]
Writes evaluation/reports/razorpay_integration_check.json.
"""

from __future__ import annotations

import json
import os

from data.generators.failure_generator import REPO_ROOT, load_jsonl
from data.generators.split import load_ids
from src.audit.db import get_engine
from src.audit.logger import AuditLogger
from src.detection.detector import detect_at_risk
from src.diagnosis.classifier import DiagnosisClassifier
from src.escalation.agent import StubEscalationAgent
from src.orchestration.state_machine import process_case
from src.retry.executor import RazorpayTestModeRetryExecutor

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
MODELS_DIR = REPO_ROOT / "models" / "diagnosis"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"
CHECK_DB_PATH = REPO_ROOT / "data" / "razorpay_integration_check.db"


def main(n_cases: int = 8, seed: int = 42) -> None:
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise SystemExit("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set — required for this live check.")

    all_cases = {c.case_id: c for c in load_jsonl(SAMPLES_DIR / "cases.jsonl")}
    holdout_ids = load_ids(SAMPLES_DIR / "holdout_case_ids.txt")
    holdout_cases = [all_cases[cid] for cid in sorted(holdout_ids)]

    # Deterministic subsample, biased toward retry-eligible cases so the real
    # executor is actually exercised, not just skipped past.
    retry_eligible = [c for c in holdout_cases if c.context.is_retry_eligible]
    subsample = retry_eligible[:n_cases] if len(retry_eligible) >= n_cases else holdout_cases[:n_cases]

    classifier = DiagnosisClassifier(random_state=seed)
    classifier.load(MODELS_DIR / "classifier.joblib")

    retry_executor = RazorpayTestModeRetryExecutor(key_id=key_id, key_secret=key_secret, seed=seed)
    escalation_agent = StubEscalationAgent(seed=seed)

    if CHECK_DB_PATH.exists():
        CHECK_DB_PATH.unlink()  # fresh DB each run — this is a repeatable check, not an accumulating log
    audit_logger = AuditLogger(get_engine(CHECK_DB_PATH))

    detect_at_risk(subsample)  # for the same visibility-only reporting run_system_eval.py does

    case_reports = []
    all_order_ids = []
    for case in subsample:
        result = process_case(case, classifier, retry_executor, escalation_agent, audit_logger)
        events = audit_logger.get_events(case.case_id)
        retry_events = [e for e in events if e["event_type"] == "retry_attempt"]
        order_ids = [e["payload"]["razorpay_order_id"] for e in retry_events if e["payload"].get("razorpay_order_id")]
        all_order_ids.extend(order_ids)

        case_reports.append(
            {
                "case_id": case.case_id,
                "amount_inr": case.context.amount_inr,
                "recovered": result.recovered,
                "recovery_channel": result.recovery_channel,
                "attempts_used": result.attempts_used,
                "razorpay_order_ids": order_ids,
                "raw_razorpay_responses": [e["payload"]["raw_response"] for e in retry_events],
            }
        )
        print(
            f"  {case.case_id:20s} attempts={result.attempts_used} "
            f"recovered={result.recovered} channel={result.recovery_channel} "
            f"orders={order_ids}"
        )

    report = {
        "n_cases": len(subsample),
        "n_real_razorpay_orders_created": len(all_order_ids),
        "all_razorpay_order_ids": all_order_ids,
        "cases": case_reports,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "razorpay_integration_check.json", "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{len(subsample)} cases run against the real Razorpay test-mode API.")
    print(f"{len(all_order_ids)} real orders created: {all_order_ids}")
    print(f"Report written to {REPORTS_DIR / 'razorpay_integration_check.json'}")


if __name__ == "__main__":
    main()
