"""Retry executor interface, with a stub (offline, deterministic) and a real
Razorpay test-mode implementation, selected via the RETRY_EXECUTOR env var so
Phase 1-2 development and unit tests never depend on external account setup.

ASSUMPTION (see configs/recovery_rules/retry_execution.yaml:execution_model):
Razorpay's public server-side API exposes no way to force a live
subscription's auto-charge to retry/fail on demand, and unrestricted
server-to-server card charges require special account approval most
merchants don't have. RazorpayTestModeRetryExecutor therefore makes a real,
always-available, unambiguous server-side call — creating a fresh Razorpay
Order (`client.order.create`) for the case's amount, tagged with the
diagnosed reason — as concrete evidence of hitting Razorpay's real test-mode
rails (real order_id, real API auth, real response), while the
success/failure *outcome* is still drawn from the same synthetic
probability model StubRetryExecutor uses, since fully driving a completed
card charge needs a client-side checkout flow this batch evaluator doesn't
run. Both the real order_id and the synthetic outcome are logged, never
conflated as if the order itself proves payment success.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel

from data.generators.failure_generator import RETRY_DECAY_FACTOR, decayed_prob, stable_rng
from data.schemas.case_schema import PaymentCase


class RetryResult(BaseModel):
    success: bool
    razorpay_order_id: Optional[str] = None
    raw_response: Optional[dict] = None
    reason: Optional[str] = None


class RetryExecutor(ABC):
    @abstractmethod
    def execute_retry(self, case: PaymentCase, attempt_number: int, targeted: bool = True) -> RetryResult: ...


class StubRetryExecutor(RetryExecutor):
    """Deterministic, seeded from the case's synthetic ground truth — no
    network call. Used for all development, unit tests, and any batch run
    where RETRY_EXECUTOR is unset.

    Each call gets its own RNG keyed by (seed, case_id, attempt_number) —
    deliberately NOT a single `random.Random(seed)` shared and consumed
    sequentially across a case list, which would make the outcome depend on
    case processing order (see data.generators.failure_generator.stable_rng)."""

    def __init__(self, seed: int = 42):
        self._seed = seed

    def execute_retry(self, case: PaymentCase, attempt_number: int, targeted: bool = True) -> RetryResult:
        base_prob = (
            case.ground_truth.retry_success_prob_targeted
            if targeted
            else case.ground_truth.retry_success_prob_untargeted
        )
        prob = decayed_prob(base_prob, n_prior_attempts=attempt_number - 1, decay_factor=RETRY_DECAY_FACTOR)
        rng = stable_rng(self._seed, case.case_id, attempt_number)
        success = rng.random() < prob
        return RetryResult(success=success, reason=None if success else case.observed.reason)


class RazorpayTestModeRetryExecutor(RetryExecutor):
    def __init__(self, key_id: str, key_secret: str, seed: int = 42):
        import razorpay  # deferred import: only required when this executor is actually used

        self._client = razorpay.Client(auth=(key_id, key_secret))
        self._seed = seed

    def execute_retry(self, case: PaymentCase, attempt_number: int, targeted: bool = True) -> RetryResult:
        order = self._client.order.create(
            {
                "amount": int(round(case.context.amount_inr * 100)),  # paise
                "currency": "INR",
                "receipt": f"{case.case_id}_attempt_{attempt_number}",
                "notes": {"case_id": case.case_id, "diagnosed_reason": case.observed.reason},
            }
        )
        base_prob = (
            case.ground_truth.retry_success_prob_targeted
            if targeted
            else case.ground_truth.retry_success_prob_untargeted
        )
        prob = decayed_prob(base_prob, n_prior_attempts=attempt_number - 1, decay_factor=RETRY_DECAY_FACTOR)
        rng = stable_rng(self._seed, case.case_id, attempt_number)
        success = rng.random() < prob
        return RetryResult(
            success=success,
            razorpay_order_id=order.get("id"),
            raw_response=order,
            reason=None if success else case.observed.reason,
        )


def get_retry_executor(seed: int = 42) -> RetryExecutor:
    backend = os.environ.get("RETRY_EXECUTOR", "stub")
    if backend == "stub":
        return StubRetryExecutor(seed=seed)
    if backend == "razorpay_test":
        key_id = os.environ["RAZORPAY_KEY_ID"]
        key_secret = os.environ["RAZORPAY_KEY_SECRET"]
        return RazorpayTestModeRetryExecutor(key_id=key_id, key_secret=key_secret, seed=seed)
    raise ValueError(f"Unknown RETRY_EXECUTOR backend: {backend!r} (expected 'stub' or 'razorpay_test')")
