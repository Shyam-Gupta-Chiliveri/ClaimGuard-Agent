"""Unsupervised claim anomaly scorer (Isolation Forest) that sits next to the red-flag rules.

Trained on the SIMULATED claims inbox. There are no real fraud labels: the triage bands come
from the rules themselves, so any "accuracy" against them would be circular. The model is
used only as a second opinion that surfaces numerically unusual claims the rules miss, and
the overlap with the rule bands is reported as a descriptive check, not as performance.

Usage: python -m ml.anomaly
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from core.paths import MARTS
from ml import registry

FEATURES = [
    "days_after_policy_start",
    "days_before_policy_expiry",
    "days_to_report",
    "prior_claims_12_months",
    "vehicle_age_years",
    "log_claimed_amount",
    "claimed_to_estimate_ratio",
    "injury",
    "police_report",
    "witness",
]
CONTAMINATION = 0.05
SEED = 2026


def featurize(claims: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=claims.index)
    for col in FEATURES[:5]:
        X[col] = pd.to_numeric(claims[col], errors="coerce")
    claimed = pd.to_numeric(claims["claimed_amount_eur"], errors="coerce")
    est = pd.to_numeric(claims["repair_estimate_eur"], errors="coerce").replace(0, np.nan)
    X["log_claimed_amount"] = np.log1p(claimed)
    X["claimed_to_estimate_ratio"] = (claimed / est).fillna(1.0)
    for col in ("injury", "police_report", "witness"):
        X[col] = claims[col].astype(str).str.lower().isin(["yes", "true", "1"]).astype(int)
    return X[FEATURES].fillna(0)


def train() -> dict:
    claims = pd.read_csv(MARTS / "claims_inbox.csv", dtype={"geo_code": str})
    X = featurize(claims)
    model = IsolationForest(n_estimators=300, contamination=CONTAMINATION, random_state=SEED).fit(X)
    raw = -model.score_samples(X)
    lo, hi = float(np.quantile(raw, 0.01)), float(np.quantile(raw, 0.99))
    score = np.clip((raw - lo) / (hi - lo), 0, 1)
    threshold = float(np.quantile(score, 1 - CONTAMINATION))
    flagged = score >= threshold
    overlap = (
        pd.DataFrame({"band": claims["triage"], "flagged": flagged})
        .groupby("band")["flagged"].mean().round(3).to_dict()
    )
    green_but_flagged = int(((claims["triage"] == "green") & flagged).sum())
    metrics = {
        "headline": {"contamination": CONTAMINATION, "flagged": int(flagged.sum()),
                     "green_claims_flagged_for_second_look": green_but_flagged},
        "flag_rate_by_rule_band": overlap,
        "note": "SIMULATED claims. Descriptive overlap with rule bands, not a fraud accuracy.",
        "gate": {"passed": True, "checks": {}},
    }
    artifact = {"model": model, "features": FEATURES, "scale": [lo, hi], "threshold": threshold}
    version = "v" + registry.content_hash((MARTS / "claims_inbox.csv").read_bytes(),
                                          json.dumps([FEATURES, CONTAMINATION, SEED]).encode())
    card = (
        f"# Model card: claim anomaly scorer ({version})\n\n"
        "Isolation Forest over ten numeric and yes/no claim fields. Trained on 800 SIMULATED claims.\n\n"
        f"- Flags the top {CONTAMINATION:.0%} most unusual claims for a second look.\n"
        f"- Flag rate by rule band (descriptive only): {overlap}.\n"
        f"- Green claims the rules would pass but the model flags: {green_but_flagged}.\n"
        "- Not a fraud classifier. Real use needs investigated claims with outcomes (e.g. insurer SIU files).\n"
    )
    registry.register("claim_anomaly", version, artifact, metrics, {"model_card.md": card})
    registry.promote("claim_anomaly", version)
    print(json.dumps({"version": version, **metrics["headline"], "by_band": overlap}, indent=2))
    return metrics


def score(artifact: dict, claim: dict) -> dict:
    X = featurize(pd.DataFrame([claim]))
    raw = -artifact["model"].score_samples(X)[0]
    lo, hi = artifact["scale"]
    s = float(np.clip((raw - lo) / (hi - lo), 0, 1))
    return {"anomaly_score": round(s, 3), "second_look": s >= artifact["threshold"],
            "threshold": round(artifact["threshold"], 3)}


if __name__ == "__main__":
    train()
