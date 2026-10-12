import pytest

from gabriel_prospect.scoring import IcpValidationError, default_icp, score_prospect, validate_icp


FULL_MATCH = {
    "agency_type": "Agence branding B2B",
    "services": "Identité de marque, stratégie social media",
    "job_title": "Fondatrice et CEO",
    "employee_count": 18,
    "country": "France",
    "city": "Lyon",
    "email": "contact@agence.test",
    "linkedin_url": None,
}


def _facts_for(data):
    return {key: f"fact-{key}" for key, value in data.items() if value not in (None, "")}


def test_default_icp_weights_total_one_hundred_and_match_validated_decisions():
    icp = default_icp()
    assert icp["weights"] == {
        "agency_type": 25,
        "services_fit": 20,
        "decision_maker": 20,
        "employee_count": 15,
        "geography": 10,
        "professional_channel": 10,
    }
    assert sum(icp["weights"].values()) == 100


def test_full_match_scores_one_hundred_with_explainable_criteria():
    score = score_prospect(FULL_MATCH, _facts_for(FULL_MATCH), default_icp())
    assert score["total"] == 100
    assert len(score["criteria"]) == 6
    assert sum(item["points"] for item in score["criteria"]) == 100
    assert all(item["explanation"] for item in score["criteria"])
    assert all(item["matched"] for item in score["criteria"])


def test_b2b_b2c_status_is_not_a_scoring_criterion():
    score = score_prospect({**FULL_MATCH, "market_type": "B2C"}, _facts_for(FULL_MATCH), default_icp())
    assert score["total"] == 100
    assert "market_type" not in {item["criterion"] for item in score["criteria"]}


def test_unknown_values_score_zero_and_are_explained_as_unknown():
    score = score_prospect({}, {}, default_icp())
    assert score["total"] == 0
    assert all(item["points"] == 0 for item in score["criteria"])
    assert all(item["status"] == "unknown" for item in score["criteria"])


def test_hypotheses_are_not_an_input_and_cannot_increase_score():
    score = score_prospect(
        {"company_name": "Agence hypothétique"},
        {"company_name": "fact-company"},
        default_icp(),
    )
    assert score["total"] == 0


def test_each_scored_match_references_imported_fact_ids():
    fact_ids = _facts_for(FULL_MATCH)
    score = score_prospect(FULL_MATCH, fact_ids, default_icp())
    for criterion in score["criteria"]:
        assert criterion["fact_ids"]
        assert all(fact_id in fact_ids.values() for fact_id in criterion["fact_ids"])


def test_custom_weights_must_total_exactly_one_hundred():
    invalid = default_icp()
    invalid["weights"]["geography"] = 9
    with pytest.raises(IcpValidationError) as exc:
        validate_icp(invalid)
    assert exc.value.code == "invalid_icp_weights"


def test_unknown_weight_keys_are_rejected():
    invalid = default_icp()
    invalid["weights"]["b2b"] = 0
    with pytest.raises(IcpValidationError) as exc:
        validate_icp(invalid)
    assert exc.value.code == "invalid_icp_weights"


def test_custom_icp_configuration_changes_matching_deterministically():
    custom = default_icp()
    custom["target_geographies"] = ["Belgique"]
    custom["employee_range"] = {"min": 1, "max": 5}
    score = score_prospect(FULL_MATCH, _facts_for(FULL_MATCH), validate_icp(custom))
    assert score["total"] == 75
    failed = {c["criterion"] for c in score["criteria"] if not c["matched"]}
    assert failed == {"employee_count", "geography"}
