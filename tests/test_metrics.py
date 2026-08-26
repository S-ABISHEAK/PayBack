from evaluation.metrics.compute import compute_metrics, compute_uplift
from evaluation.metrics.schema import CaseResult


def _result(**overrides) -> CaseResult:
    base = dict(case_id="c1", amount_inr=1000.0, eligible=True, recovered=False)
    base.update(overrides)
    return CaseResult(**base)


def test_basic_recovery_rate():
    results = [
        _result(case_id="a", amount_inr=1000, eligible=True, recovered=True, recovery_channel="retry", attempts_used=1),
        _result(case_id="b", amount_inr=500, eligible=True, recovered=False),
        _result(case_id="c", amount_inr=2000, eligible=False, recovered=False),
    ]
    report = compute_metrics("test_run", results)
    assert report.rupees_at_risk == 1500  # only eligible cases
    assert report.rupees_recovered == 1000
    assert report.recovery_rate == 1000 / 1500
    assert report.retry_only_recovered_inr == 1000
    assert report.escalation_assisted_recovered_inr == 0


def test_promise_precision_recall_f1():
    results = [
        _result(case_id="a", promise_predicted=True, promise_true=True),   # TP
        _result(case_id="b", promise_predicted=True, promise_true=False),  # FP
        _result(case_id="c", promise_predicted=False, promise_true=True),  # FN
        _result(case_id="d", promise_predicted=False, promise_true=False),  # TN
    ]
    report = compute_metrics("test_run", results)
    assert report.promise_precision == 0.5
    assert report.promise_recall == 0.5
    assert report.promise_f1 == 0.5


def test_uplift_is_difference_of_recovery_rates():
    system_results = [_result(case_id="a", amount_inr=1000, eligible=True, recovered=True, recovery_channel="retry")]
    baseline_results = [_result(case_id="a", amount_inr=1000, eligible=True, recovered=False)]
    system_report = compute_metrics("system", system_results)
    baseline_report = compute_metrics("baseline", baseline_results)
    assert compute_uplift(system_report, baseline_report) == 1.0
