"""Runs the full recovery system (detection -> diagnosis -> policy ->
guardrails -> retry/escalate -> audit) over the exact same held-out
population the naive baseline ran over, and writes a comparable report plus
the uplift. This is the number the pitch's headline uplift claim comes from.

Usage: python scripts/run_system_eval.py [--seed 42]
"""

from __future__ import annotations

import argparse

from data.generators.failure_generator import REPO_ROOT, load_jsonl
from data.generators.split import load_ids
from evaluation.metrics.compute import compute_metrics, compute_uplift, save_case_results, save_report
from evaluation.metrics.schema import MetricsReport
from src.audit.db import get_engine
from src.audit.logger import AuditLogger
from src.detection.detector import detect_at_risk
from src.diagnosis.classifier import DiagnosisClassifier
from src.escalation.agent import get_escalation_agent
from src.orchestration.state_machine import process_case
from src.retry.executor import get_retry_executor

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
MODELS_DIR = REPO_ROOT / "models" / "diagnosis"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"


def main(seed: int = 42) -> None:
    all_cases = {c.case_id: c for c in load_jsonl(SAMPLES_DIR / "cases.jsonl")}
    holdout_ids = load_ids(SAMPLES_DIR / "holdout_case_ids.txt")
    holdout_cases = [all_cases[cid] for cid in sorted(holdout_ids)]

    # Detection is a distinct pipeline stage (spec: DETECT -> DIAGNOSE -> ...);
    # process_case() independently re-derives the same eligibility internally
    # (defense in depth, and keeps it usable standalone from replay_case.py),
    # so every held-out case still gets a CaseResult regardless of this
    # count — it's reported for visibility, not used to filter what's run.
    at_risk_cases = detect_at_risk(holdout_cases)
    print(f"Detection: {len(at_risk_cases)}/{len(holdout_cases)} held-out cases flagged at-risk.")

    classifier = DiagnosisClassifier(random_state=seed)
    classifier.load(MODELS_DIR / "classifier.joblib")

    retry_executor = get_retry_executor(seed=seed)
    escalation_agent = get_escalation_agent(seed=seed)
    audit_logger = AuditLogger(get_engine())

    results = [
        process_case(case, classifier, retry_executor, escalation_agent, audit_logger) for case in holdout_cases
    ]

    system_report = compute_metrics("system", results)
    save_report(system_report, REPORTS_DIR / "system_report.json")
    save_case_results(results, REPORTS_DIR / "system_case_results.jsonl")

    print(f"System over {system_report.n_cases} held-out cases:")
    print(f"  Rupees at risk:     {system_report.rupees_at_risk:,.2f}")
    print(f"  Rupees recovered:   {system_report.rupees_recovered:,.2f}")
    print(f"  Recovery rate:      {system_report.recovery_rate:.2%}")
    print(f"  Retry-only ₹:       {system_report.retry_only_recovered_inr:,.2f}")
    print(f"  Escalation-assist ₹:{system_report.escalation_assisted_recovered_inr:,.2f}")
    print(f"  Escalation rate:    {system_report.escalation_rate:.2%}")
    print(f"  Guardrail violations: {system_report.guardrail_violations}")

    baseline_path = REPORTS_DIR / "baseline_report.json"
    if baseline_path.exists():
        baseline_report = MetricsReport.model_validate_json(baseline_path.read_text())
        uplift = compute_uplift(system_report, baseline_report)
        print(f"\n  Baseline recovery rate: {baseline_report.recovery_rate:.2%}")
        print(f"  System recovery rate:   {system_report.recovery_rate:.2%}")
        print(f"  Uplift:                 {uplift:+.2%}")
    else:
        print("\n  (No baseline_report.json found — run scripts/run_baseline_eval.py first for uplift.)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(seed=args.seed)
