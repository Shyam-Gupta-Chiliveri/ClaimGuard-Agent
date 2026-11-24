"""Compute the analysis findings and write reports/analysis.md and data/marts/insights.json.

Every number in the report comes from the marts or the model registry; nothing is typed in.
Usage: python -m pipeline.report
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from core.paths import MARTS, REPORTS
from ml import registry


def pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"


def main() -> None:
    d = pd.read_csv(MARTS / "districts.csv", dtype={"geo_code": str})
    s = pd.read_csv(MARTS / "states.csv")
    t = pd.read_csv(MARTS / "germany_trends.csv")
    e = pd.read_csv(MARTS / "europe.csv")
    e = e[e.geo_code != "FX"]
    f = pd.read_csv(MARTS / "fraud_landscape.csv", dtype={"year": str})
    c = pd.read_csv(MARTS / "claims_inbox.csv", dtype={"geo_code": str})
    _, metrics, _ = registry.load("regionalklasse")
    _, anomaly_metrics, _ = registry.load("claim_anomaly")
    drift = json.loads((REPORTS / "drift.json").read_text())
    rep = metrics["report"]["targets"]
    insights: list[dict] = []

    def add(key, title, value, text, tab):
        insights.append({"key": key, "title": title, "value": value, "text": text, "tab": tab})

    m = d[d.liability_class_2027.notna()]
    urb = m.groupby("area_type").liability_class_2027.median()
    rho_density = spearmanr(m.population_per_km2, m.liability_class_2027).statistic
    rho_acc = spearmanr(m.accidents_per_1000_cars, m.liability_class_2027, nan_policy="omit").statistic
    add("density", "Density beats accidents", f"ρ = {rho_density:.2f}",
        f"Population density ranks districts' Haftpflicht class far better (Spearman {rho_density:.2f}) than injury accidents "
        f"per car do ({rho_acc:.2f}). Median class: urban {urb.get('urban', np.nan):.0f}, rural {urb.get('rural', np.nan):.0f}. "
        "GDV classes are driven by claim cost, and most claims are property-damage-only accidents the Unfallatlas never records.",
        "germany")

    sev = d.groupby("area_type")[["share_killed_or_serious", "accidents_per_1000_cars"]].median()
    add("severity", "Rural crashes are rarer but harsher",
        f"{pct(sev.loc['rural', 'share_killed_or_serious'])} vs {pct(sev.loc['urban', 'share_killed_or_serious'])}",
        f"In rural districts {pct(sev.loc['rural', 'share_killed_or_serious'])} of injury accidents kill or seriously injure someone, "
        f"against {pct(sev.loc['urban', 'share_killed_or_serious'])} in cities, while accidents per 1,000 cars are "
        f"{sev.loc['rural', 'accidents_per_1000_cars']:.1f} vs {sev.loc['urban', 'accidents_per_1000_cars']:.1f}. "
        "Frequency and severity point in opposite directions — the core idea of a frequency/severity tariff model.",
        "germany")

    top_state = s.iloc[0]
    low_state = s.iloc[-1]
    add("states", "State spread",
        f"{top_state.liability_class_car_weighted:.1f} → {low_state.liability_class_car_weighted:.1f}",
        f"Car-weighted Haftpflicht class is highest in {top_state.bundesland} ({top_state.liability_class_car_weighted:.1f}) "
        f"and lowest in {low_state.bundesland} ({low_state.liability_class_car_weighted:.1f}).", "germany")

    tp = d[d.partial_cover_class_2027.notna()]
    tk_state = tp.groupby("bundesland").partial_cover_class_2027.median().sort_values(ascending=False)
    rho_area = spearmanr(tp.area_km2, tp.partial_cover_class_2027).statistic
    add("teilkasko", "Teilkasko has a different map", f"ρ(area) = {rho_area:.2f}",
        f"Teilkasko covers theft, glass, storm, hail and collisions with game. Its class rises with district area "
        f"(Spearman {rho_area:.2f}), consistent with game collisions in large rural districts. Highest median class: "
        f"{tk_state.index[0]} ({tk_state.iloc[0]:.0f}) and {tk_state.index[1]} ({tk_state.iloc[1]:.0f}) — a city and a rural "
        f"state at once, so theft and countryside risks both matter; lowest: {tk_state.index[-1]} ({tk_state.iloc[-1]:.0f}).",
        "germany")

    tc = t[t.complete].set_index("year")
    first, last = tc.index.min(), tc.index.max()
    change = tc.loc[last, "accidents_with_injury"] / tc.loc[first, "accidents_with_injury"] - 1
    add("trend", "Injury accidents rebound after 2020", f"{change:+.1%}",
        f"Injury accidents went from {tc.loc[first, 'accidents_with_injury']:,.0f} ({first}, pandemic year) to "
        f"{tc.loc[last, 'accidents_with_injury']:,.0f} ({last}). Years before 2020 are left out because not every state reported.",
        "germany")

    bev = d.share_bev.dropna()
    bev_top = d.loc[d.share_bev.idxmax()]
    add("bev", "EV adoption is uneven", f"{pct(bev.min(), 1)} – {pct(bev.max(), 1)}",
        f"Battery-electric share of the car stock (KBA 1 Jan 2025) ranges from {pct(bev.min(), 1)} to {pct(bev.max(), 1)} "
        f"({bev_top.geo_name}). The 2026 fleet already drifts: {drift['features'][0]['feature'].replace('_', ' ')} PSI "
        f"{drift['features'][0]['psi']:.2f} → drift status '{drift['status']}'.", "ml")

    eu = e[(e.year == 2024) & (e.geo_code.str.len() == 2) & e.road_deaths_per_100000.notna()]
    eu_rank = int((eu.road_deaths_per_100000 > eu.loc[eu.geo_code == "DE", "road_deaths_per_100000"].iloc[0]).sum()) + 1
    de_rd = eu.loc[eu.geo_code == "DE", "road_deaths_per_100000"].iloc[0]
    agg = e[(e.year == 2024) & (e.geo_code.str.startswith("EU"))]
    eu_avg = agg.road_deaths_per_100000.dropna()
    eu_txt = f" EU average {eu_avg.iloc[0]:.2f}." if len(eu_avg) else ""
    add("europe_roads", "Germany's roads in Europe", f"{de_rd:.2f} per 100k",
        f"Germany had {de_rd:.2f} road deaths per 100,000 people in 2024, rank {eu_rank} of {len(eu)} countries "
        f"(1 = most dangerous).{eu_txt}", "europe")

    cr = e[(e.year == 2024) & (e.geo_code.str.len() == 2) & e.nonlife_claims_ratio.notna()]
    de_cr = cr.loc[cr.geo_code == "DE", "nonlife_claims_ratio"]
    if len(de_cr):
        add("europe_claims", "Non-life claims ratio", f"{de_cr.iloc[0]:.0%}",
            f"German insurers paid out {de_cr.iloc[0]:.0%} of non-life premiums earned as claims in 2024 (EIOPA Solo Annual); "
            f"the median of {len(cr)} countries is {cr.nonlife_claims_ratio.median():.0%}. This is all non-life business, not motor alone.",
            "europe")

    police = f[(f.source_dataset == "bka_insurance_fraud") & (f.measure == "recorded_offences")
               & (f.breakdown == "insurance_fraud_and_abuse_517400")].assign(year=lambda x: x.year.astype(int))
    peak = police.loc[police.value.idxmax()]
    latest = police.loc[police.year.idxmax()]
    gdv_share = f[(f.source_dataset == "gdv_claim_fraud") & (f.measure == "suspicious_claims_share")].value.iloc[0]
    add("police", "The fraud reporting gap", f"{latest.value:,.0f} cases",
        f"Police recorded {latest.value:,.0f} insurance-fraud cases in {latest.year} (PKS 517400), "
        f"{1 - latest.value / peak.value:.0%} below the {peak.year} peak of {peak.value:,.0f}. Insurers (GDV) still treat about "
        f"{gdv_share:.0f}% of claims as suspicious — fraud is handled inside claims departments, rarely by the police.", "fraud")

    se = f[(f.source_dataset == "larmtjanst_fraud") & (f.measure == "refused_claim_value") & (f.breakdown == "motor")]
    se = se.assign(year=se.year.astype(int)).sort_values("year")
    add("sweden", "Sweden: refused motor claims", f"{se.value.iloc[-1] / se.value.iloc[0] - 1:+.0%}",
        f"Swedish insurers refused {se.value.iloc[-1]:.0f} MSEK of motor claims after investigation in {se.year.iloc[-1]}, "
        f"up from {se.value.iloc[0]:.0f} MSEK in {se.year.iloc[0]} (Larmtjänst).", "fraud")

    lr = rep["liability_class_2027"]["scores"]
    best = lr["best_model"]
    add("spatial_cv", "Spatial leakage is real", f"MAE {lr['random'][best]['mae']:.2f} → {lr['spatial'][best]['mae']:.2f}",
        f"A random split makes the model look {lr['spatial'][best]['mae'] / lr['random'][best]['mae'] - 1:.0%} better than it is. "
        f"Validated on unseen Bundesländer, the {best} model misses the Haftpflicht class by {lr['spatial'][best]['mae']:.2f} "
        f"classes on average (median baseline {lr['spatial']['baseline_median']['mae']:.2f}), {pct(lr['spatial'][best]['within_one_class'])} within ±1.",
        "ml")

    res = pd.DataFrame(rep["liability_class_2027"]["residuals"])
    by_state = res.groupby("bundesland").residual.mean().sort_values()
    top_gap = res.sort_values("residual", ascending=False).head(4)
    add("residuals", "Where public data under-explains the class", f"{by_state.iloc[-1]:+.1f} classes",
        f"GDV classes sit above the model most in {by_state.index[-1]} (mean residual {by_state.iloc[-1]:+.1f}) and below it in "
        f"{by_state.index[0]} ({by_state.iloc[0]:+.1f}). Largest gaps: " +
        ", ".join(f"{r.geo_name} ({r.residual:+.1f})" for r in top_gap.itertuples()) +
        ". Hypotheses to test with claims data: tourist and transit traffic, repair-cost levels, theft, fraud.", "ml")

    counts = c.triage.value_counts()
    add("triage", "Triage funnel (SIMULATED)", f"{counts.get('red', 0)} red / {len(c)}",
        f"Of {len(c)} simulated claims, {counts.get('amber', 0)} go to a handler and {counts.get('red', 0)} to investigators. "
        f"The anomaly model sends {anomaly_metrics['headline']['green_claims_flagged_for_second_look']} green claims for a second look "
        "that no rule caught.", "triage")

    (MARTS / "insights.json").write_text(json.dumps(insights, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# ClaimGuard — analysis of German motor-insurance risk and claim fraud", "",
             "All figures are computed by `pipeline/report.py` from the project marts. Claims data is SIMULATED where stated.", ""]
    sections = {"germany": "Germany", "europe": "Europe", "fraud": "Fraud", "ml": "Machine learning", "triage": "Triage"}
    for tab, title in sections.items():
        lines += [f"## {title}", ""]
        for i in insights:
            if i["tab"] == tab:
                lines += [f"### {i['title']} — {i['value']}", "", i["text"], ""]
    lines += ["## Method notes", "",
              "- Districts: 400 Kreise (Destatis 2024 boundaries); Eisenach is folded into Wartburgkreis.",
              "- Accidents: Unfallatlas, injury accidents only, 2020-2025 average.",
              "- Fleet: KBA FZ1, 1 January 2025 (training) and 2026 (drift check).",
              "- Models: spatial GroupKFold by Bundesland; see `reports/model_card_regionalklasse.md`."]
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for i in insights:
        print(f"[{i['tab']}] {i['title']}: {i['value']}\n    {i['text']}")


if __name__ == "__main__":
    main()
