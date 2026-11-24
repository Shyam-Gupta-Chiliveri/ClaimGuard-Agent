"""File-based model registry: models/registry/<model>/<version>/ plus registry.json.

Versions are content hashes of training data and config, so the same inputs always
produce the same version id (reproducible in CI). Stages: candidate, production, archived.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

from core.paths import REGISTRY

INDEX = REGISTRY / "registry.json"


def content_hash(*parts: bytes) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.hexdigest()[:12]


def _load() -> dict[str, Any]:
    if INDEX.exists():
        return json.loads(INDEX.read_text())
    return {"models": {}}


def _save(index: dict[str, Any]) -> None:
    REGISTRY.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(index, indent=2))


def register(model_name: str, version: str, artifact: Any, metrics: dict, extra_files: dict[str, str]) -> Path:
    folder = REGISTRY / model_name / version
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, folder / "model.joblib")
    (folder / "metrics.json").write_text(json.dumps(metrics, indent=2))
    for name, text in extra_files.items():
        (folder / name).write_text(text)
    index = _load()
    entry = index["models"].setdefault(model_name, {"production": None, "versions": {}})
    previous = entry["versions"].get(version, {})
    entry["versions"][version] = {
        "created": previous.get("created", datetime.now(UTC).isoformat(timespec="seconds")),
        "stage": previous.get("stage", "candidate"),
        "headline": metrics.get("headline", {}),
        "gate_passed": metrics.get("gate", {}).get("passed"),
    }
    _save(index)
    return folder


def production(model_name: str) -> str | None:
    return _load()["models"].get(model_name, {}).get("production")


def promote(model_name: str, version: str) -> None:
    index = _load()
    entry = index["models"][model_name]
    current = entry.get("production")
    if current and current != version and current in entry["versions"]:
        entry["versions"][current]["stage"] = "archived"
    entry["versions"][version]["stage"] = "production"
    entry["production"] = version
    _save(index)


def load(model_name: str, version: str | None = None) -> tuple[Any, dict, Path]:
    version = version or production(model_name)
    if version is None:
        raise FileNotFoundError(f"no production version of {model_name}; run `make train`")
    folder = REGISTRY / model_name / version
    return joblib.load(folder / "model.joblib"), json.loads((folder / "metrics.json").read_text()), folder


def listing() -> dict[str, Any]:
    return _load()
