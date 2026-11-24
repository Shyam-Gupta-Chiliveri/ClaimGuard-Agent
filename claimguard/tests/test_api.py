import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("path", [
    "/api/health", "/api/overview", "/api/insights", "/api/districts", "/api/districts/11000",
    "/api/districts/11000/explain", "/api/states", "/api/germany/trends", "/api/germany/profiles",
    "/api/germany/scatter", "/api/europe?year=2024", "/api/fraud/landscape", "/api/fraud/police",
    "/api/fraud/rules", "/api/claims?band=red", "/api/claims/SIM-0001", "/api/ml/regionalklasse",
    "/api/ml/registry", "/api/ml/drift", "/api/ml/anomaly", "/api/rag/search?q=Regionalklasse",
    "/api/agent/brief/SIM-0001", "/",
])
def test_get_endpoints(path):
    assert client.get(path).status_code == 200


def test_geojson_has_400_districts():
    geo = client.get("/api/geo/districts").json()
    assert len(geo["features"]) == 400


def test_unknown_district_404():
    assert client.get("/api/districts/99999").status_code == 404


def test_score_claim_red():
    body = {"days_after_policy_start": 5, "description_matches_damage": "no", "document_manipulated": "yes"}
    r = client.post("/api/claims/score", json=body).json()
    assert r["result"]["band"] == "red"
    assert {f["rule_id"] for f in r["result"]["fired"]} == {"R1", "R5", "R7"}


def test_brief_for_posted_claim():
    claim = {"claim_id": "N8N-1", "days_after_policy_start": 5, "description_matches_damage": "no", "document_manipulated": "yes"}
    r = client.post("/api/agent/brief", json={"claim": claim}).json()
    assert r["claim_id"] == "N8N-1" and r["band"] == "red" and r["score"] == 55
    assert "R5" in r["brief"] or "manipulated" in r["brief"].lower()


def test_score_claim_validates_input():
    assert client.post("/api/claims/score", json={"injury": "maybe"}).status_code == 422
    assert client.post("/api/claims/score", json={"days_to_report": -3}).status_code == 422


def test_europe_has_no_aggregates_or_duplicates():
    rows = client.get("/api/europe?year=2024").json()
    codes = [r["geo_code"] for r in rows]
    assert "FX" not in codes and all(len(c) == 2 for c in codes)
    assert len(codes) == len(set(codes))


def _events(text):
    return [json.loads(line[6:]) for line in text.split("\n\n") if line.startswith("data: ")]


def test_agent_chat_streams_answer_with_sources():
    r = client.post("/api/agent/chat", json={"question": "Tell me about Gelsenkirchen"})
    events = _events(r.text)
    assert events[-1]["type"] == "answer"
    assert "Gelsenkirchen" in events[-1]["text"]
    assert events[-1]["sources"]
    assert any(e["type"] == "tool" and e["name"] == "district_profile" for e in events)


def test_agent_ask_non_streaming():
    r = client.post("/api/agent/ask", json={"question": "police fraud trend"}).json()
    assert "2,129" in r["answer"]
