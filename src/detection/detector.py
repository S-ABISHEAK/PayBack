"""Detection: filters a batch to the cases that still have some eligible
intervention (retry or escalation). Every generated case already represents
a failed/at-risk payment (see data/generators/failure_generator.py) — this
module's job is separating "still actionable" from "already exhausted both
channels," not classifying failure vs. success."""

from __future__ import annotations

from data.schemas.case_schema import PaymentCase


def detect_at_risk(cases: list[PaymentCase]) -> list[PaymentCase]:
    return [c for c in cases if c.context.is_retry_eligible or c.context.is_escalation_eligible]
