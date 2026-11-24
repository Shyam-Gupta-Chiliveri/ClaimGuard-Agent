"""ClaimGuard API + static HTML frontend.

Run: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import agent, llm, tools
from app.store import FEATURE_LABELS, TARGET_LABELS, clean, records, store
from core.paths import WEB
from ml import registry

app = FastAPI(title="ClaimGuard", version="1.0.0",
              description="German motor-insurance risk, Europe comparison and claim-fraud triage.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])
STARTED = time.time()
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")


class ClaimIn(BaseModel):
    claim_id: str | None = None
    geo_code: str | None = None
    days_after_policy_start: int = Field(200, ge=0, le=4000)
    days_before_policy_expiry: int = Field(165, ge=-400, le=4000)
    days_to_report: int = Field(2, ge=0, le=3650)
    prior_claims_12_months: int = Field(0, ge=0, le=50)
    description_matches_damage: Literal["yes", "no"] = "yes"
    amount_inflated: Literal["yes", "no"] = "no"
    document_manipulated: Literal["yes", "no"] = "no"
    police_report: Literal["yes", "no"] = "yes"
    injury: Literal["yes", "no"] = "no"
    witness: Literal["yes", "no"] = "yes"
    vehicle_age_years: int = Field(6, ge=0, le=80)
    repair_estimate_eur: float = Field(2500, ge=0)
    claimed_amount_eur: float = Field(2500, ge=0)


class ChatIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    history: list[dict] = []
    lang: str = "en"


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


# ------------------------------------------------------------------ health & overview


@app.get("/api/health")
def health():
    return {"status": "ok", "uptime_s": round(time.time() - STARTED), "agent": llm.describe(),
            "models": {m: registry.production(m) for m in ("regionalklasse", "claim_anomaly")}}


@app.get("/api/overview")
def overview():
    return {**store.overview, "agent": llm.describe(), "drift_status": store.drift.get("status")}


@app.get("/api/insights")
def insights():
    return store.insights


# ------------------------------------------------------------------ Germany


@app.get("/api/geo/districts")
def geo_districts():
    return Response(store.geojson, media_type="application/geo+json",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/geo/states")
def geo_states():
    return Response(store.states_geojson, media_type="application/geo+json",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/districts")
def districts():
    return store.map_layer()


@app.get("/api/districts/{code}")
def district(code: str):
    r = tools.district_profile(code)
    if "error" in r:
        raise HTTPException(404, r["error"])
    return r


@app.get("/api/districts/{code}/explain")
def explain(code: str, target: str = "liability_class_2027"):
    if target not in TARGET_LABELS:
        raise HTTPException(400, f"target must be one of {list(TARGET_LABELS)}")
    try:
        return store.explain_district(code, target)
    except KeyError:
        raise HTTPException(404, f"district {code} not found") from None


@app.get("/api/states")
def states():
    return records(store.states)


@app.get("/api/germany/trends")
def trends():
    return records(store.trends)


@app.get("/api/germany/profiles")
def profiles():
    p = store.profiles
    out: dict = {}
    for (area, measure), g in p.groupby(["area_type", "measure"]):
        out.setdefault(measure, {})[area] = dict(zip(g.breakdown, g.share.round(4), strict=True))
    return out


@app.get("/api/germany/scatter")
def scatter():
    d = store.districts
    cols = ["geo_code", "geo_name", "bundesland", "area_type", "population_per_km2", "liability_class_2027",
            "accidents_per_1000_cars", "population_2024", "share_bev", "partial_cover_class_2027"]
    return records(d[d.liability_class_2027.notna()][cols])


# ------------------------------------------------------------------ Europe


@app.get("/api/europe")
def europe(year: int | None = None):
    e = store.europe
    if year:
        e = e[e.year == year]
    cols = ["geo_code", "country", "year", "population", "cars_per_1000", "road_deaths_per_100000",
            "nonlife_claims_ratio", "nonlife_premiums_written_eur_million"]
    return records(e[cols])


# ------------------------------------------------------------------ fraud & triage


@app.get("/api/fraud/landscape")
def fraud_landscape():
    f = store.fraud[store.fraud.source_dataset != "bka_insurance_fraud"]
    return records(f.drop(columns=["source_file"]))


@app.get("/api/fraud/police")
def fraud_police():
    return tools.police_fraud_series()


@app.get("/api/fraud/rules")
def fraud_rules():
    return records(store.rules)


@app.get("/api/claims")
def claims(band: str | None = None, limit: int = Query(100, le=800)):
    c = store.claims
    if band:
        c = c[c.triage == band]
    cols = ["claim_id", "geo_code", "geo_name", "bundesland", "incident_date", "claimed_amount_eur",
            "repair_estimate_eur", "score", "triage", "rules_fired", "reason_summary"]
    return {"label": "SIMULATED claims", "counts": clean(store.claims.triage.value_counts().to_dict()),
            "rows": records(c.sort_values("score", ascending=False).head(limit)[cols])}


@app.get("/api/claims/{claim_id}")
def claim(claim_id: str):
    r = tools.claim_lookup(claim_id)
    if "error" in r:
        raise HTTPException(404, r["error"])
    return r


async def notify_n8n(payload: dict) -> None:
    if not N8N_WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(N8N_WEBHOOK_URL, json=payload)
    except httpx.HTTPError:
        pass


@app.post("/api/claims/score")
async def score(claim: ClaimIn, background: BackgroundTasks):
    data = claim.model_dump()
    result = store.score(data)
    if result["band"] == "red" or result["route"].startswith("second look"):
        background.add_task(notify_n8n, {"event": "claim_flagged", "claim": data, "result": result})
    return {"claim": data, "result": result}


@app.get("/api/claims/stream/live")
async def claims_stream(speed: float = Query(1.0, ge=0.2, le=10)):
    """Replays the SIMULATED inbox as if claims were arriving now, scoring each on arrival."""
    rows = store.claims.to_dict("records")

    async def gen():
        rng = random.Random()
        order = list(range(len(rows)))
        rng.shuffle(order)
        for n, i in enumerate(order):
            row = rows[i]
            result = store.score(row)
            yield sse({"seq": n, "claim_id": row["claim_id"], "geo_code": row["geo_code"], "geo_name": row["geo_name"],
                       "bundesland": row["bundesland"], "claimed_amount_eur": row["claimed_amount_eur"],
                       "score": result["score"], "band": result["band"], "route": result["route"],
                       "fired": [f["rule_id"] for f in result["fired"]],
                       "anomaly": result["anomaly"]["anomaly_score"], "label": "SIMULATED"})
            await asyncio.sleep(rng.uniform(0.6, 1.8) / speed)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ ML / MLOps


@app.get("/api/ml/regionalklasse")
def ml_regionalklasse():
    _, metrics = store.regional_model
    out = {"version": registry.production("regionalklasse"), "headline": metrics["headline"],
           "gate": metrics["gate"], "feature_labels": FEATURE_LABELS, "targets": {}}
    for target, t in metrics["report"]["targets"].items():
        out["targets"][target] = {k: t[k] for k in ("label", "n", "scores", "importance", "partial_dependence")}
        out["targets"][target]["points"] = [
            {"geo_code": r["geo_code"], "geo_name": r["geo_name"], "actual": r[target],
             "predicted": r["predicted_spatial_cv"], "residual": r["residual"], "bundesland": r["bundesland"]}
            for r in t["residuals"]]
    return clean(out)


@app.get("/api/ml/registry")
def ml_registry():
    return registry.listing()


@app.get("/api/ml/drift")
def ml_drift():
    return store.drift


@app.get("/api/ml/anomaly")
def ml_anomaly():
    _, metrics, _ = registry.load("claim_anomaly")
    return {"version": registry.production("claim_anomaly"), **metrics}


# ------------------------------------------------------------------ RAG & agent


@app.get("/api/rag/search")
def rag_search(q: str = Query(..., min_length=2), k: int = Query(5, le=10)):
    return tools.search_documents(q, k)


@app.post("/api/agent/chat")
def agent_chat(body: ChatIn):
    def gen():
        try:
            for event in agent.run(body.question, body.history, body.lang):
                yield sse(event)
        except Exception as exc:
            yield sse({"type": "answer", "text": f"Agent error: {exc}", "sources": [], "mode": "error"})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/agent/ask")
def agent_ask(body: ChatIn):
    """Non-streaming variant for n8n and scripts."""
    events = list(agent.run(body.question, body.history, body.lang))
    answer = next((e for e in reversed(events) if e["type"] == "answer"), {})
    return {"answer": answer.get("text"), "sources": answer.get("sources", []), "mode": answer.get("mode"),
            "trace": [e for e in events if e["type"] in ("tool", "observation")]}


@app.get("/api/agent/brief/{claim_id}")
def agent_brief(claim_id: str, lang: str = "en"):
    r = agent.investigator_brief(claim_id, lang)
    if "error" in r:
        raise HTTPException(404, r["error"])
    return r


class BriefIn(BaseModel):
    claim: ClaimIn
    result: dict | None = None
    lang: str = "en"


@app.post("/api/agent/brief")
def agent_brief_new(body: BriefIn):
    """Investigator note for any claim (n8n sends the claim it just scored)."""
    return agent.brief_for(body.claim.model_dump(), body.result, lang=body.lang)


# ------------------------------------------------------------------ frontend

app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html")
