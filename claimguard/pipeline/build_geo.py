"""Simplified district and state GeoJSON from BKG VG250 (geo84, 1 Jan 2020 boundaries).

Eisenach (16056) is dissolved into Wartburgkreis (16063) to match the 400 districts of
the 2024 Destatis population table. Only land areas (GF = 4) are used.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

import pandas as pd
import shapefile
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
ZIP = Path(os.environ.get("VG250_ZIP", ROOT.parent / "Dataset" / "vg250_01-01.geo84.shape.ebenen.zip"))
BASE = "vg250_01-01.geo84.shape.ebenen/vg250_ebenen_0101/"
OUT = ROOT / "data" / "geo"
TOLERANCE = {"KRS": 0.004, "LAN": 0.006}


def read_layer(z: zipfile.ZipFile, layer: str):
    stem = BASE + f"VG250_{layer}"
    reader = shapefile.Reader(
        shp=io.BytesIO(z.read(stem + ".shp")),
        dbf=io.BytesIO(z.read(stem + ".dbf")),
        shx=io.BytesIO(z.read(stem + ".shx")),
        encoding="utf-8",
    )
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        if rec["GF"] == 4:
            yield rec, shape(sr.shape.__geo_interface__)


def rounded(geom, digits=4):
    def r(coords):
        if isinstance(coords[0], (float, int)):
            return [round(coords[0], digits), round(coords[1], digits)]
        return [r(c) for c in coords]
    g = mapping(geom)
    return {"type": g["type"], "coordinates": r(g["coordinates"])}


def build(layer: str, key: str, remap: dict[str, str] | None = None, names: dict[str, str] | None = None) -> dict:
    with zipfile.ZipFile(ZIP) as z:
        parts: dict[str, list] = {}
        labels: dict[str, str] = {}
        for rec, geom in read_layer(z, layer):
            code = rec[key]
            code = (remap or {}).get(code, code)
            parts.setdefault(code, []).append(geom)
            labels.setdefault(code, rec["GEN"])
    features = []
    for code, geoms in sorted(parts.items()):
        geom = unary_union(geoms).simplify(TOLERANCE[layer], preserve_topology=True)
        features.append({
            "type": "Feature",
            "properties": {"code": code, "name": (names or {}).get(code, labels[code])},
            "geometry": rounded(geom),
        })
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    districts = pd.read_csv(ROOT / "data" / "marts" / "districts.csv", dtype={"geo_code": str})
    names = dict(zip(districts.geo_code, districts.geo_name, strict=True))
    krs = build("KRS", "AGS", remap={"16056": "16063"}, names=names)
    codes = {f["properties"]["code"] for f in krs["features"]}
    missing = set(districts.geo_code) - codes
    extra = codes - set(districts.geo_code)
    if missing or extra:
        raise SystemExit(f"district codes do not match: missing {sorted(missing)}, extra {sorted(extra)}")
    lan = build("LAN", "SN_L")
    for name, fc in (("districts", krs), ("states", lan)):
        path = OUT / f"{name}.geojson"
        path.write_text(json.dumps(fc, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        print(f"{name}: {len(fc['features'])} features, {path.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
