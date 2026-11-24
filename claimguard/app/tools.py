"""Tools the agent can call. Each returns JSON-safe data plus the sources it used."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from app.store import FEATURE_LABELS, TARGET_LABELS, clean, records, store

DISTRICT_METRICS = {
    "liability_class_2027": "GDV Kfz-Haftpflicht Regionalklasse 2027",
    "comprehensive_class_2027": "GDV Vollkasko Regionalklasse 2027",
    "partial_cover_class_2027": "GDV Teilkasko Regionalklasse 2027",
    "accidents_per_1000_cars": "injury accidents per 1,000 cars (avg 2020-2025)",
    "accidents_per_10k_people": "injury accidents per 10,000 people",
    "share_killed_or_serious": "share of accidents with killed or seriously injured",
    "population_per_km2": "population per km²",
    "cars_per_1000_people": "cars per 1,000 people",
    "share_bev": "battery-electric share of cars",
    "share_with_bicycle": "share of accidents involving bicycles",
    "share_night_22_05": "share of accidents at night",
    "accident_trend_per_year": "accident trend per year 2020-2025",
}
EUROPE_METRICS = {
    "road_deaths_per_100000": "road deaths per 100,000 people (Eurostat sdg_11_40)",
    "cars_per_1000": "passenger cars per 1,000 people (Eurostat road_eqs_carhab)",
    "nonlife_claims_ratio": "non-life claims ratio, R0310/R0210 (EIOPA Solo Annual)",
    "nonlife_premiums_written_eur_million": "non-life premiums written, EUR million (EIOPA)",
    "population": "population on 1 January (Eurostat demo_pjan)",
}
SRC = {
    "districts": "Destatis 04-kreise 2024; Unfallatlas 2020-2025; KBA FZ1 2025; GDV Regionalklassen 2027",
    "europe": "Eurostat demo_pjan, road_eqs_carhab, sdg_11_40; EIOPA Solo Annual",
    "police": "BKA Polizeiliche Kriminalstatistik, key 517400",
    "claims": "SIMULATED claims inbox (seed 2026) — not real claims",
}


def _district_card(row: pd.Series) -> dict:
    keys = ["geo_code", "geo_name", "bundesland", "district_type", "area_type", "population_2024",
            "population_per_km2", "passenger_cars_2025", "cars_per_1000_people", "liability_class_2027",
            "comprehensive_class_2027", "partial_cover_class_2027", "accidents_2025", "accidents_per_1000_cars",
            "share_killed_or_serious", "share_with_bicycle", "share_bev", "accident_trend_per_year", "gdv_coverage"]
    return clean({k: row.get(k) for k in keys})


def district_profile(district: str) -> dict:
    row = store.find_district(district)
    if row is None:
        return {"error": f"No German district matches '{district}'."}
    card = _district_card(row)
    d = store.districts
    for col in ("liability_class_2027", "accidents_per_1000_cars", "population_per_km2"):
        if pd.notna(row[col]):
            card[f"{col}_percentile"] = round(float((d[col] < row[col]).mean() * 100), 1)
    out = {"district": card, "sources": [SRC["districts"]]}
    if pd.notna(row["liability_class_2027"]):
        out["model_explanation"] = store.explain_district(row.geo_code)
    return out


def rank_districts(metric: str = "liability_class_2027", order: str = "desc", n: int = 10,
                   bundesland: str | None = None, area_type: str | None = None) -> dict:
    if metric not in DISTRICT_METRICS:
        return {"error": f"metric must be one of {list(DISTRICT_METRICS)}"}
    d = store.districts
    if bundesland:
        d = d[d.bundesland.str.lower().str.contains(bundesland.lower(), regex=False)]
    if area_type in ("urban", "rural"):
        d = d[d.area_type == area_type]
    d = d[d[metric].notna()].sort_values([metric, "population_2024"], ascending=[order == "asc", False])
    rows = d.head(max(1, min(int(n), 40)))[["geo_code", "geo_name", "bundesland", "area_type", metric]]
    return {"metric": metric, "metric_label": DISTRICT_METRICS[metric], "order": order,
            "filters": {"bundesland": bundesland, "area_type": area_type}, "rows": records(rows),
            "german_median": clean(store.districts[metric].median()), "sources": [SRC["districts"]]}


def compare_states(metric: str = "liability_class_car_weighted") -> dict:
    s = store.states
    if metric not in s.columns:
        return {"error": f"metric must be one of {[c for c in s.columns if c != 'bundesland']}"}
    return {"metric": metric, "rows": records(s.sort_values(metric, ascending=False)[["bundesland", metric]]),
            "note": "Classes are weighted by the number of passenger cars in each district.",
            "sources": [SRC["districts"]]}


def europe_compare(metric: str = "road_deaths_per_100000", year: int | None = None,
                   countries: list[str] | None = None) -> dict:
    if metric not in EUROPE_METRICS:
        return {"error": f"metric must be one of {list(EUROPE_METRICS)}"}
    e = store.europe[store.europe[metric].notna()]
    year = int(year) if year else int(e.year.max())
    if year not in set(e.year):
        year = int(e.year.max())
    rows = e[e.year == year]
    if countries:
        rows = rows[rows.geo_code.isin([c.upper() for c in countries])]
    rows = rows.sort_values(metric, ascending=False)[["geo_code", "country", metric]].reset_index(drop=True)
    de = rows.index[rows.geo_code == "DE"]
    return {"metric": metric, "metric_label": EUROPE_METRICS[metric], "year": year, "rows": records(rows),
            "germany_rank": int(de[0]) + 1 if len(de) else None, "countries": len(rows), "sources": [SRC["europe"]],
            "caveat": "The EIOPA claims ratio covers all non-life business, not motor alone." if "nonlife" in metric else None}


FRAUD_COUNTRIES = {"de": "DE", "germany": "DE", "deutschland": "DE", "se": "SE", "sweden": "SE",
                   "nl": "NL", "netherlands": "NL", "fr": "FR", "france": "FR", "uk": "UK",
                   "united kingdom": "UK", "europe": "Europe", "eu": "Europe"}


def fraud_facts(country: str | None = None, keyword: str | None = None) -> dict:
    f = store.fraud
    # the police time series has its own tool; here only its latest year
    f = f[(f.source_dataset != "bka_insurance_fraud") | (f.year == "2024")]
    if country:
        f = f[f.geo_code == FRAUD_COUNTRIES.get(country.lower(), country.upper())]
    if keyword:
        k = keyword.lower().replace(" ", "_")
        f = f[f.measure.str.contains(k, regex=False) | f.breakdown.str.contains(k, regex=False)]
    rows = f.sort_values(["source_dataset", "year"], ascending=[True, False]).head(40)
    return {"rows": records(rows[["source_dataset", "geo_code", "year", "measure", "breakdown", "value", "unit"]]),
            "sources": sorted(set(rows.source_note.dropna().str.slice(0, 160))),
            "caveat": "Countries measure different things (suspicion estimates, refused claims, proven cases, police "
                      "records), so the numbers are not directly comparable."}


def police_fraud_series(start: int = 1993, end: int = 2024) -> dict:
    f = store.fraud
    s = f[(f.source_dataset == "bka_insurance_fraud") & (f.breakdown == "insurance_fraud_and_abuse_517400")
          & (f.measure.isin(["recorded_offences", "cleared_offences", "suspects"]))]
    s = s.assign(year=s.year.astype(int))
    s = s[(s.year >= start) & (s.year <= end)].pivot_table(index="year", columns="measure", values="value").reset_index()
    peak = s.loc[s.recorded_offences.idxmax()]
    return {"rows": records(s), "peak": clean({"year": peak.year, "recorded_offences": peak.recorded_offences}),
            "latest": clean(s.iloc[-1].to_dict()), "sources": [SRC["police"]]}


def score_claim(days_after_policy_start: int = 200, days_before_policy_expiry: int = 165, days_to_report: int = 2,
                prior_claims_12_months: int = 0, description_matches_damage: str = "yes",
                amount_inflated: str = "no", document_manipulated: str = "no", police_report: str = "yes",
                injury: str = "no", witness: str = "yes", vehicle_age_years: int = 6,
                repair_estimate_eur: float = 2500, claimed_amount_eur: float = 2500) -> dict:
    claim = {k: v for k, v in locals().items()}
    result = store.score(claim)
    return {"claim": claim, "result": result, "sources": ["ClaimGuard red-flag rulebook (IVASS / GDV / BKA basis)"]}


def triage_queue(band: str = "red", n: int = 10) -> dict:
    c = store.claims
    if band in ("red", "amber", "green"):
        c = c[c.triage == band]
    c = c.sort_values("score", ascending=False).head(max(1, min(int(n), 50)))
    counts = store.claims.triage.value_counts().to_dict()
    return {"band": band, "counts": clean(counts),
            "rows": records(c[["claim_id", "geo_name", "bundesland", "claimed_amount_eur", "score", "triage",
                               "rules_fired", "reason_summary"]]),
            "label": "SIMULATED claims", "sources": [SRC["claims"]]}


def claim_lookup(claim_id: str) -> dict:
    c = store.claims
    hit = c[c.claim_id.str.upper() == claim_id.upper()]
    if hit.empty:
        return {"error": f"No claim {claim_id}"}
    row = hit.iloc[0].to_dict()
    result = store.score(row)
    return {"claim": clean(row), "result": result, "sources": [SRC["claims"]]}


def search_documents(query: str, k: int = 5) -> dict:
    hits = store.retriever.search(query, k=max(1, min(int(k), 8)))
    return {"hits": [{"source": h["source"], "locator": h["locator"], "kind": h["kind"],
                      "text": h["text"][:700], "score": h["score"]} for h in hits]}


def model_info() -> dict:
    _, metrics = store.regional_model
    out = {"headline": metrics["headline"], "gate": metrics["gate"], "drift_status": store.drift.get("status"),
           "targets": {}}
    for target, t in metrics["report"]["targets"].items():
        best = t["scores"]["best_model"]
        out["targets"][target] = {
            "label": t["label"], "best_model": best,
            "spatial_cv": t["scores"]["spatial"][best], "random_cv": t["scores"]["random"][best],
            "baseline": t["scores"]["spatial"]["baseline_median"],
            "top_drivers": [FEATURE_LABELS.get(i["feature"], i["feature"]) for i in t["importance"][:5]],
        }
    out["sources"] = ["models/registry (spatial GroupKFold by Bundesland)"]
    return clean(out)


def priced_gaps(target: str = "liability_class_2027", direction: str = "above", n: int = 10) -> dict:
    r = store.residuals.merge(store.districts[["geo_code", "geo_name", "bundesland", "area_type", target]],
                              on="geo_code")
    col = f"resid_{target}"
    r = r[r[col].notna()].sort_values(col, ascending=(direction != "above")).head(max(1, min(int(n), 30)))
    return {"target": target, "label": TARGET_LABELS.get(target, target), "direction": direction,
            "rows": records(r[["geo_code", "geo_name", "bundesland", "area_type", target, f"pred_{target}", col]]),
            "meaning": "Residual = GDV class minus the class predicted from public data in spatial cross-validation. "
                       "Above means GDV's class is higher than accidents, density and fleet suggest. These are "
                       "hypotheses (e.g. property-damage-only claims, repair costs, theft, fraud) for an actuary to check.",
            "sources": [SRC["districts"], "ClaimGuard Regionalklasse model"]}


TOOLS: dict[str, tuple[Callable[..., dict], str, dict]] = {
    "district_profile": (district_profile, "Facts, GDV classes, accident rates and model explanation for one German district (name or 5-digit code).",
                         {"district": {"type": "string"}}),
    "rank_districts": (rank_districts, "Rank German districts by a metric, optionally filtered by Bundesland or urban/rural.",
                       {"metric": {"type": "string", "enum": list(DISTRICT_METRICS)}, "order": {"type": "string", "enum": ["desc", "asc"]},
                        "n": {"type": "integer"}, "bundesland": {"type": "string"}, "area_type": {"type": "string", "enum": ["urban", "rural"]}}),
    "compare_states": (compare_states, "Compare the 16 Bundeslaender (car-weighted GDV classes, accidents per 1,000 cars, BEV share).",
                       {"metric": {"type": "string", "enum": ["liability_class_car_weighted", "comprehensive_class_car_weighted",
                                                              "partial_cover_class_car_weighted", "accidents_per_1000_cars", "share_bev"]}}),
    "europe_compare": (europe_compare, "Compare European countries on road safety, car ownership or non-life insurance (EIOPA).",
                       {"metric": {"type": "string", "enum": list(EUROPE_METRICS)}, "year": {"type": "integer"},
                        "countries": {"type": "array", "items": {"type": "string"}}}),
    "fraud_facts": (fraud_facts, "Published insurance-fraud figures for Germany, Sweden, Netherlands, France, UK or Europe.",
                    {"country": {"type": "string"}, "keyword": {"type": "string"}}),
    "police_fraud_series": (police_fraud_series, "German police-recorded insurance fraud (BKA PKS 517400) 1993-2024.",
                            {"start": {"type": "integer"}, "end": {"type": "integer"}}),
    "score_claim": (score_claim, "Score a motor claim with the red-flag rules and the anomaly model.",
                    {"days_after_policy_start": {"type": "integer"}, "days_before_policy_expiry": {"type": "integer"},
                     "days_to_report": {"type": "integer"}, "prior_claims_12_months": {"type": "integer"},
                     "description_matches_damage": {"type": "string", "enum": ["yes", "no"]},
                     "amount_inflated": {"type": "string", "enum": ["yes", "no"]},
                     "document_manipulated": {"type": "string", "enum": ["yes", "no"]},
                     "police_report": {"type": "string", "enum": ["yes", "no"]}, "injury": {"type": "string", "enum": ["yes", "no"]},
                     "witness": {"type": "string", "enum": ["yes", "no"]}, "vehicle_age_years": {"type": "integer"},
                     "repair_estimate_eur": {"type": "number"}, "claimed_amount_eur": {"type": "number"}}),
    "triage_queue": (triage_queue, "List claims in the SIMULATED inbox by triage band.",
                     {"band": {"type": "string", "enum": ["red", "amber", "green", "all"]}, "n": {"type": "integer"}}),
    "claim_lookup": (claim_lookup, "Look up one SIMULATED claim by id, e.g. SIM-0042, and re-score it.",
                     {"claim_id": {"type": "string"}}),
    "search_documents": (search_documents, "Search the PDFs (EIOPA, Unfallatlas, KBA) and methodology notes. Use for definitions and caveats.",
                         {"query": {"type": "string"}, "k": {"type": "integer"}}),
    "model_info": (model_info, "Quality, validation and drift status of the Regionalklasse models.", {}),
    "priced_gaps": (priced_gaps, "Districts whose GDV class is far above or below what public data predicts.",
                    {"target": {"type": "string", "enum": list(TARGET_LABELS)}, "direction": {"type": "string", "enum": ["above", "below"]},
                     "n": {"type": "integer"}}),
}


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": name, "description": desc,
                                              "parameters": {"type": "object", "properties": props}}}
            for name, (_, desc, props) in TOOLS.items()]


def call(name: str, args: dict[str, Any]) -> dict:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    fn, _, props = TOOLS[name]
    args = {k: v for k, v in (args or {}).items() if k in props}
    try:
        return fn(**args)
    except Exception as exc:  # tools must never crash the agent loop
        return {"error": f"{type(exc).__name__}: {exc}"}
