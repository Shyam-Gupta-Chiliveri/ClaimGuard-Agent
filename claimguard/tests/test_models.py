import numpy as np
import pandas as pd
import pytest

from ml import registry
from ml.drift import psi


@pytest.fixture(scope="module")
def regional():
    return registry.load("regionalklasse")


def test_production_model_passed_gate(regional):
    _, metrics, _ = regional
    assert metrics["gate"]["passed"]


def test_spatial_cv_beats_baseline_for_every_target(regional):
    _, metrics, _ = regional
    for target, t in metrics["report"]["targets"].items():
        s = t["scores"]
        assert s["spatial"][s["best_model"]]["mae"] < s["spatial"]["baseline_median"]["mae"], target


def test_random_split_is_optimistic(regional):
    _, metrics, _ = regional
    s = metrics["report"]["targets"]["liability_class_2027"]["scores"]
    assert s["random"][s["best_model"]]["mae"] < s["spatial"][s["best_model"]]["mae"]


def test_predictions_in_class_range(regional):
    artifact, _, _ = regional
    d = pd.read_csv("data/marts/districts.csv", dtype={"geo_code": str})
    X = d[artifact["features"]].copy()
    X["area_km2"] = np.log10(X["area_km2"])
    pred = artifact["targets"]["liability_class_2027"]["model"].predict(X)
    assert np.all(pred > -1) and np.all(pred < 14)


def test_psi_zero_for_same_distribution():
    rng = np.random.default_rng(0)
    x = pd.Series(rng.normal(size=5000))
    q = x.quantile(np.linspace(0, 1, 11)).tolist()
    assert psi(q, x) < 0.01
    assert psi(q, x + 1.5) > 0.25


def test_anomaly_model_registered():
    artifact, metrics, _ = registry.load("claim_anomaly")
    assert set(artifact) >= {"model", "features", "scale", "threshold"}
    assert "SIMULATED" in metrics["note"]
