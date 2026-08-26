"""Lightweight ML root-cause classifier — a structured *advisory* signal only.

Trained on the dev split's `ground_truth.true_cause`; `predict()` only ever
sees `observed`/`context` fields, never `ground_truth`, at inference time.
Output feeds the policy engine as (predicted_cause, confidence) — it never
authorizes an action itself (spec §8D). Independent accuracy evaluation:
evaluation/experiments/train_diagnosis.py.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from pydantic import BaseModel
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from data.schemas.case_schema import FailureCause, PaymentCase

CATEGORICAL_FEATURES = ["observed_code", "observed_reason", "observed_source", "observed_step", "subscription_state"]
NUMERIC_FEATURES = [
    "attempt_count",
    "time_since_previous_attempt_hours",
    "customer_payment_history_score",
    "instrument_age_days",
    "day_of_month",
    "amount_inr",
]


class DiagnosisPrediction(BaseModel):
    predicted_cause: FailureCause
    confidence: float
    probabilities: dict[str, float]


def case_to_features(case: PaymentCase) -> dict:
    return {
        "observed_code": case.observed.code.value,
        "observed_reason": case.observed.reason,
        "observed_source": case.observed.source.value,
        "observed_step": case.observed.step.value,
        "subscription_state": case.context.subscription_state.value,
        "attempt_count": case.context.attempt_count,
        "time_since_previous_attempt_hours": case.context.time_since_previous_attempt_hours,
        "customer_payment_history_score": case.context.customer_payment_history_score,
        "instrument_age_days": case.context.instrument_age_days,
        "day_of_month": case.context.day_of_month,
        "amount_inr": case.context.amount_inr,
    }


def cases_to_frame(cases: list[PaymentCase]) -> pd.DataFrame:
    return pd.DataFrame([case_to_features(c) for c in cases])


class DiagnosisClassifier:
    def __init__(self, random_state: int = 42):
        self._pipeline = Pipeline(
            [
                (
                    "preprocess",
                    ColumnTransformer(
                        [
                            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
                            ("num", SimpleImputer(strategy="median"), NUMERIC_FEATURES),
                        ]
                    ),
                ),
                ("clf", RandomForestClassifier(n_estimators=300, random_state=random_state)),
            ]
        )
        self._classes: list[str] | None = None

    def fit(self, cases: list[PaymentCase]) -> None:
        X = cases_to_frame(cases)
        y = [c.ground_truth.true_cause.value for c in cases]
        self._pipeline.fit(X, y)
        self._classes = list(self._pipeline.named_steps["clf"].classes_)

    def predict(self, case: PaymentCase) -> DiagnosisPrediction:
        if self._classes is None:
            raise RuntimeError("DiagnosisClassifier.fit() (or .load()) must be called before predict()")
        X = cases_to_frame([case])
        proba = self._pipeline.predict_proba(X)[0]
        probabilities = {cls: float(p) for cls, p in zip(self._classes, proba)}
        best_idx = int(proba.argmax())
        return DiagnosisPrediction(
            predicted_cause=FailureCause(self._classes[best_idx]),
            confidence=float(proba[best_idx]),
            probabilities=probabilities,
        )

    def save(self, path: Path) -> None:
        path = Path(path)
        joblib.dump(self._pipeline, path)
        joblib.dump(self._classes, path.with_suffix(path.suffix + ".classes"))

    def load(self, path: Path) -> None:
        path = Path(path)
        self._pipeline = joblib.load(path)
        self._classes = joblib.load(path.with_suffix(path.suffix + ".classes"))
