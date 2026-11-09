"""The validator must reject anything the warehouse does not back. No API, no warehouse."""

from ai.validate import check

TRUTH = {
    "rate_individuals": 6.17,
    "change_12m_total_pp": -0.32,
    "top_product": "Personal loans",
    "top_product_rate": 11.62,
}


def truth(metric_id):
    return TRUTH[metric_id]


def test_correct_claim_passes():
    claim = {"text": "In August 2026, delinquency among individuals reached 6.2%.",
             "metric_id": "rate_individuals", "value": 6.17}
    assert check(claim, truth) is None


def test_wrong_value_is_rejected():
    claim = {"text": "Delinquency among individuals reached 7.2%.", "metric_id": "rate_individuals", "value": 7.17}
    assert "warehouse says" in check(claim, truth)


def test_unknown_metric_is_rejected():
    claim = {"text": "Default rates doubled.", "metric_id": "made_up_metric", "value": 2}
    assert "unknown metric_id" in check(claim, truth)


def test_number_in_sentence_must_match_value():
    # The value field is right, but the sentence says something else.
    claim = {"text": "Delinquency among individuals reached 8.1%.", "metric_id": "rate_individuals", "value": 6.17}
    assert "sentence has 8.1" in check(claim, truth)


def test_negative_change_written_as_a_fall_passes():
    claim = {"text": "Over 12 months, the system rate fell 0.3 percentage points.",
             "metric_id": "change_12m_total_pp", "value": -0.32}
    assert check(claim, truth) is None


def test_text_metric_must_name_the_right_group():
    good = {"text": "Personal loans had the highest rate.", "metric_id": "top_product", "value": "Personal loans"}
    bad = {"text": "Credit cards had the highest rate.", "metric_id": "top_product", "value": "Credit card"}
    assert check(good, truth) is None
    assert check(bad, truth) is not None


def test_text_claim_with_extra_number_is_rejected():
    claim = {"text": "Personal loans had the highest rate, at 11.6%.", "metric_id": "top_product", "value": "Personal loans"}
    assert "unexpected number" in check(claim, truth)


def test_rate_of_a_group_must_name_the_right_group():
    good = {"text": "Personal loans had the highest rate, at 11.6%.", "metric_id": "top_product_rate", "value": 11.62}
    bad = {"text": "Credit cards had the highest rate, at 11.6%.", "metric_id": "top_product_rate", "value": 11.62}
    assert check(good, truth) is None
    assert "must name 'Personal loans'" in check(bad, truth)
