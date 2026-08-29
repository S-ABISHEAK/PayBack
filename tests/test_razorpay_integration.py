"""Live integration test against Razorpay's real test-mode API — skipped
automatically when no keys are configured (e.g. CI, a fresh clone) rather
than failing, since this is the one component that genuinely needs an
external account. See evaluation/experiments/verify_razorpay_integration.py
for the fuller end-to-end orchestrator check this doesn't replace."""

import os

import pytest

from src.retry.executor import RazorpayTestModeRetryExecutor
from tests.factories import make_case

_HAS_KEYS = bool(os.environ.get("RAZORPAY_KEY_ID")) and bool(os.environ.get("RAZORPAY_KEY_SECRET"))

pytestmark = pytest.mark.skipif(not _HAS_KEYS, reason="RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not set")


def _executor() -> RazorpayTestModeRetryExecutor:
    return RazorpayTestModeRetryExecutor(
        key_id=os.environ["RAZORPAY_KEY_ID"],
        key_secret=os.environ["RAZORPAY_KEY_SECRET"],
    )


def test_execute_retry_creates_a_real_razorpay_order():
    case = make_case("razorpay_it_case_1", seed=5)
    result = _executor().execute_retry(case, attempt_number=1)

    assert result.razorpay_order_id is not None
    assert result.razorpay_order_id.startswith("order_")
    assert result.raw_response["entity"] == "order"
    assert result.raw_response["status"] == "created"
    assert result.raw_response["amount"] == int(round(case.context.amount_inr * 100))
    assert result.raw_response["currency"] == "INR"


def test_execute_retry_outcome_is_still_the_same_deterministic_synthetic_model():
    """The order itself is real, but the success/failure OUTCOME is still
    drawn from the same synthetic probability model StubRetryExecutor uses
    (documented ASSUMPTION in src/retry/executor.py) — confirms the two
    executors agree on outcome for the same case/attempt, so swapping
    RETRY_EXECUTOR never silently changes what "success" means."""
    from src.retry.executor import StubRetryExecutor

    case = make_case("razorpay_it_case_2", seed=7)
    real_result = _executor().execute_retry(case, attempt_number=1)
    stub_result = StubRetryExecutor().execute_retry(case, attempt_number=1)

    assert real_result.success == stub_result.success
