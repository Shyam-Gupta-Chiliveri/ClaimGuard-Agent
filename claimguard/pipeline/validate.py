"""Data contract checks on the marts (and on the raw long CSV when it is present).

Run in CI before training. Exits non-zero on the first failed contract.
Usage: python -m pipeline.validate
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from core.paths import GEO, MARTS, ROOT

RAW = ROOT.parent / "motor_insurance_risk_raw.csv"
RAW_HEADER = ["source_dataset", "source_file", "geo_level", "geo_code", "geo_name", "state_or_region", "year",
              "period", "measure", "breakdown", "value", "unit", "source_note"]


def checks() -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        out.append((name, bool(ok), detail))

    d = pd.read_csv(MARTS / "districts.csv", dtype={"geo_code": str})
    check("400 districts", len(d) == 400, str(len(d)))
    check("district codes unique and 5 digits", d.geo_code.is_unique and d.geo_code.str.fullmatch(r"\d{5}").all())
    check("16 Bundeslaender", d.bundesland.nunique() == 16, str(d.bundesland.nunique()))
    pop = d.population_2024.sum()
    check("population 2024 between 83.0 and 84.0 million", 83.0e6 < pop < 84.0e6, f"{pop:,.0f}")
    for col, hi in (("liability_class_2027", 12), ("comprehensive_class_2027", 9), ("partial_cover_class_2027", 16)):
        s = d[col].dropna()
        check(f"{col} within 1..{hi}", s.between(1, hi).all() and len(s) >= 390, f"n={len(s)}")
    shares = [c for c in d.columns if c.startswith("share_")]
    bad = [c for c in shares if not d[c].dropna().between(0, 1).all()]
    check("all share_* columns within [0, 1]", not bad, ",".join(bad))
    check("Trier and Trier-Saarburg have no fleet features",
          d.loc[d.geo_code.isin(["07211", "07235"]), "share_bev"].isna().all())
    check("accidents never negative", (d.filter(like="accidents_20").fillna(0) >= 0).all().all())

    c = pd.read_csv(MARTS / "claims_inbox.csv", dtype={"geo_code": str})
    check("every claim is labelled SIMULATED", c.simulation_label.str.startswith("SIMULATED").all())
    check("claim districts exist", c.geo_code.isin(d.geo_code).all())

    geo = json.loads((GEO / "districts.geojson").read_text())
    codes = {f["properties"]["code"] for f in geo["features"]}
    check("map codes equal district codes", codes == set(d.geo_code))

    e = pd.read_csv(MARTS / "europe.csv")
    ratio = e.nonlife_claims_ratio.dropna()
    check("EIOPA non-life claims ratio plausible (0..2)", ratio.between(0, 2).all())

    if RAW.exists():
        with RAW.open("rb") as fh:
            head = fh.readline()
        check("raw CSV starts with UTF-8 BOM", head.startswith(b"\xef\xbb\xbf"))
        check("raw CSV has the 13-column header", head.decode("utf-8-sig").strip().split(",") == RAW_HEADER)
        with RAW.open("rb") as fh:
            fh.seek(-1, 2)
            check("raw CSV ends with a newline (append-safe)", fh.read(1) == b"\n")
    return out


def main() -> int:
    results = checks()
    width = max(len(n) for n, *_ in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
