"""Per-case evaluation-run outcome and the aggregate metrics report (spec §11)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class CaseResult(BaseModel):
    case_id: str
    amount_inr: float
    eligible: bool
    recovered: bool
    recovery_channel: Optional[Literal["retry", "escalation"]] = None
    attempts_used: int = 0
    escalated: bool = False
    promise_predicted: Optional[bool] = None
    promise_true: Optional[bool] = None
    guardrail_violations: int = 0
    audit_fields_present: Optional[float] = None  # fraction in [0,1]; None if audit trail not yet wired up


class MetricsReport(BaseModel):
    run_name: str
    n_cases: int
    rupees_at_risk: float
    rupees_recovered: float
    recovery_rate: float
    retry_only_recovered_inr: float
    escalation_assisted_recovered_inr: float
    promise_precision: Optional[float] = None
    promise_recall: Optional[float] = None
    promise_f1: Optional[float] = None
    guardrail_violations: int
    avg_attempts_per_recovered: Optional[float] = None
    escalation_rate: float
    audit_completeness: Optional[float] = None
