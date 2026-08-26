"""Evaluates the promise extractor's has_promise precision/recall/F1 against
the Phase 3 dialogue scenario set's ground truth. Runs on the scenario's
scripted customer turns directly (not a live agent conversation) — the
extractor only ever reads customer-side text, so this evaluates the
extractor itself independent of which escalation agent is in use, matching
spec §12's requirement for independent evaluation of AI components.

Usage: python scripts/evaluate_promise_extraction.py [--backend rule_based]
"""

from __future__ import annotations

import argparse
import json

from sklearn.metrics import precision_recall_fscore_support

from data.generators.failure_generator import REPO_ROOT
from data.generators.hinglish_dialogue_generator import load_jsonl
from src.promise.extractor import LLMPromiseExtractor, RuleBasedPromiseExtractor

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"


def main(backend: str = "rule_based") -> None:
    scenarios_path = SAMPLES_DIR / "dialogue_scenarios.jsonl"
    if not scenarios_path.exists():
        raise SystemExit("No dialogue scenarios found. Run scripts/generate_dialogue_scenarios.py first.")
    scenarios = load_jsonl(scenarios_path)

    extractor = RuleBasedPromiseExtractor() if backend == "rule_based" else LLMPromiseExtractor()

    y_true, y_pred = [], []
    per_scenario = []
    for s in scenarios:
        transcript = [{"role": "customer", "text": line} for line in s.scripted_customer_turns]
        prediction = extractor.extract(transcript, fallback_amount_inr=s.amount_inr)
        y_true.append(s.ground_truth.has_promise)
        y_pred.append(prediction.has_promise)
        per_scenario.append(
            {
                "scenario_id": s.scenario_id,
                "category": s.category,
                "true_has_promise": s.ground_truth.has_promise,
                "predicted_has_promise": prediction.has_promise,
                "predicted_amount_inr": prediction.promised_amount_inr,
                "true_amount_inr": s.ground_truth.promised_amount_inr,
                "predicted_date_offset_days": prediction.promised_date_offset_days,
                "true_date_offset_days": s.ground_truth.promised_date_offset_days,
                "confidence": prediction.confidence,
                "correct": prediction.has_promise == s.ground_truth.has_promise,
            }
        )

    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)

    # Secondary diagnostic: amount/date accuracy conditional on a correctly
    # detected true positive — not the headline metric, but worth reporting.
    true_positives = [r for r in per_scenario if r["true_has_promise"] and r["predicted_has_promise"]]
    amount_matches = sum(1 for r in true_positives if r["predicted_amount_inr"] == r["true_amount_inr"])
    date_matches = sum(
        1 for r in true_positives if r["predicted_date_offset_days"] == r["true_date_offset_days"]
    )

    report = {
        "backend": backend,
        "n_scenarios": len(scenarios),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "amount_accuracy_given_true_positive": (amount_matches / len(true_positives)) if true_positives else None,
        "date_accuracy_given_true_positive": (date_matches / len(true_positives)) if true_positives else None,
        "per_scenario": per_scenario,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "promise_extraction_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"Promise extraction ({backend}) over {len(scenarios)} scenarios:")
    print(f"  Precision: {precision:.2%}")
    print(f"  Recall:    {recall:.2%}")
    print(f"  F1:        {f1:.2%}")
    print(f"  Amount accuracy (given correct promise detection): {report['amount_accuracy_given_true_positive']}")
    print(f"  Date accuracy (given correct promise detection):   {report['date_accuracy_given_true_positive']}")
    print(f"  Report written to {REPORTS_DIR / 'promise_extraction_report.json'}")

    misses = [r for r in per_scenario if not r["correct"]]
    if misses:
        print(f"\n  Misclassified ({len(misses)}):")
        for m in misses:
            print(f"    {m['scenario_id']:32s} true={m['true_has_promise']} pred={m['predicted_has_promise']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["rule_based", "llm"], default="rule_based")
    args = parser.parse_args()
    main(backend=args.backend)
