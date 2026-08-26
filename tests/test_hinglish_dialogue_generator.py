from data.generators.hinglish_dialogue_generator import TEMPLATES, generate_dialogue_scenarios


def test_generates_all_categories():
    scenarios = generate_dialogue_scenarios(n_per_category=3, seed=1)
    categories = {s.category for s in scenarios}
    assert categories == {t[0] for t in TEMPLATES}
    assert len(scenarios) == 3 * len(TEMPLATES)


def test_reproducible_with_same_seed():
    a = generate_dialogue_scenarios(n_per_category=3, seed=5)
    b = generate_dialogue_scenarios(n_per_category=3, seed=5)
    assert [s.model_dump_json() for s in a] == [s.model_dump_json() for s in b]


def test_ground_truth_consistent_with_promise_fields():
    scenarios = generate_dialogue_scenarios(n_per_category=4, seed=2)
    for s in scenarios:
        if s.ground_truth.has_promise:
            assert s.ground_truth.promised_amount_inr is not None
        else:
            assert s.ground_truth.promised_amount_inr is None


def test_scripted_customer_turns_have_no_unfilled_placeholders():
    scenarios = generate_dialogue_scenarios(n_per_category=2, seed=3)
    for s in scenarios:
        for turn in s.scripted_customer_turns:
            assert "{" not in turn and "}" not in turn
