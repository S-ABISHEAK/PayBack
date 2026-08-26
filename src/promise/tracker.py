"""Follow-up state transitions for an extracted promise-to-pay (spec §6
step 7: "Track eligible promises and evaluate whether the promised payment
is fulfilled"). A promise starts PENDING when extracted; evaluate_followup()
resolves it to FULFILLED or BROKEN once the promised date has passed.

Since this is a synthetic batch system with no real elapsed time or live
payment feed, the follow-up outcome is drawn from the same ground-truth
probabilistic model the rest of the system uses for simulated results
(never a live payment check) — the caller supplies `fulfillment_prob`,
typically the case's own ground_truth.escalation_success_prob.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from data.generators.failure_generator import stable_rng
from src.promise.extractor import PromiseExtraction


class PromiseStatus(str, Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    BROKEN = "broken"


class TrackedPromise(BaseModel):
    case_id: str
    promised_amount_inr: Optional[float] = None
    promised_date_offset_days: Optional[int] = None
    extraction_confidence: float
    status: PromiseStatus = PromiseStatus.PENDING


class PromiseTracker:
    """Each evaluate_followup() call gets its own RNG keyed by (seed, case_id)
    rather than a shared sequential `random.Random(seed)` — see
    data.generators.failure_generator.stable_rng for why that matters once
    this is driven from a batch of cases rather than one at a time."""

    def __init__(self, seed: int = 42):
        self._seed = seed

    def open_promise(self, case_id: str, extraction: PromiseExtraction) -> TrackedPromise:
        if not extraction.has_promise:
            raise ValueError("Cannot open a tracked promise from an extraction with has_promise=False")
        return TrackedPromise(
            case_id=case_id,
            promised_amount_inr=extraction.promised_amount_inr,
            promised_date_offset_days=extraction.promised_date_offset_days,
            extraction_confidence=extraction.confidence,
            status=PromiseStatus.PENDING,
        )

    def evaluate_followup(self, promise: TrackedPromise, fulfillment_prob: float) -> TrackedPromise:
        if promise.status != PromiseStatus.PENDING:
            raise ValueError(f"Promise for {promise.case_id} is already resolved ({promise.status.value})")
        rng = stable_rng(self._seed, promise.case_id)
        fulfilled = rng.random() < fulfillment_prob
        return promise.model_copy(update={"status": PromiseStatus.FULFILLED if fulfilled else PromiseStatus.BROKEN})
