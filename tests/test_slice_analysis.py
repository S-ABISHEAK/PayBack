from evaluation.experiments.run_slice_analysis import SLICE_DIMENSIONS, _attempt_bucket, _slice_report
from evaluation.metrics.schema import CaseResult
from tests.factories import make_case


def test_attempt_bucket_caps_at_4_plus():
    assert _attempt_bucket(0) == "0"
    assert _attempt_bucket(3) == "3"
    assert _attempt_bucket(4) == "4+"
    assert _attempt_bucket(9) == "4+"


def test_slice_report_groups_by_failure_category():
    cases = [make_case(f"case_{i}", seed=i) for i in range(10)]
    cases_by_id = {c.case_id: c for c in cases}
    results = [
        CaseResult(case_id=c.case_id, amount_inr=c.context.amount_inr, eligible=True, recovered=(i % 2 == 0))
        for i, c in enumerate(cases)
    ]

    report = _slice_report(cases_by_id, results, SLICE_DIMENSIONS["failure_category"])

    total_cases_in_slices = sum(s["n_cases"] for s in report.values())
    assert total_cases_in_slices == len(cases)
    for slice_value in report:
        assert slice_value in {c.ground_truth.true_cause.value for c in cases}


def test_slice_report_skips_results_with_no_matching_case():
    results = [CaseResult(case_id="ghost_case", amount_inr=100, eligible=True, recovered=True)]
    report = _slice_report({}, results, SLICE_DIMENSIONS["amount_bucket"])
    assert report == {}
