"""Slice analysis (spec §12 step 8): recovery rate and uplift broken down by
failure category, amount bucket, and attempt count — not just the single
headline number. Joins the per-case result files (produced by
run_baseline.py / run_system_eval.py) back to the case metadata by case_id.

Usage: python scripts/run_slice_analysis.py
"""

from __future__ import annotations

import json

from data.generators.failure_generator import REPO_ROOT, load_jsonl
from data.generators.split import amount_bucket
from evaluation.metrics.compute import compute_metrics, load_case_results

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"


def _attempt_bucket(attempt_count: int) -> str:
    return str(attempt_count) if attempt_count < 4 else "4+"


SLICE_DIMENSIONS = {
    "failure_category": lambda case: case.ground_truth.true_cause.value,
    "amount_bucket": lambda case: amount_bucket(case.context.amount_inr),
    "attempt_count": lambda case: _attempt_bucket(case.context.attempt_count),
}


def _slice_report(cases_by_id: dict, results: list, dimension_fn) -> dict:
    groups: dict[str, list] = {}
    for r in results:
        case = cases_by_id.get(r.case_id)
        if case is None:
            continue
        groups.setdefault(dimension_fn(case), []).append(r)

    result = {}
    for slice_value, slice_results in sorted(groups.items()):
        m = compute_metrics("slice", slice_results)
        result[slice_value] = {
            "n_cases": len(slice_results),
            "rupees_at_risk": m.rupees_at_risk,
            "rupees_recovered": m.rupees_recovered,
            "recovery_rate": m.recovery_rate,
        }
    return result


def main() -> None:
    cases_by_id = {c.case_id: c for c in load_jsonl(SAMPLES_DIR / "cases.jsonl")}

    baseline_path = REPORTS_DIR / "baseline_case_results.jsonl"
    system_path = REPORTS_DIR / "system_case_results.jsonl"
    if not baseline_path.exists() or not system_path.exists():
        raise SystemExit(
            "Missing per-case result files. Run scripts/run_baseline_eval.py and "
            "scripts/run_system_eval.py first (both now save *_case_results.jsonl)."
        )

    baseline_results = load_case_results(baseline_path)
    system_results = load_case_results(system_path)

    report = {}
    for dim_name, dim_fn in SLICE_DIMENSIONS.items():
        baseline_slices = _slice_report(cases_by_id, baseline_results, dim_fn)
        system_slices = _slice_report(cases_by_id, system_results, dim_fn)
        combined = {}
        for slice_value in sorted(set(baseline_slices) | set(system_slices)):
            b = baseline_slices.get(slice_value, {"n_cases": 0, "recovery_rate": 0.0})
            s = system_slices.get(slice_value, {"n_cases": 0, "recovery_rate": 0.0})
            combined[slice_value] = {
                "n_cases": s.get("n_cases", 0),
                "baseline_recovery_rate": b["recovery_rate"],
                "system_recovery_rate": s["recovery_rate"],
                "uplift": s["recovery_rate"] - b["recovery_rate"],
            }
        report[dim_name] = combined

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "slice_analysis_report.json", "w") as f:
        json.dump(report, f, indent=2)

    for dim_name, slices in report.items():
        print(f"\n{dim_name}:")
        for slice_value, m in slices.items():
            print(
                f"  {slice_value:28s} n={m['n_cases']:4d}  "
                f"baseline={m['baseline_recovery_rate']:6.1%}  "
                f"system={m['system_recovery_rate']:6.1%}  "
                f"uplift={m['uplift']:+6.1%}"
            )
    print(f"\nReport written to {REPORTS_DIR / 'slice_analysis_report.json'}")


if __name__ == "__main__":
    main()
