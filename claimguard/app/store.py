"""Loads marts, map, models and the retrieval index once and answers data questions."""

from __future__ import annotations

import json
import math
from functools import cached_property
from typing import Any

import numpy as np
import pandas as pd

from core.paths import GEO, MARTS, REPORTS
from core.triage import score_claim
from ml import anomaly, registry
from rag.index import Retriever

FEATURE_LABELS = {
    "log_density": "population density (log)",
    "is_urban": "urban district",
    "area_km2": "district area (log km²)",
    "cars_per_1000_people": "cars per 1,000 people",
    "accidents_per_1000_cars": "injury accidents per 1,000 cars",
    "accidents_per_10k_people": "injury accidents per 10,000 people",
    "accident_trend_per_year": "accident trend 2020-2025",
    "share_killed_or_serious": "share killed or seriously injured",
    "share_darkness": "share in darkness",
    "share_wet_road": "share on wet roads",
    "share_winter_road": "share on winter roads",
    "share_weekend": "share at weekends",
    "share_night_22_05": "share at night (22-05h)",
    "share_rush_hour": "share in rush hour",
    "share_rear_end": "share rear-end collisions",
    "share_left_road": "share run-off-road",
    "share_turning_crossing": "share turning/crossing",
    "share_with_bicycle": "share involving bicycles",
    "share_with_pedestrian": "share involving pedestrians",
    "share_with_motorcycle": "share involving motorcycles",
    "share_with_goods_vehicle": "share involving goods vehicles",
    "share_diesel": "diesel share of cars",
    "share_bev": "battery-electric share of cars",
    "share_hybrid": "hybrid share of cars",
    "share_old_fleet_euro4_or_older": "share Euro 4 or older",
    "share_engine_2000cc_plus": "share 2,000 cc or more",
    "car_growth_2018_2025": "car stock growth 2018-2025",
    "motorcycles_per_1000_people": "motorcycles per 1,000 people",
    "trucks_per_1000_people": "trucks per 1,000 people",
    "share_male": "male share of population",
}

TARGET_LABELS = {
    "liability_class_2027": "Kfz-Haftpflicht",
    "comprehensive_class_2027": "Vollkasko",
    "partial_cover_class_2027": "Teilkasko",
}


def clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def records(df: pd.DataFrame) -> list[dict]:
    return clean(df.to_dict("records"))


class Store:
    @cached_property
    def districts(self) -> pd.DataFrame:
        return pd.read_csv(MARTS / "districts.csv", dtype={"geo_code": str})

    @cached_property
    def states(self) -> pd.DataFrame:
        return pd.read_csv(MARTS / "states.csv")

    @cached_property
    def trends(self) -> pd.DataFrame:
        return pd.read_csv(MARTS / "germany_trends.csv")

    @cached_property
    def profiles(self) -> pd.DataFrame:
        return pd.read_csv(MARTS / "accident_profiles.csv")

    @cached_property
    def europe(self) -> pd.DataFrame:
        """Country rows only: two-letter codes, without metropolitan France (FX), which repeats FR."""
        e = pd.read_csv(MARTS / "europe.csv")
        return e[(e.geo_code.str.len() == 2) & (e.geo_code != "FX")].reset_index(drop=True)

    @cached_property
    def fraud(self) -> pd.DataFrame:
        return pd.read_csv(MARTS / "fraud_landscape.csv", dtype={"year": str})

    @cached_property
    def claims(self) -> pd.DataFrame:
        return pd.read_csv(MARTS / "claims_inbox.csv", dtype={"geo_code": str})

    @cached_property
    def rules(self) -> pd.DataFrame:
        cols = ["rule_id", "indicator", "points", "applies_when", "published_basis", "source"]
        return pd.read_csv(MARTS / "fraud_rules.csv")[cols]

    @cached_property
    def overview(self) -> dict:
        return json.loads((MARTS / "overview.json").read_text(encoding="utf-8"))

    @cached_property
    def insights(self) -> list[dict]:
        path = MARTS / "insights.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    @cached_property
    def geojson(self) -> str:
        return (GEO / "districts.geojson").read_text(encoding="utf-8")

    @cached_property
    def states_geojson(self) -> str:
        return (GEO / "states.geojson").read_text(encoding="utf-8")

    @cached_property
    def regional_model(self) -> tuple[dict, dict]:
        artifact, metrics, _ = registry.load("regionalklasse")
        return artifact, metrics

    @cached_property
    def anomaly_model(self) -> dict:
        artifact, _, _ = registry.load("claim_anomaly")
        return artifact

    @cached_property
    def retriever(self) -> Retriever:
        return Retriever.load()

    @cached_property
    def drift(self) -> dict:
        path = REPORTS / "drift.json"
        return json.loads(path.read_text()) if path.exists() else {"status": "unknown", "features": []}

    @cached_property
    def residuals(self) -> pd.DataFrame:
        _, metrics = self.regional_model
        frames = []
        for target, t in metrics["report"]["targets"].items():
            r = pd.DataFrame(t["residuals"])[["geo_code", "predicted_spatial_cv", "residual"]]
            r.columns = ["geo_code", f"pred_{target}", f"resid_{target}"]
            frames.append(r.set_index("geo_code"))
        return pd.concat(frames, axis=1).reset_index()

    # ---- lookups -----------------------------------------------------------------

    def find_district(self, query: str) -> pd.Series | None:
        d = self.districts
        q = str(query).strip().lower()
        if q.isdigit():
            hit = d[d.geo_code == q.zfill(5)]
            return hit.iloc[0] if len(hit) else None
        names = d.geo_name.str.lower()
        for mask in (names == q, names.str.split(",").str[0].str.strip() == q,
                     names.str.startswith(q), names.str.contains(q, regex=False)):
            hit = d[mask]
            if len(hit):
                return hit.sort_values("population_2024", ascending=False).iloc[0]
        return None

    def map_layer(self) -> list[dict]:
        cols = ["geo_code", "geo_name", "bundesland", "area_type", "population_2024", "population_per_km2",
                "liability_class_2027", "comprehensive_class_2027", "partial_cover_class_2027",
                "accidents_per_1000_cars", "accidents_per_10k_people", "share_killed_or_serious",
                "share_bev", "cars_per_1000_people", "share_with_bicycle", "accident_trend_per_year"]
        df = self.districts[cols].merge(self.residuals, on="geo_code", how="left")
        return records(df)

    def explain_district(self, code: str, target: str = "liability_class_2027") -> dict:
        artifact, _ = self.regional_model
        row = self.districts[self.districts.geo_code == code]
        if row.empty:
            raise KeyError(code)
        X = row[artifact["features"]].copy()
        X["area_km2"] = np.log10(X["area_km2"])
        spec = artifact["targets"][target]
        model = spec["model"]
        pred = float(model.predict(X)[0])
        contributions = []
        for f in artifact["features"]:
            if pd.isna(X.iloc[0][f]):
                continue
            Xm = X.copy()
            Xm[f] = artifact["medians"][f]
            delta = pred - float(model.predict(Xm)[0])
            if abs(delta) > 0.01:
                contributions.append({"feature": f, "label": FEATURE_LABELS.get(f, f),
                                      "value": float(row.iloc[0][f]), "median": float(artifact["medians"][f]),
                                      "effect": round(delta, 2)})
        contributions.sort(key=lambda c: -abs(c["effect"]))
        actual = row.iloc[0][target]
        return clean({"geo_code": code, "geo_name": row.iloc[0].geo_name, "target": target,
                      "label": spec["label"], "model": spec["name"], "predicted": round(pred, 2),
                      "actual": actual, "gap": None if pd.isna(actual) else round(float(actual) - pred, 2),
                      "drivers": contributions[:8],
                      "method": "Each driver shows how the prediction changes if that feature is set to the German median."})

    def score(self, claim: dict) -> dict:
        result = score_claim(claim).as_dict()
        result["anomaly"] = anomaly.score(self.anomaly_model, claim)
        if result["band"] == "green" and result["anomaly"]["second_look"]:
            result["route"] = "second look (anomaly)"
        else:
            result["route"] = result["action"]
        return clean(result)


store = Store()
