import pandas as pd
import pytest

from core.paths import MARTS
from core.triage import RULES, band_for, fired_rules, score_claim


@pytest.fixture(scope="module")
def inbox():
    return pd.read_csv(MARTS / "claims_inbox.csv", dtype={"geo_code": str}).fillna({"rules_fired": ""})


def test_engine_reproduces_every_simulated_claim(inbox):
    for row in inbox.to_dict("records"):
        result = score_claim(row)
        expected = [r for r in row["rules_fired"].split(";") if r]
        assert [f["rule_id"] for f in result.fired] == expected, row["claim_id"]
        assert result.score == row["score"], row["claim_id"]
        assert result.band == row["triage"], row["claim_id"]


@pytest.mark.parametrize("score,band", [(0, "green"), (14, "green"), (15, "amber"), (34, "amber"), (35, "red"), (200, "red")])
def test_band_edges(score, band):
    assert band_for(score) == band


def test_clean_claim_fires_nothing():
    claim = {"days_after_policy_start": 200, "days_before_policy_expiry": 165, "days_to_report": 2,
             "prior_claims_12_months": 0, "description_matches_damage": "yes", "amount_inflated": "no",
             "document_manipulated": "no", "police_report": "yes", "injury": "no", "witness": "yes",
             "vehicle_age_years": 5, "claimed_amount_eur": 2000, "repair_estimate_eur": 2000}
    assert fired_rules(claim) == []


def test_staged_accident_pattern_is_red():
    claim = {"days_after_policy_start": 9, "days_before_policy_expiry": 356, "days_to_report": 45,
             "prior_claims_12_months": 3, "description_matches_damage": "no", "amount_inflated": "yes",
             "document_manipulated": "no", "police_report": "no", "injury": "yes", "witness": "no",
             "vehicle_age_years": 18, "claimed_amount_eur": 14000, "repair_estimate_eur": 3000}
    result = score_claim(claim)
    assert result.band == "red"
    assert result.score == sum(r["points"] for r in RULES.values()) - RULES["R2"]["points"] - RULES["R7"]["points"]


def test_r8_needs_serious_claim():
    small = {"police_report": "no", "injury": "no", "claimed_amount_eur": 4999}
    big = {**small, "claimed_amount_eur": 5000}
    assert "R8" not in fired_rules(small)
    assert "R8" in fired_rules(big)
