"""Runs the naive baseline over the frozen held-out split and writes a report.

Usage: python scripts/run_baseline_eval.py [--seed 42]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from data.generators.failure_generator import load_jsonl
from data.generators.split import load_ids
from evaluation.baselines.naive_retry import run_naive_baseline
from evaluation.metrics.compute import compute_metrics, save_case_results, save_report

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"


def main(seed: int = 42) -> None:
    all_cases = {c.case_id: c for c in load_jsonl(SAMPLES_DIR / "cases.jsonl")}
    holdout_ids = load_ids(SAMPLES_DIR / "holdout_case_ids.txt")
    holdout_cases = [all_cases[cid] for cid in sorted(holdout_ids)]

    results = run_naive_baseline(holdout_cases, seed=seed)
    report = compute_metrics("naive_baseline", results)
    save_report(report, REPORTS_DIR / "baseline_report.json")
    save_case_results(results, REPORTS_DIR / "baseline_case_results.jsonl")

    print(f"Naive baseline over {report.n_cases} held-out cases:")
    print(f"  Rupees at risk:     {report.rupees_at_risk:,.2f}")
    print(f"  Rupees recovered:   {report.rupees_recovered:,.2f}")
    print(f"  Recovery rate:      {report.recovery_rate:.2%}")
    print(f"  Report written to:  {REPORTS_DIR / 'baseline_report.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    main(seed=args.seed)
