import pytest

from app import tools
from app.agent import compose, plan


@pytest.mark.parametrize("question,first_tool", [
    ("Tell me about München", "district_profile"),
    ("Top 10 most expensive rural districts in Bayern", "rank_districts"),
    ("How does Germany compare in Europe on road deaths?", "europe_compare"),
    ("What is the non-life claims ratio in European countries?", "europe_compare"),
    ("Insurance fraud in Sweden", "fraud_facts"),
    ("Police fraud trend", "police_fraud_series"),
    ("Show me the red claims queue", "triage_queue"),
    ("Explain SIM-42", "claim_lookup"),
    ("Is there drift in the model?", "model_info"),
    ("Which districts are overpriced?", "priced_gaps"),
    ("What does the Unfallatlas record?", "search_documents"),
])
def test_planner_routes(question, first_tool):
    assert plan(question)[0][0] == first_tool


def test_rank_filters_apply():
    r = tools.rank_districts("liability_class_2027", "desc", 5, bundesland="bayern", area_type="rural")
    assert r["rows"] and all(row["bundesland"] == "Bayern" and row["area_type"] == "rural" for row in r["rows"])


def test_fraud_percent_is_not_rescaled():
    r = tools.fraud_facts("sweden", "claims_investigated_share")
    text = compose("", [("fraud_facts", r)])
    assert "0.4 percent" in text


def test_tool_errors_do_not_raise():
    assert "error" in tools.call("rank_districts", {"metric": "nope"})
    assert "error" in tools.call("does_not_exist", {})
