"""Trains the diagnosis classifier on the dev split, evaluates independently
on the held-out split (never seen during fit), and writes both the model and
a confusion-matrix report. Target accuracy band is 70-85% by design (see
data/generators/failure_generator.py's leakage mitigation) — a much higher
number would indicate the observed features are leaking the label.
"""

from __future__ import annotations

import json

from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from data.generators.failure_generator import REPO_ROOT, load_jsonl
from data.generators.split import load_ids
from src.diagnosis.classifier import DiagnosisClassifier

SAMPLES_DIR = REPO_ROOT / "data" / "samples"
MODELS_DIR = REPO_ROOT / "models" / "diagnosis"
REPORTS_DIR = REPO_ROOT / "evaluation" / "reports"


def main(seed: int = 42) -> None:
    all_cases = {c.case_id: c for c in load_jsonl(SAMPLES_DIR / "cases.jsonl")}
    dev_cases = [all_cases[cid] for cid in sorted(load_ids(SAMPLES_DIR / "dev_case_ids.txt"))]
    holdout_cases = [all_cases[cid] for cid in sorted(load_ids(SAMPLES_DIR / "holdout_case_ids.txt"))]

    clf = DiagnosisClassifier(random_state=seed)
    clf.fit(dev_cases)

    y_true = [c.ground_truth.true_cause.value for c in holdout_cases]
    predictions = [clf.predict(c) for c in holdout_cases]
    y_pred = [p.predicted_cause.value for p in predictions]
    confidences = [p.confidence for p in predictions]

    accuracy = accuracy_score(y_true, y_pred)
    labels = sorted(set(y_true) | set(y_pred))
    report = {
        "accuracy": accuracy,
        "avg_confidence": sum(confidences) / len(confidences),
        "n_dev": len(dev_cases),
        "n_holdout": len(holdout_cases),
        "classification_report": classification_report(y_true, y_pred, output_dict=True, zero_division=0),
        "confusion_matrix": {"labels": labels, "matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist()},
    }

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    clf.save(MODELS_DIR / "classifier.joblib")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "diagnosis_classifier_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print(f"Diagnosis classifier accuracy on held-out ({len(holdout_cases)} cases): {accuracy:.1%}")
    print(f"Average confidence: {report['avg_confidence']:.2f}")
    print(f"Model saved to {MODELS_DIR / 'classifier.joblib'}")
    print(f"Report saved to {REPORTS_DIR / 'diagnosis_classifier_report.json'}")


if __name__ == "__main__":
    main()
