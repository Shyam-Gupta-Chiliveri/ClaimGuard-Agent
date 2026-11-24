"""Feature drift: Population Stability Index of the newest KBA fleet (2026) against the
training reference (2025) stored in the production Regionalklasse artifact.

PSI < 0.10 stable, 0.10-0.25 watch, > 0.25 retrain.
Usage: python -m ml.drift   (writes reports/drift.json; exit 0 always, CI reads the status)
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from core.paths import MARTS, REPORTS
from ml import registry

WATCH, ACT = 0.10, 0.25


def psi(reference_quantiles: list[float], current: pd.Series) -> float:
    edges = np.unique(np.asarray(reference_quantiles, dtype=float))
    if len(edges) < 3:
        return 0.0
    inner = edges[1:-1]
    expected = np.full(len(inner) + 1, 1 / (len(inner) + 1))
    counts = np.bincount(np.searchsorted(inner, current.dropna().to_numpy(), side="right"), minlength=len(inner) + 1)
    actual = counts / max(counts.sum(), 1)
    actual = np.clip(actual, 1e-4, None)
    expected = np.clip(expected, 1e-4, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def run() -> dict:
    artifact, _, _ = registry.load("regionalklasse")
    ref = artifact["reference"]
    current = pd.read_csv(MARTS / "fleet_2026.csv", dtype={"geo_code": str})
    rows = []
    for feat in [c for c in current.columns if c in ref]:
        value = psi(ref[feat]["quantiles"], current[feat])
        status = "retrain" if value > ACT else "watch" if value > WATCH else "stable"
        rows.append({"feature": feat, "psi": round(value, 4), "status": status,
                     "reference_mean": round(ref[feat]["mean"], 4),
                     "current_mean": round(float(current[feat].mean()), 4)})
    rows.sort(key=lambda r: -r["psi"])
    overall = "retrain" if any(r["status"] == "retrain" for r in rows) else \
              "watch" if any(r["status"] == "watch" for r in rows) else "stable"
    result = {"reference": "KBA 1 Jan 2025 (training)", "current": "KBA 1 Jan 2026",
              "model_version": registry.production("regionalklasse"), "status": overall,
              "thresholds": {"watch": WATCH, "retrain": ACT}, "features": rows}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "drift.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    r = run()
    print(r["status"], [(f["feature"], f["psi"]) for f in r["features"][:6]])
