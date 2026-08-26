"""Aggregate metrics (spec §11) from a list of per-case evaluation results."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.metrics.schema import CaseResult, MetricsReport


def compute_metrics(run_name: str, results: list[CaseResult]) -> MetricsReport:
    eligible = [r for r in results if r.eligible]
    recovered = [r for r in eligible if r.recovered]
    retry_only = [r for r in recovered if r.recovery_channel == "retry"]
    escalation_assisted = [r for r in recovered if r.recovery_channel == "escalation"]
    escalated = [r for r in results if r.escalated]

    rupees_at_risk = sum(r.amount_inr for r in eligible)
    rupees_recovered = sum(r.amount_inr for r in recovered)

    promise_cases = [r for r in results if r.promise_true is not None and r.promise_predicted is not None]
    promise_precision = promise_recall = promise_f1 = None
    if promise_cases:
        tp = sum(1 for r in promise_cases if r.promise_predicted and r.promise_true)
        fp = sum(1 for r in promise_cases if r.promise_predicted and not r.promise_true)
        fn = sum(1 for r in promise_cases if not r.promise_predicted and r.promise_true)
        promise_precision = tp / (tp + fp) if (tp + fp) else 0.0
        promise_recall = tp / (tp + fn) if (tp + fn) else 0.0
        promise_f1 = (
            2 * promise_precision * promise_recall / (promise_precision + promise_recall)
            if (promise_precision + promise_recall)
            else 0.0
        )

    audit_tracked = [r.audit_fields_present for r in results if r.audit_fields_present is not None]

    return MetricsReport(
        run_name=run_name,
        n_cases=len(results),
        rupees_at_risk=rupees_at_risk,
        rupees_recovered=rupees_recovered,
        recovery_rate=(rupees_recovered / rupees_at_risk) if rupees_at_risk else 0.0,
        retry_only_recovered_inr=sum(r.amount_inr for r in retry_only),
        escalation_assisted_recovered_inr=sum(r.amount_inr for r in escalation_assisted),
        promise_precision=promise_precision,
        promise_recall=promise_recall,
        promise_f1=promise_f1,
        guardrail_violations=sum(r.guardrail_violations for r in results),
        avg_attempts_per_recovered=(
            sum(r.attempts_used for r in recovered) / len(recovered) if recovered else None
        ),
        escalation_rate=(len(escalated) / len(results)) if results else 0.0,
        audit_completeness=(sum(audit_tracked) / len(audit_tracked)) if audit_tracked else None,
    )


def compute_uplift(system_report: MetricsReport, baseline_report: MetricsReport) -> float:
    """System recovery rate minus baseline recovery rate, both over the same population."""
    return system_report.recovery_rate - baseline_report.recovery_rate


def save_report(report: MetricsReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report.model_dump(), f, indent=2)


def save_case_results(results: list[CaseResult], path: Path) -> None:
    """Per-case results, not just the aggregate report — needed for slice
    analysis (spec §12 step 8) and for the dashboard's case-level replay view."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")


def load_case_results(path: Path) -> list[CaseResult]:
    with open(path) as f:
        return [CaseResult.model_validate_json(line) for line in f if line.strip()]
