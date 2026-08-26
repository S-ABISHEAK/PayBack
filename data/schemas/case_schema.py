"""Schema for a synthetic failed/at-risk recurring-payment case.

Structural split is deliberate: `GroundTruth` is never fed to the diagnosis
classifier or the policy engine as an input feature — it exists only to
drive generation and to compute evaluation metrics. `Observed` and `Context`
are the only fields visible to the diagnosis classifier. See
data/generators/failure_generator.py for how the two are linked with
deliberate noise instead of a lossless lookup.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FailureCause(str, Enum):
    INSUFFICIENT_FUNDS = "insufficient_funds"
    TEMPORARY_BANK_SIDE_FAILURE = "temporary_bank_side_failure"
    MANDATE_LIMIT_RELATED = "mandate_limit_related"
    EXPIRED_INVALID_INSTRUMENT = "expired_invalid_instrument"
    CUSTOMER_DECLINED_INTENTIONAL = "customer_declined_intentional"
    UNKNOWN_AMBIGUOUS = "unknown_ambiguous"


class ErrorCode(str, Enum):
    BAD_REQUEST_ERROR = "BAD_REQUEST_ERROR"
    GATEWAY_ERROR = "GATEWAY_ERROR"


class ErrorSource(str, Enum):
    CUSTOMER = "customer"
    BANK = "bank"
    GATEWAY = "gateway"


class ErrorStep(str, Enum):
    PAYMENT_AUTHENTICATION = "payment_authentication"
    PAYMENT_AUTHORIZATION = "payment_authorization"
    PAYMENT_PROCESSING = "payment_processing"


class SubscriptionState(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    HALTED = "halted"


class RecoveryChannel(str, Enum):
    RETRY = "retry"
    ESCALATION = "escalation"


class GroundTruth(BaseModel):
    """Hidden generation-time truth. Eval-only — never a classifier/policy input."""

    true_cause: FailureCause

    # Synthetic recovery-model parameters (Section 9's "synthetic ground-truth
    # recovery potential") — illustrative, configurable modeling choices for
    # this simulation, not a real-world compliance claim, so NOT an
    # ASSUMPTION: label (that convention is reserved for payment-rail rules).
    retry_success_prob_untargeted: float = Field(
        ge=0, le=1, description="P(success) for an immediate, cause-blind retry — what the naive baseline gets."
    )
    retry_success_prob_targeted: float = Field(
        ge=0, le=1, description="P(success) for a diagnosis-aware, correctly-timed retry."
    )
    escalation_recoverable: bool = Field(
        description="Whether this case can plausibly be recovered via escalation once retry is exhausted."
    )
    escalation_success_prob: float = Field(
        ge=0, le=1, description="P(promise made and fulfilled) if escalated."
    )


class ObservedError(BaseModel):
    """What the diagnosis classifier actually sees — Razorpay's real error shape."""

    code: ErrorCode
    reason: str
    source: ErrorSource
    step: ErrorStep


class PaymentContext(BaseModel):
    subscription_id: str
    customer_id: str
    amount_inr: float = Field(gt=0)
    subscription_state: SubscriptionState
    attempt_count: int = Field(ge=0, description="Failed attempts so far for this payment cycle.")
    previous_outcomes: list[str] = Field(default_factory=list)
    time_since_previous_attempt_hours: Optional[float] = None
    customer_payment_history_score: Optional[float] = Field(
        default=None, ge=0, le=1, description="Proxy signal; nulled on a subset of cases (field dropout)."
    )
    instrument_age_days: Optional[int] = Field(default=None, ge=0)
    day_of_month: int = Field(ge=1, le=28)
    is_retry_eligible: bool
    is_escalation_eligible: bool


class PaymentCase(BaseModel):
    case_id: str
    ground_truth: GroundTruth
    observed: ObservedError
    context: PaymentContext

    # Populated only by an evaluation run, never by the generator.
    final_outcome: Optional[str] = None  # "recovered" | "unrecovered" | None (not yet evaluated)
    recovery_channel: Optional[RecoveryChannel] = None
    attempts_used: int = 0
