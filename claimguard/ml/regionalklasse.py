"""Train, evaluate, gate and register the Regionalklasse models.

Validation is spatial: GroupKFold by Bundesland, so every fold predicts whole states the
model has never seen. A random KFold is reported next to it to show how much neighbouring
districts leak into an ordinary split.

Usage: python -m ml.regionalklasse [--no-promote]
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.base import clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold, KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from core.paths import CONFIGS, MARTS, REPORTS
from ml import registry

CONFIG_PATH = CONFIGS / "regionalklasse.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def load_frame(cfg: dict[str, Any]) -> pd.DataFrame:
    df = pd.read_csv(MARTS / "districts.csv", dtype={"geo_code": str})
    df["area_km2"] = np.log10(df["area_km2"])
    return df


def make_models(cfg: dict[str, Any]) -> dict[str, Any]:
    p = cfg["models"]
    return {
        "baseline_median": DummyRegressor(strategy="median"),
        "ridge": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=p["ridge"]["alpha"])),
        "gradient_boosting": HistGradientBoostingRegressor(random_state=cfg["seed"], **p["gradient_boosting"]),
    }


def metrics(y_true: np.ndarray, y_pred: np.ndarray, lo: int, hi: int) -> dict[str, float]:
    cls = np.clip(np.rint(y_pred), lo, hi)
    rho = spearmanr(y_true, y_pred).statistic if np.std(y_pred) > 0 else 0.0
    return {
        "mae": float(np.mean(np.abs(y_true - y_pred))),
        "rmse": float(np.sqrt(np.mean((y_true - y_pred) ** 2))),
        "exact_class": float(np.mean(cls == y_true)),
        "within_one_class": float(np.mean(np.abs(cls - y_true) <= 1)),
        "spearman": float(rho),
    }


def out_of_fold(model, X, y, splitter, groups=None) -> np.ndarray:
    pred = np.zeros(len(y))
    for train, test in splitter.split(X, y, groups):
        m = clone(model).fit(X.iloc[train], y[train])
        pred[test] = m.predict(X.iloc[test])
    return pred


def spatial_importance(model, X, y, groups, seed) -> pd.DataFrame:
    """Permutation importance measured on held-out states only."""
    rows = []
    for fold, (train, test) in enumerate(GroupKFold(n_splits=8).split(X, y, groups)):
        m = clone(model).fit(X.iloc[train], y[train])
        r = permutation_importance(m, X.iloc[test], y[test], n_repeats=10, random_state=seed + fold,
                                   scoring="neg_mean_absolute_error")
        rows.append(r.importances_mean)
    imp = pd.DataFrame(rows, columns=X.columns).mean().sort_values(ascending=False)
    return imp.rename("mae_increase").reset_index().rename(columns={"index": "feature"})


def partial_dependence(model, X, features, grid=20) -> dict[str, dict[str, list[float]]]:
    out = {}
    for f in features:
        values = X[f].dropna()
        xs = np.unique(np.quantile(values, np.linspace(0.05, 0.95, grid)))
        ys = []
        for v in xs:
            Xv = X.copy()
            Xv[f] = v
            ys.append(float(model.predict(Xv).mean()))
        out[f] = {"x": [float(v) for v in xs], "y": ys}
    return out


def gate(cfg, target, scores) -> dict[str, Any]:
    rule = cfg["gate"].get(target)
    if not rule:
        return {"passed": True, "checks": {}}
    best = scores["spatial"][scores["best_model"]]
    base = scores["spatial"]["baseline_median"]
    checks = {
        "mae_below_max": best["mae"] <= rule["max_mae"],
        "within_one_above_min": best["within_one_class"] >= rule["min_within_one"],
        "beats_baseline": best["mae"] <= base["mae"] * (1 - rule["must_beat_baseline_by"]),
    }
    return {"passed": all(checks.values()), "checks": checks, "rule": rule}


def train(promote: bool = True) -> dict[str, Any]:
    cfg = load_config()
    df = load_frame(cfg)
    features = cfg["features"]
    seed = cfg["seed"]
    models = make_models(cfg)
    artifact = {"features": features, "targets": {}, "medians": {}, "reference": {}}
    report: dict[str, Any] = {"targets": {}}

    for target, spec in cfg["targets"].items():
        data = df[df[target].notna()].reset_index(drop=True)
        X, y, groups = data[features], data[target].to_numpy(), data[cfg["group_column"]]
        lo, hi = spec["min"], spec["max"]
        scores: dict[str, Any] = {"spatial": {}, "random": {}}
        oof_spatial = {}
        for name, model in models.items():
            p_sp = out_of_fold(model, X, y, GroupKFold(n_splits=8), groups)
            p_rd = out_of_fold(model, X, y, KFold(cfg["random_folds"], shuffle=True, random_state=seed))
            scores["spatial"][name] = metrics(y, p_sp, lo, hi)
            scores["random"][name] = metrics(y, p_rd, lo, hi)
            oof_spatial[name] = p_sp
        candidates = [m for m in models if m != "baseline_median"]
        best = min(candidates, key=lambda m: scores["spatial"][m]["mae"])
        scores["best_model"] = best
        prev_col = target.replace("2027", "2026")
        if prev_col in data:
            scores["persistence_2026"] = metrics(y, data[prev_col].fillna(np.median(y)).to_numpy(), lo, hi)

        final = clone(models[best]).fit(X, y)
        importance = spatial_importance(models[best], X, y, groups, seed)
        top = importance.feature.head(6).tolist()
        pdp = partial_dependence(final, X, top)
        pred = oof_spatial[best]
        residuals = data[["geo_code", "geo_name", "bundesland", "area_type", target]].copy()
        residuals["predicted_spatial_cv"] = pred.round(2)
        residuals["residual"] = (y - pred).round(2)

        artifact["targets"][target] = {"model": final, "name": best, "min": lo, "max": hi, "label": spec["label"]}
        scores["gate"] = gate(cfg, target, scores)
        report["targets"][target] = {
            "label": spec["label"],
            "n": int(len(data)),
            "scores": scores,
            "importance": importance.to_dict("records"),
            "partial_dependence": pdp,
            "residuals": residuals.sort_values("residual").to_dict("records"),
        }

    artifact["medians"] = df[features].median().to_dict()
    artifact["reference"] = {
        f: {"quantiles": df[f].quantile(np.linspace(0, 1, 11)).tolist(), "mean": float(df[f].mean())}
        for f in features
    }

    headline_target = "liability_class_2027"
    head = report["targets"][headline_target]["scores"]
    gate_result = head["gate"]
    metrics_doc = {
        "headline": {"target": headline_target, "model": head["best_model"], **head["spatial"][head["best_model"]]},
        "gate": gate_result,
        "report": report,
    }
    data_bytes = (MARTS / "districts.csv").read_bytes()
    version = "v" + registry.content_hash(data_bytes, CONFIG_PATH.read_bytes())
    card = model_card(cfg, report, version)
    registry.register(cfg["model_name"], version, artifact, metrics_doc, {"model_card.md": card})

    decision = "kept current production"
    current = registry.production(cfg["model_name"])
    if not gate_result["passed"]:
        decision = "gate failed; not promoted"
    elif promote:
        if current is None or current == version:
            registry.promote(cfg["model_name"], version)
            decision = "promoted"
        else:
            _, cur_metrics, _ = registry.load(cfg["model_name"], current)
            if metrics_doc["headline"]["mae"] <= cur_metrics["headline"]["mae"] + cfg["promotion_tolerance_mae"]:
                registry.promote(cfg["model_name"], version)
                decision = f"promoted over {current}"
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "model_card_regionalklasse.md").write_text(card)
    print(json.dumps({"version": version, "decision": decision, "headline": metrics_doc["headline"],
                      "gate": gate_result["checks"]}, indent=2))
    return {"version": version, "decision": decision, "gate": gate_result}


def model_card(cfg, report, version) -> str:
    lines = [f"# Model card: Regionalklasse predictor ({version})", "",
             cfg["description"], "",
             "## Data", "",
             "- 400 German districts (Destatis 2024 boundaries). Districts without a single GDV class are excluded.",
             "- Features: Unfallatlas accidents with personal injury 2020-2025 (Destatis), KBA vehicle stock 1 Jan 2025, Destatis population 2024.",
             "- Target: GDV Regionalklassen 2027. GDV sets classes from insurers' claims experience, which includes property-damage-only claims that the Unfallatlas does not record.",
             "- Trier (07211) and Trier-Saarburg (07235) have no fleet features because KBA reports them as one figure.", "",
             "## Validation", "",
             "Spatial cross-validation: GroupKFold over the 16 Bundeslaender (8 folds). Random 5-fold is shown only to measure leakage.", ""]
    for target, t in report["targets"].items():
        s = t["scores"]
        lines += [f"### {t['label']} ({target}, n={t['n']})", "",
                  "| model | spatial MAE | spatial within ±1 | random MAE | spearman (spatial) |",
                  "|---|---|---|---|---|"]
        for m in s["spatial"]:
            sp, rd = s["spatial"][m], s["random"][m]
            lines.append(f"| {m} | {sp['mae']:.2f} | {sp['within_one_class']:.0%} | {rd['mae']:.2f} | {sp['spearman']:.2f} |")
        if "persistence_2026" in s:
            p = s["persistence_2026"]
            lines.append(f"| last year's class (2026) | {p['mae']:.2f} | {p['within_one_class']:.0%} | - | {p['spearman']:.2f} |")
        top = ", ".join(i["feature"] for i in t["importance"][:5])
        lines += ["", f"Best model: **{s['best_model']}**. Top drivers (held-out permutation importance): {top}.",
                  f"Gate: {'passed' if s['gate']['passed'] else 'failed'}.", ""]
    lines += ["## Intended use and limits", "",
              "- Explains which public factors line up with GDV classes and flags districts whose class is higher or lower than public data suggests.",
              "- Not a pricing model. It does not use insurer claims data, and residuals are hypotheses for an actuary to check, not evidence of mispricing.",
              "- The 2026 class predicts the 2027 class almost perfectly; the model is built without it on purpose, to learn drivers rather than persistence."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-promote", action="store_true")
    args = ap.parse_args()
    result = train(promote=not args.no_promote)
    if not result["gate"]["passed"]:
        raise SystemExit("quality gate failed")
