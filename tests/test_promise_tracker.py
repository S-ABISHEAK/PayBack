import pytest

from src.promise.extractor import PromiseExtraction
from src.promise.tracker import PromiseStatus, PromiseTracker


def test_open_promise_from_extraction():
    tracker = PromiseTracker(seed=1)
    extraction = PromiseExtraction(has_promise=True, promised_amount_inr=500, promised_date_offset_days=3, confidence=0.8)
    promise = tracker.open_promise("case_1", extraction)
    assert promise.status == PromiseStatus.PENDING
    assert promise.promised_amount_inr == 500


def test_cannot_open_promise_without_has_promise():
    tracker = PromiseTracker(seed=1)
    extraction = PromiseExtraction(has_promise=False, confidence=0.8)
    with pytest.raises(ValueError):
        tracker.open_promise("case_1", extraction)


def test_evaluate_followup_resolves_to_fulfilled_or_broken():
    tracker = PromiseTracker(seed=1)
    extraction = PromiseExtraction(has_promise=True, promised_amount_inr=500, promised_date_offset_days=1, confidence=0.8)
    promise = tracker.open_promise("case_1", extraction)
    resolved = tracker.evaluate_followup(promise, fulfillment_prob=0.9)
    assert resolved.status in (PromiseStatus.FULFILLED, PromiseStatus.BROKEN)


def test_evaluate_followup_deterministic_with_same_seed():
    extraction = PromiseExtraction(has_promise=True, promised_amount_inr=500, promised_date_offset_days=1, confidence=0.8)
    t1 = PromiseTracker(seed=7)
    t2 = PromiseTracker(seed=7)
    p1 = t1.evaluate_followup(t1.open_promise("case_1", extraction), fulfillment_prob=0.5)
    p2 = t2.evaluate_followup(t2.open_promise("case_1", extraction), fulfillment_prob=0.5)
    assert p1.status == p2.status


def test_cannot_evaluate_followup_twice():
    tracker = PromiseTracker(seed=1)
    extraction = PromiseExtraction(has_promise=True, promised_amount_inr=500, confidence=0.8)
    promise = tracker.open_promise("case_1", extraction)
    resolved = tracker.evaluate_followup(promise, fulfillment_prob=0.5)
    with pytest.raises(ValueError):
        tracker.evaluate_followup(resolved, fulfillment_prob=0.5)
