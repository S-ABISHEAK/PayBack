"""Pure data-loading / assembly functions for the dashboard.

No FastAPI imports here on purpose — everything below is independently
callable (``python -c "from frontend.loaders import build_overview; ..."``)
and returns plain JSON-serialisable dicts/lists. All of the report-reading
logic that used to live in the body of the old ``apps/dashboard/app.py``
Streamlit script is ported here, with the same "the file might not exist yet,
degrade to ``None``" behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from data.generators.failure_generator import load_jsonl
from data.generators.split import load_ids
from evaluation.metrics.compute import load_case_results
from src.audit.db import get_engine
from src.audit.logger import AuditLogger

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"
DB_PATH = REPO_ROOT / "data" / "recovery.db"

CASES_PATH = SAMPLES_DIR / "cases.jsonl"
HOLDOUT_IDS_PATH = SAMPLES_DIR / "holdout_case_ids.txt"
SYSTEM_RESULTS_PATH = REPORTS_DIR / "system_case_results.jsonl"


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# Case dataset + system results (shared by the overview and per-case views)
# --------------------------------------------------------------------------- #

def load_cases() -> dict:
    """Returns {case_id: PaymentCase}. Raises FileNotFoundError if the dataset
    has never been generated — the caller turns that into a friendly message."""
    if not CASES_PATH.exists():
        raise FileNotFoundError(
            "No dataset found. Run `python scripts/generate_dataset.py --seed 42` first."
        )
    return {c.case_id: c for c in load_jsonl(CASES_PATH)}


def load_holdout_ids() -> set[str]:
    return load_ids(HOLDOUT_IDS_PATH) if HOLDOUT_IDS_PATH.exists() else set()


def load_system_results() -> dict:
    if not SYSTEM_RESULTS_PATH.exists():
        return {}
    return {r.case_id: r for r in load_case_results(SYSTEM_RESULTS_PATH)}


def _case_row(case, holdout_ids: set[str], system_results: dict) -> dict:
    r = system_results.get(case.case_id)
    return {
        "case_id": case.case_id,
        "amount_inr": case.context.amount_inr,
        "subscription_state": case.context.subscription_state.value,
        "attempt_count": case.context.attempt_count,
        "observed_reason": case.observed.reason,
        "is_retry_eligible": case.context.is_retry_eligible,
        "is_escalation_eligible": case.context.is_escalation_eligible,
        "split": "held-out" if case.case_id in holdout_ids else "dev",
        # ground truth exposed only because this is a build-time view over the
        # generator's own output, never a model input.
        "true_cause": case.ground_truth.true_cause.value,
        "recovered": r.recovered if r else None,
        "recovery_channel": r.recovery_channel if r else None,
        "guardrail_violations": r.guardrail_violations if r else None,
    }


# --------------------------------------------------------------------------- #
# Overview payload
# --------------------------------------------------------------------------- #

def _comparison() -> Optional[dict]:
    baseline = _read_json(REPORTS_DIR / "baseline_report.json")
    system = _read_json(REPORTS_DIR / "system_report.json")
    if not baseline or not system:
        return None
    return {
        "rupees_at_risk": system["rupees_at_risk"],
        "baseline_recovery_rate": baseline["recovery_rate"],
        "system_recovery_rate": system["recovery_rate"],
        "uplift": system["recovery_rate"] - baseline["recovery_rate"],
        "retry_only_recovered_inr": system["retry_only_recovered_inr"],
        "escalation_assisted_recovered_inr": system["escalation_assisted_recovered_inr"],
        "escalation_rate": system["escalation_rate"],
        "guardrail_violations": system["guardrail_violations"],
    }


def _promise_extraction() -> Optional[dict]:
    report = _read_json(REPORTS_DIR / "promise_extraction_report.json")
    if not report:
        return None
    return {
        "precision": report["precision"],
        "recall": report["recall"],
        "f1": report["f1"],
        "backend": report["backend"],
    }


# (file on disk, human label) for the 5-point rubric progression. `.groq_prompted`
# runs are averaged; `.groq_prompted.json` / `.hard.json` are deliberately excluded
# (duplicate of run3, and the separate 12-scenario stress test, respectively).
_RUBRIC_PROGRESSION = [
    ("escalation_rubric_report.pre_fewshot.json", "qwen2.5:3b, zero-shot"),
    ("escalation_rubric_report.3b_fewshot.json", "qwen2.5:3b, few-shot"),
    ("escalation_rubric_report.7b_fewshot.json", "qwen2.5:7b, untuned"),
    ("escalation_rubric_report.json", "qwen2.5:7b, tuned (local default)"),
]
_GROQ_RUN_FILES = [
    "escalation_rubric_report.groq_prompted.run1.json",
    "escalation_rubric_report.groq_prompted.run2.json",
    "escalation_rubric_report.groq_prompted.run3.json",
]
_CRITERIA = ("tone_naturalness", "task_success", "code_switch_quality", "overall")


def _mean_scores_across(files: list[str]) -> Optional[dict]:
    reports = [_read_json(REPORTS_DIR / f) for f in files]
    reports = [r for r in reports if r]
    if not reports:
        return None
    return {
        c: sum(r["mean_scores"][c] for r in reports) / len(reports) for c in _CRITERIA
    }


def _rubric_progression() -> Optional[list[dict]]:
    rows: list[dict] = []
    for fname, label in _RUBRIC_PROGRESSION:
        report = _read_json(REPORTS_DIR / fname)
        if not report:
            continue
        rows.append(
            {
                "label": label,
                "overall": report["mean_scores"]["overall"],
                "source_file": fname,
                "current": fname == "escalation_rubric_report.json",
            }
        )
    groq = _mean_scores_across(_GROQ_RUN_FILES)
    if groq:
        rows.append(
            {
                "label": "qwen/qwen3.8-27b via Groq (n=3 runs)",
                "overall": groq["overall"],
                "source_file": "escalation_rubric_report.groq_prompted.run{1,2,3}.json",
                "current": False,
            }
        )
    return rows or None


def _rubric_comparison() -> Optional[dict]:
    local = _read_json(REPORTS_DIR / "escalation_rubric_report.json")
    groq = _mean_scores_across(_GROQ_RUN_FILES)
    if not local and not groq:
        return None
    return {
        "local": {c: local["mean_scores"][c] for c in _CRITERIA} if local else None,
        "groq": groq,
    }


def _judge_discrimination() -> Optional[dict]:
    report = _read_json(REPORTS_DIR / "judge_discrimination_check.json")
    if not report:
        return None
    return {
        "judge_model": report["judge_model"],
        "n_corruption_cases": report["n_corruption_cases"],
        "mean_overall_score_drop": report["mean_overall_score_drop"],
    }


def _razorpay_integration() -> Optional[dict]:
    report = _read_json(REPORTS_DIR / "razorpay_integration_check.json")
    if not report:
        return None
    return {
        "n_cases": report["n_cases"],
        "n_real_razorpay_orders_created": report["n_real_razorpay_orders_created"],
        "cases": [
            {
                "case_id": c["case_id"],
                "amount_inr": c["amount_inr"],
                "recovered": c["recovered"],
                "recovery_channel": c["recovery_channel"],
                "attempts_used": c["attempts_used"],
                "razorpay_order_ids": c["razorpay_order_ids"],
            }
            for c in report["cases"]
        ],
    }


def build_overview(current_model_backend: str) -> dict:
    cases = load_cases()
    holdout_ids = load_holdout_ids()
    system_results = load_system_results()

    rows = [_case_row(c, holdout_ids, system_results) for c in cases.values()]
    total_amount = sum(r["amount_inr"] for r in rows)

    return {
        "totals": {
            "total_cases": len(rows),
            "holdout_cases": sum(1 for r in rows if r["split"] == "held-out"),
            "total_amount_inr": total_amount,
        },
        "cases": rows,
        "system_results_loaded": bool(system_results),
        "system_results_count": len(system_results),
        "comparison": _comparison(),
        "slices": _read_json(REPORTS_DIR / "slice_analysis_report.json"),
        "promise_extraction": _promise_extraction(),
        "rubric_progression": _rubric_progression(),
        "rubric_comparison": _rubric_comparison(),
        "judge_discrimination": _judge_discrimination(),
        "razorpay_integration": _razorpay_integration(),
        "current_model_backend": current_model_backend,
    }


# --------------------------------------------------------------------------- #
# Per-case payload
# --------------------------------------------------------------------------- #

def build_case_detail(case_id: str) -> Optional[dict]:
    cases = load_cases()
    case = cases.get(case_id)
    if case is None:
        return None

    system_results = load_system_results()
    r = system_results.get(case_id)

    audit_events: list[dict] = []
    latest_promise = None
    if DB_PATH.exists():
        logger = AuditLogger(get_engine(DB_PATH))
        events = logger.get_events(case_id)
        audit_events = [
            {
                "id": e["id"],
                "event_type": e["event_type"],
                "payload": e["payload"],
                "created_at": e["created_at"],
            }
            for e in events
        ]
        promise_events = [e for e in events if e["event_type"] == "promise_extraction"]
        if promise_events:
            latest_promise = promise_events[-1]["payload"]

    return {
        "case_id": case.case_id,
        "amount_inr": case.context.amount_inr,
        "subscription_state": case.context.subscription_state.value,
        "attempt_count": case.context.attempt_count,
        "is_retry_eligible": case.context.is_retry_eligible,
        "is_escalation_eligible": case.context.is_escalation_eligible,
        "observed": {
            "code": case.observed.code.value,
            "reason": case.observed.reason,
            "source": case.observed.source.value,
            "step": case.observed.step.value,
        },
        "true_cause": case.ground_truth.true_cause.value,
        "system_result": (
            {
                "recovered": r.recovered,
                "recovery_channel": r.recovery_channel,
                "guardrail_violations": r.guardrail_violations,
            }
            if r
            else None
        ),
        "audit_events": audit_events,
        "latest_promise": latest_promise,
    }
