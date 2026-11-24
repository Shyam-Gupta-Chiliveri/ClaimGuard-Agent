"""Build the analysis marts that the app, the models and the dashboards read.

Inputs (read-only):
  ../motor_insurance_risk_raw.csv          long fact table, one published number per row
  ../analysis/germany_districts.csv        one row per current district (classes, cars, accidents)
  ../analysis/eu_countries.csv             country comparison (SA non-life only)
  ../analysis/simulated_claims_inbox.csv   800 SIMULATED claims for the triage demo
  ../analysis/fraud_red_flag_rules.csv     red-flag rulebook

Outputs: data/marts/*.csv and data/marts/overview.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
RAW_CSV = Path(os.environ.get("RAW_CSV", PROJECT / "motor_insurance_risk_raw.csv"))
ANALYSIS = Path(os.environ.get("ANALYSIS_DIR", PROJECT / "analysis"))
OUT = ROOT / "data" / "marts"

ACCIDENT_YEARS = [str(y) for y in range(2020, 2026)]
FLEET_YEAR = "2025"
# Eisenach (16056) merged into Wartburgkreis (16063) in July 2021.
BOUNDARY_REMAP = {"16056": "16063"}
# KBA prints one car stock on 07211 under the name TRIER-SAARBURG; it cannot be split
# between the city of Trier (07211) and the Landkreis Trier-Saarburg (07235).
NO_CAR_FEATURES = {"07211", "07235"}

FRAUD_SOURCES = [
    "gdv_claim_fraud",
    "bka_insurance_fraud",
    "larmtjanst_fraud",
    "cbv_fraud",
    "alfa_fraud",
    "abi_fraud",
    "insurance_europe_fraud",
]


def load_raw() -> pd.DataFrame:
    cols = ["source_dataset", "source_file", "geo_level", "geo_code", "geo_name", "year",
            "measure", "breakdown", "value", "unit", "source_note"]
    df = pd.read_csv(RAW_CSV, dtype=str, usecols=cols, low_memory=False)
    df["value_num"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def accident_features(df: pd.DataFrame) -> pd.DataFrame:
    acc = df[(df.source_dataset == "unfallatlas") & (df.year.isin(ACCIDENT_YEARS))].copy()
    acc["geo_code"] = acc["geo_code"].replace(BOUNDARY_REMAP)
    sums = acc.groupby(["geo_code", "measure", "breakdown"])["value_num"].sum()

    def part(measure, *breakdowns):
        keys = [(measure, b) for b in breakdowns]
        frames = [sums.xs(k, level=["measure", "breakdown"]) for k in keys if k in sums.droplevel(0).index]
        if not frames:
            return pd.Series(dtype=float)
        return pd.concat(frames, axis=1).sum(axis=1)

    total = part("accidents_total", "all")
    out = pd.DataFrame({"accidents_2020_2025": total})
    out["accidents_per_year"] = total / len(ACCIDENT_YEARS)
    sev = part("accidents_by_severity", "persons_killed", "seriously_injured")
    out["share_killed_or_serious"] = sev / total
    out["share_fatal"] = part("accidents_by_severity", "persons_killed") / total
    out["share_darkness"] = part("accidents_by_light", "darkness") / total
    out["share_wet_road"] = part("accidents_by_road_surface", "wet_or_damp") / total
    out["share_winter_road"] = part("accidents_by_road_surface", "winter_slippery") / total
    out["share_weekend"] = part("accidents_by_weekday", "saturday", "sunday") / total
    out["share_night_22_05"] = part("accidents_by_hour", *[f"hour_{h:02d}" for h in (22, 23, 0, 1, 2, 3, 4, 5)]) / total
    out["share_rush_hour"] = part("accidents_by_hour", *[f"hour_{h:02d}" for h in (7, 8, 16, 17, 18)]) / total
    out["share_rear_end"] = part("accidents_by_kind", "collision_with_vehicle_ahead") / total
    out["share_left_road"] = part("accidents_by_kind", "left_the_road_to_the_left", "left_the_road_to_the_right") / total
    out["share_turning_crossing"] = part("accidents_by_kind", "collision_while_turning_or_crossing") / total
    out["share_with_bicycle"] = part("accidents_involving", "bicycle") / total
    out["share_with_pedestrian"] = part("accidents_involving", "pedestrian") / total
    out["share_with_motorcycle"] = part("accidents_involving", "motorcycle") / total
    out["share_with_goods_vehicle"] = part("accidents_involving", "goods_vehicle") / total

    yearly = (
        acc[(acc.measure == "accidents_total") & (acc.breakdown == "all")]
        .groupby(["geo_code", "year"])["value_num"].sum().unstack()
    )
    years = np.array([int(y) for y in yearly.columns])
    centred = years - years.mean()

    def slope(row):
        mask = row.notna().to_numpy()
        if mask.sum() < 4 or row.mean() == 0:
            return np.nan
        y = row.to_numpy()[mask]
        x = centred[mask]
        return float(np.polyfit(x, y, 1)[0] / y.mean())

    out["accident_trend_per_year"] = yearly.apply(slope, axis=1)
    return out


def fleet_features(df: pd.DataFrame, year: str = FLEET_YEAR) -> pd.DataFrame:
    kba = df[df.source_dataset.isin(["kba_vehicle_stock", "kba_passenger_car_detail"]) & (df.year == year)]
    stock = kba[kba.source_dataset == "kba_vehicle_stock"].pivot_table(
        index="geo_code", columns="measure", values="value_num", aggfunc="sum")
    fuel = kba[kba.measure == "passenger_cars_by_fuel"].pivot_table(
        index="geo_code", columns="breakdown", values="value_num", aggfunc="sum")
    euro = kba[kba.measure == "passenger_cars_by_euro_standard"].pivot_table(
        index="geo_code", columns="breakdown", values="value_num", aggfunc="sum")
    cars = stock["passenger_cars"]
    out = pd.DataFrame(index=stock.index)
    out["motorcycles"] = stock.get("motorcycles")
    out["trucks"] = stock.get("trucks")
    out["share_diesel"] = fuel.get("diesel") / cars
    out["share_petrol"] = fuel.get("benzin") / cars
    bev = fuel.get("elektro_bev")
    if "elektro" in fuel:
        bev = bev.fillna(fuel["elektro"]) if bev is not None else fuel["elektro"]
    out["share_bev"] = bev / cars
    out["share_hybrid"] = fuel.get("hybrid_insgesamt") / cars
    old = euro.reindex(columns=["euro_1", "euro_2", "euro_3", "euro_4", "ohne_emissions_gruppe"]).sum(axis=1, min_count=1)
    out["share_old_fleet_euro4_or_older"] = old / cars
    out["share_engine_2000cc_plus"] = stock.get("passenger_cars_engine_2000cc_or_more") / cars
    first = df[(df.source_dataset == "kba_vehicle_stock") & (df.measure == "passenger_cars") & (df.year == "2018")]
    first = first.set_index("geo_code")["value_num"]
    out["car_growth_2018_2025"] = cars / first.reindex(cars.index) - 1
    out["passenger_cars"] = cars
    return out


def build_fleet_snapshot(df: pd.DataFrame, districts: pd.DataFrame, year: str) -> pd.DataFrame:
    """Fleet features for a later KBA year, used for drift monitoring against the training year."""
    fleet = fleet_features(df, year).drop(columns=["car_growth_2018_2025"])
    fleet.index = fleet.index.map(lambda c: BOUNDARY_REMAP.get(c, c))
    base = districts.set_index("geo_code")[["population_2024"]]
    snap = base.join(fleet, how="left")
    pop = snap["population_2024"]
    snap["cars_per_1000_people"] = snap["passenger_cars"] / pop * 1000
    snap["motorcycles_per_1000_people"] = snap["motorcycles"] / pop * 1000
    snap["trucks_per_1000_people"] = snap["trucks"] / pop * 1000
    snap.loc[snap.index.isin(NO_CAR_FEATURES)] = np.nan
    snap["fleet_year"] = int(year)
    return snap.drop(columns=["population_2024", "motorcycles", "trucks", "passenger_cars"]).reset_index()


def build_districts(df: pd.DataFrame) -> pd.DataFrame:
    base = pd.read_csv(ANALYSIS / "germany_districts.csv", dtype={"geo_code": str})
    feats = base.set_index("geo_code")
    acc = accident_features(df)
    fleet = fleet_features(df)
    feats = feats.join(acc, how="left").join(fleet, how="left")

    cars = feats["passenger_cars_2025"]
    pop = feats["population_2024"]
    feats["cars_per_1000_people"] = cars / pop * 1000
    feats["accidents_per_1000_cars"] = feats["accidents_per_year"] / cars * 1000
    feats["accidents_per_10k_people"] = feats["accidents_per_year"] / pop * 10000
    feats["motorcycles_per_1000_people"] = feats["motorcycles"] / pop * 1000
    feats["trucks_per_1000_people"] = feats["trucks"] / pop * 1000
    feats["share_male"] = feats["population_male"] / pop
    feats["is_urban"] = (feats["area_type"] == "urban").astype(int)
    feats["log_density"] = np.log10(feats["population_per_km2"])
    car_cols = [c for c in feats.columns if c.startswith(("cars_per", "accidents_per_1000_cars", "share_diesel",
                                                          "share_petrol", "share_bev", "share_hybrid", "share_old",
                                                          "share_engine", "car_growth", "motorcycles_per",
                                                          "trucks_per"))]
    feats.loc[feats.index.isin(NO_CAR_FEATURES), car_cols] = np.nan
    feats = feats.drop(columns=["motorcycles", "trucks", "passenger_cars"])
    feats.index.name = "geo_code"
    return feats.reset_index()


def _car_weighted(g: pd.DataFrame, cars: pd.Series, col: str) -> float | None:
    mask = g[col].notna() & (cars > 0)
    return float(np.average(g.loc[mask, col], weights=cars[mask])) if mask.any() else None


def build_states(districts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for state, g in districts.groupby("bundesland"):
        cars = g["passenger_cars_2025"].fillna(0)

        def weighted(col, g=g, cars=cars):
            return _car_weighted(g, cars, col)

        rows.append({
            "bundesland": state,
            "districts": len(g),
            "population_2024": int(g["population_2024"].sum()),
            "passenger_cars_2025": int(cars.sum()),
            "accidents_2025": int(g["accidents_2025"].fillna(0).sum()),
            "liability_class_car_weighted": weighted("liability_class_2027"),
            "comprehensive_class_car_weighted": weighted("comprehensive_class_2027"),
            "partial_cover_class_car_weighted": weighted("partial_cover_class_2027"),
            "accidents_per_1000_cars": float(g["accidents_2025"].fillna(0).sum() / cars.sum() * 1000),
            "share_bev": weighted("share_bev"),
        })
    return pd.DataFrame(rows).sort_values("liability_class_car_weighted", ascending=False)


def build_trends(df: pd.DataFrame) -> pd.DataFrame:
    acc = df[(df.source_dataset == "unfallatlas") & (df.measure == "accidents_total") & (df.breakdown == "all")]
    nat = acc.groupby("year")["value_num"].sum()
    states = acc.assign(state=acc.geo_code.str[:2]).groupby("year")["state"].nunique()
    sev = df[(df.source_dataset == "unfallatlas") & (df.measure == "accidents_by_severity")]
    sev = sev.pivot_table(index="year", columns="breakdown", values="value_num", aggfunc="sum")
    cars = df[(df.source_dataset == "kba_vehicle_stock") & (df.measure == "passenger_cars") & (df.geo_level == "district")]
    cars = cars.groupby("year")["value_num"].sum()
    out = pd.DataFrame({"accidents_with_injury": nat, "states_covered": states}).join(sev).join(cars.rename("passenger_cars"))
    out["complete"] = out["states_covered"] == 16
    out.index.name = "year"
    return out.reset_index()


def build_profiles(df: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    acc = df[(df.source_dataset == "unfallatlas") & (df.year.isin(ACCIDENT_YEARS))
             & (df.measure.isin(["accidents_by_hour", "accidents_by_month", "accidents_by_weekday"]))].copy()
    acc["geo_code"] = acc["geo_code"].replace(BOUNDARY_REMAP)
    area = districts.set_index("geo_code")["area_type"]
    acc["area_type"] = acc["geo_code"].map(area)
    prof = acc.groupby(["area_type", "measure", "breakdown"])["value_num"].sum().reset_index()
    prof["share"] = prof["value_num"] / prof.groupby(["area_type", "measure"])["value_num"].transform("sum")
    return prof


def build_fraud(df: pd.DataFrame) -> pd.DataFrame:
    fraud = df[df.source_dataset.isin(FRAUD_SOURCES)].copy()
    return fraud[["source_dataset", "source_file", "geo_code", "geo_name", "year", "measure",
                  "breakdown", "value_num", "unit", "source_note"]].rename(columns={"value_num": "value"})


def build_overview(districts, trends, europe, fraud, claims) -> dict:
    latest = trends[trends.complete].iloc[-1]
    police = fraud[(fraud.source_dataset == "bka_insurance_fraud") & (fraud.measure == "recorded_offences")
                   & (fraud.breakdown == "insurance_fraud_and_abuse_517400")]
    police_latest = police.sort_values("year").iloc[-1]
    gdv = fraud[(fraud.source_dataset == "gdv_claim_fraud") & (fraud.year == "2024")].set_index(["measure", "breakdown"])["value"]
    de = europe[(europe.geo_code == "DE") & (europe.year == 2024)].iloc[0]
    top = districts.sort_values("liability_class_2027", ascending=False).head(6)
    return {
        "population_2024": int(districts["population_2024"].sum()),
        "districts": int(len(districts)),
        "passenger_cars_2026": int(districts["passenger_cars_2026"].fillna(0).sum()),
        "accidents_with_injury_latest": int(latest["accidents_with_injury"]),
        "accidents_year": int(latest["year"]),
        "police_insurance_fraud_cases": int(police_latest["value"]),
        "police_year": int(police_latest["year"]),
        "gdv_suspicious_share_pct": float(gdv[("suspicious_claims_share", "all_lines")]),
        "gdv_fraud_loss_bn_eur": float(gdv[("estimated_fraud_loss", "property_and_casualty_more_than")]),
        "germany_road_deaths_per_100k_2024": float(de["road_deaths_per_100000"]),
        "germany_nonlife_claims_ratio_2024": float(de["nonlife_claims_ratio"]),
        "highest_liability_districts": top[["geo_code", "geo_name", "liability_class_2027"]].to_dict("records"),
        "simulated_claims": int(len(claims)),
        "simulated_triage": claims["triage"].value_counts().to_dict(),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_raw()
    districts = build_districts(df)
    states = build_states(districts)
    trends = build_trends(df)
    profiles = build_profiles(df, districts)
    fraud = build_fraud(df)
    europe = pd.read_csv(ANALYSIS / "eu_countries.csv")
    claims = pd.read_csv(ANALYSIS / "simulated_claims_inbox.csv", dtype={"geo_code": str})
    rules = pd.read_csv(ANALYSIS / "fraud_red_flag_rules.csv")

    districts.to_csv(OUT / "districts.csv", index=False)
    states.to_csv(OUT / "states.csv", index=False)
    trends.to_csv(OUT / "germany_trends.csv", index=False)
    profiles.to_csv(OUT / "accident_profiles.csv", index=False)
    fraud.to_csv(OUT / "fraud_landscape.csv", index=False)
    europe.to_csv(OUT / "europe.csv", index=False)
    claims.to_csv(OUT / "claims_inbox.csv", index=False)
    rules.to_csv(OUT / "fraud_rules.csv", index=False)
    build_fleet_snapshot(df, districts, "2026").to_csv(OUT / "fleet_2026.csv", index=False)
    overview = build_overview(districts, trends, europe, fraud, claims)
    (OUT / "overview.json").write_text(json.dumps(overview, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"districts {len(districts)}, states {len(states)}, trend years {len(trends)}, "
          f"fraud rows {len(fraud)}, europe rows {len(europe)}, claims {len(claims)}")


if __name__ == "__main__":
    main()
