"""Build one raw CSV for the motor-insurance project.

Sources stay as published. Blank cells mean the source has no value for
that place or year. Nothing is filled in, and no row is dropped because
a field is missing.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

ROOT = Path("/Users/shyam/Downloads/Insurance project")
RAW = ROOT / "Dataset"
OUT = ROOT / "motor_insurance_risk_raw.csv"
PDF_DIR = ROOT / "PDFs"

KBA_FILES = {
    2018: "fz1_2018_xls.xls",
    2019: "fz1_2019_xlsx.xlsx",
    2020: "fz1_2020_xlsx.xlsx",
    2021: "fz1_2021.xlsx",
    2022: "fz1_2022.xlsx",
    2023: "fz1_2023.xlsx",
    2025: "fz1_2025.xlsx",
    2026: "fz1_2026.xlsx",
}

ACCIDENT_ZIPS = {
    2016: "Unfallorte2016_EPSG25832_CSV.zip",
    2017: "Unfallorte2017_EPSG25832_CSV.zip",
    2018: "Unfallorte2018_EPSG25832_CSV.zip",
    2019: "Unfallorte2019_EPSG25832_CSV.zip",
    2020: "Unfallorte2020_EPSG25832_CSV.zip",
    2021: "Unfallorte2021_EPSG25832_CSV.zip",
    2022: "Unfallorte2022_EPSG25832_CSV.zip",
    2023: "Unfallorte2023_EPSG25832_CSV.zip",
    2024: "Unfallorte2024_EPSG25832_CSV.zip",
    2025: "Unfallorte2025_EPSG25832_CSV.zip",
}

LAND_NAME = {
    "BADEN-WUERTTEMBERG": "Baden-Württemberg",
    "BAYERN": "Bayern",
    "BERLIN": "Berlin",
    "BRANDENBURG": "Brandenburg",
    "BREMEN": "Bremen",
    "HAMBURG": "Hamburg",
    "HESSEN": "Hessen",
    "MECKLENBURG-VORPOMMERN": "Mecklenburg-Vorpommern",
    "NIEDERSACHSEN": "Niedersachsen",
    "NORDRHEIN-WESTFALEN": "Nordrhein-Westfalen",
    "RHEINLAND-PFALZ": "Rheinland-Pfalz",
    "SAARLAND": "Saarland",
    "SACHSEN": "Sachsen",
    "SACHSEN-ANHALT": "Sachsen-Anhalt",
    "SCHLESWIG-HOLSTEIN": "Schleswig-Holstein",
    "THUERINGEN": "Thüringen",
}

STATE_BY_CODE = {
    "01": "Schleswig-Holstein",
    "02": "Hamburg",
    "03": "Niedersachsen",
    "04": "Bremen",
    "05": "Nordrhein-Westfalen",
    "06": "Hessen",
    "07": "Rheinland-Pfalz",
    "08": "Baden-Württemberg",
    "09": "Bayern",
    "10": "Saarland",
    "11": "Berlin",
    "12": "Brandenburg",
    "13": "Mecklenburg-Vorpommern",
    "14": "Sachsen",
    "15": "Sachsen-Anhalt",
    "16": "Thüringen",
}

# Official ISO codes for country names as they appear in the Eurostat extract.
ISO2 = {
    "Austria": "AT",
    "Belgium": "BE",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Greece": "EL",
    "Hungary": "HU",
    "Iceland": "IS",
    "Ireland": "IE",
    "Italy": "IT",
    "Latvia": "LV",
    "Liechtenstein": "LI",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Netherlands": "NL",
    "Norway": "NO",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
    "Albania": "AL",
    "Bosnia and Herzegovina": "BA",
    "Kosovo": "XK",
    "Montenegro": "ME",
    "North Macedonia": "MK",
    "Serbia": "RS",
    "Switzerland": "CH",
    "Turkey": "TR",
    "Türkiye": "TR",
    "United Kingdom": "UK",
    "European Union - 27 countries (from 2020)": "EU27",
    "European Union - 28 countries (2013-2020)": "EU28",
}

EIOPA_ALIASES = {
    "CZECHIA": "Czechia",
    "CZECH REPUBLIC": "Czechia",
    "TURKEY": "Türkiye",
    "TÜRKIYE": "Türkiye",
    "REPUBLIC OF MOLDOVA": "Moldova",
    "MOLDOVA": "Moldova",
    "NORTH MACEDONIA": "North Macedonia",
    "UNITED KINGDOM": "United Kingdom",
}

DROP_TOKENS = {
    "stadt",
    "hansestadt",
    "landeshauptstadt",
    "kreisfreie",
    "freie",
    "und",
    "der",
    "des",
    "die",
    "landkreis",
    "kreis",
    "lk",
    "kr",
    "am",
    "an",
    "im",
    "in",
    "den",
    "dem",
    "von",
    "vom",
    "zu",
    "zur",
    "zum",
    "land",
}


def canon(raw: str) -> tuple[str, str]:
    original = str(raw).strip()
    s = (
        original.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
        .replace("Ä", "ae")
        .replace("Ö", "oe")
        .replace("Ü", "ue")
        .lower()
    )
    kind = "plain"
    if "(land)" in s or re.search(r",\s*land\b", s):
        kind = "land"
    elif (
        "(stadt)" in s
        or re.search(r",\s*stadt\b", s)
        or re.search(r"\bstadt\b", s)
        or s.endswith("stadt")
        or "hansestadt" in s
        or "landeshauptstadt" in s
        or "kreisfreie stadt" in s
    ):
        kind = "stadt"
    s = s.replace("/", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = []
    for token in s.split():
        if token.endswith("kreis") and len(token) > 5:
            token = token[:-5]
        if token in DROP_TOKENS or len(token) <= 1:
            continue
        if token:
            tokens.append(token)
    return " ".join(tokens), kind


def lookup_keys(raw: str) -> list[tuple[str, str]]:
    """Several name keys, strict one first."""
    key, kind = canon(raw)
    keys = [(key, kind)]
    if "/" in str(raw):
        left = str(raw).split("/", 1)[0]
        keys.append(canon(left))
    # "Weimarer Land" style already handled. Keep unique order.
    seen = set()
    out = []
    for item in keys:
        if item[0] and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def load_kba_year(year: int) -> pd.DataFrame:
    path = RAW / KBA_FILES[year]
    engine = "xlrd" if path.suffix == ".xls" else "openpyxl"
    xl = pd.ExcelFile(path, engine=engine)
    sheet = "FZ1.1" if "FZ1.1" in xl.sheet_names else "Kfz_u_Kfz_Anh"
    df = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
    header_row = None
    for i in range(min(15, len(df))):
        for j in range(min(6, df.shape[1])):
            cell = df.iat[i, j]
            if pd.notna(cell) and "Kennziffer" in str(cell):
                header_row = i
                break
        if header_row is not None:
            break
    if header_row is None:
        raise RuntimeError(f"No header in {path.name}")
    pkw_col = None
    for j in range(df.shape[1]):
        cell = df.iat[header_row - 1, j] if header_row else None
        if pd.notna(cell) and "Personenkraftwagen" in str(cell):
            pkw_col = j
            break
    if pkw_col is None:
        pkw_col = 9
    rows = []
    land = None
    for i in range(header_row + 1, len(df)):
        land_cell = df.iat[i, 1]
        if pd.notna(land_cell):
            text = re.sub(r"\s+", " ", str(land_cell)).strip().upper()
            if text and "INHALT" not in text and text not in {"LAND", "NAN"}:
                land = text
        code_cell = df.iat[i, 3]
        if pd.isna(code_cell):
            continue
        text = re.sub(r"\s+", " ", str(code_cell)).strip()
        match = re.match(r"^(\d{5})\s+(.+)$", text)
        if not match:
            continue
        code, name = match.group(1), match.group(2).strip(" .")
        if "ZUSAMMEN" in name.upper() or "INSGESAMT" in name.upper():
            continue
        pkw = pd.to_numeric(df.iat[i, pkw_col], errors="coerce")
        rows.append(
            {
                "ags": code,
                "kba_name": name,
                "kba_land_raw": land,
                "bundesland_kba": LAND_NAME.get(land, None),
                f"passenger_cars_{year}": pkw,
            }
        )
    out = pd.DataFrame(rows)
    if out["ags"].duplicated().any():
        dupes = out.loc[out["ags"].duplicated(keep=False), "ags"].unique()
        raise RuntimeError(f"Duplicate AGS in KBA {year}: {dupes[:10]}")
    return out


def load_kba() -> pd.DataFrame:
    frames = []
    for year in sorted(KBA_FILES):
        part = load_kba_year(year)
        print(f"KBA {year}: {len(part)} districts, cars sum {part[f'passenger_cars_{year}'].sum():,.0f}")
        frames.append(part)
    master = frames[-1][["ags", "kba_name", "kba_land_raw", "bundesland_kba"]].copy()
    # Keep a district that exists in an earlier file even if it is gone in 2026.
    for part in frames:
        extra = part.loc[~part["ags"].isin(master["ags"]), ["ags", "kba_name", "kba_land_raw", "bundesland_kba"]]
        master = pd.concat([master, extra], ignore_index=True)
    for part in frames:
        year_cols = [c for c in part.columns if c.startswith("passenger_cars_")]
        master = master.merge(part[["ags"] + year_cols], on="ags", how="left")
    return master


def load_population() -> pd.DataFrame:
    df = pd.read_excel(
        RAW / "04-kreise.xlsx",
        sheet_name="Kreisfreie Städte u. Landkreise",
        header=None,
        engine="openpyxl",
    )
    rows = []
    bundesland = None
    for i in range(len(df)):
        key = df.iat[i, 0]
        if pd.isna(key):
            continue
        key = str(key).strip()
        if not re.fullmatch(r"\d{1,5}", key):
            continue
        name = df.iat[i, 2]
        if pd.isna(name) or str(name).strip().lower() == "insgesamt":
            if len(key) == 2:
                label = df.iat[i, 1]
                bundesland = str(label).strip() if pd.notna(label) else bundesland
            continue
        if len(key) != 5:
            if len(key) == 2:
                label = df.iat[i, 1]
                bundesland = str(label).strip() if pd.notna(label) else bundesland
            continue
        rows.append(
            {
                "ags": key.zfill(5),
                "district_type": None if pd.isna(df.iat[i, 1]) else str(df.iat[i, 1]).strip(),
                "official_name": str(name).strip(),
                "nuts3": None if pd.isna(df.iat[i, 3]) else str(df.iat[i, 3]).strip(),
                "area_km2": pd.to_numeric(df.iat[i, 4], errors="coerce"),
                "population_total": pd.to_numeric(df.iat[i, 5], errors="coerce"),
                "population_male": pd.to_numeric(df.iat[i, 6], errors="coerce"),
                "population_female": pd.to_numeric(df.iat[i, 7], errors="coerce"),
                "population_per_km2": pd.to_numeric(df.iat[i, 8], errors="coerce"),
                "bundesland_destatis": bundesland,
            }
        )
    out = pd.DataFrame(rows)
    print(f"Destatis districts: {len(out)}, population sum {out['population_total'].sum():,.0f}")
    return out


def load_gdv() -> pd.DataFrame:
    gdv = pd.read_csv(RAW / "gdv_regionalklassen_2027.csv")
    gdv = gdv.rename(
        columns={
            "zulassungsbezirk": "gdv_name",
            "bundesland": "bundesland_gdv",
            "hp_2027": "liability_class_2027",
            "hp_change": "liability_change_vs_2026",
            "hp_2026": "liability_class_2026",
            "vk_2027": "comprehensive_class_2027",
            "vk_change": "comprehensive_change_vs_2026",
            "vk_2026": "comprehensive_class_2026",
            "tk_2027": "partial_cover_class_2027",
            "tk_change": "partial_cover_change_vs_2026",
            "tk_2026": "partial_cover_class_2026",
        }
    )
    print(f"GDV districts: {len(gdv)}")
    inconsistent = []
    for label, now, change, prev in [
        ("liability", "liability_class_2027", "liability_change_vs_2026", "liability_class_2026"),
        ("comprehensive", "comprehensive_class_2027", "comprehensive_change_vs_2026", "comprehensive_class_2026"),
        ("partial", "partial_cover_class_2027", "partial_cover_change_vs_2026", "partial_cover_class_2026"),
    ]:
        expected = gdv[now] - gdv[change]
        bad = gdv.loc[expected != gdv[prev], "gdv_name"]
        if len(bad):
            inconsistent.append((label, bad.tolist()[:8]))
    print("GDV 2026 formula mismatches:", inconsistent or "none")
    return gdv


# GDV name -> district key, only where the registration district is the same
# place as today's Kreis or kreisfreie Stadt. A registration district that
# is only part of a Kreis is not given that Kreis's population or accidents.
MANUAL_AGS = {
    "Aachen": "05334",
    "Bitburg-Prüm": "07232",
    "Daun": "07233",
    "Dillingen/Donau": "09773",
    "Freiburg/Breisgau": "08311",
    "Hagen/Westfalen": "05914",
    "Heppenheim/Bergstraße": "06431",
    "Landau/Pfalz": "07313",
    "Leipziger Land": "14729",
    "Neustadt/Aisch-Bad Windsheim": "09575",
    "Neustadt/Waldnaab": "09374",
    "Offenbach (Stadt)": "06413",
    "Saarbrücken": "10041",
    "Siegen": "05970",
    "Unstrut-Hainichen-Kreis": "16064",
    "Weimar (Land)": "16071",
    "Wesermarsch in Brake": "03461",
    "Zollern/Albkreis": "08417",
}

# These GDV districts sit inside a larger Kreis. The class stays on its own
# row. Population, cars and accidents of the Kreis are not copied across.
RELATED_DISTRICT = {
    "Moosburg": "09178",
    "Wetzlar": "06532",
    "Greifswald": "13075",
    "Neubrandenburg": "13071",
    "Stralsund": "13073",
    "Wismar": "13074",
    "Göttingen (Stadt)": "03159",
    "Göttingen (Land)": "03159",
    "Hannover (Stadt)": "03241",
    "Hannover (Land)": "03241",
    "Bad Kreuznach (Stadt)": "07133",
    "Bad Kreuznach (Land)": "07133",
    "Idar-Oberstein": "07134",
    "Neuwied (Stadt)": "07138",
    "Neuwied (Land)": "07138",
    "Sankt Ingbert": "10045",
    "Völklingen": "10041",
}


def match_gdv_to_ags(gdv: pd.DataFrame, kba: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    index: dict[tuple[str, str], list[str]] = {}

    def add(key: str, kind: str, ags: str) -> None:
        if not key:
            return
        for item in ((key, kind), (key.replace(" ", ""), kind)):
            index.setdefault(item, [])
            if ags not in index[item]:
                index[item].append(ags)

    for row in kba.itertuples(index=False):
        key, kind = canon(row.kba_name)
        add(key, kind, row.ags)
    for row in pop.itertuples(index=False):
        key, _kind = canon(row.official_name)
        district_type = "" if pd.isna(row.district_type) else str(row.district_type)
        kind = "stadt" if "Stadt" in district_type else "plain"
        add(key, kind, row.ags)

    def pick(name: str) -> tuple[str, str]:
        for key, kind in lookup_keys(name):
            compact = key.replace(" ", "")
            want_order = [kind]
            if kind == "plain":
                want_order.append("stadt")
            elif kind == "land":
                want_order.append("plain")
            elif kind == "stadt":
                want_order.append("plain")
            found = []
            for want in want_order:
                bucket = []
                for item in ((key, want), (compact, want)):
                    bucket.extend(index.get(item, []))
                bucket = list(dict.fromkeys(bucket))
                if len(bucket) == 1:
                    return bucket[0], "name"
                if len(bucket) > 1:
                    found = bucket
                    break
            if found:
                return "", "ambiguous"
        # One longer official name, for example Lindau -> Lindau (Bodensee).
        # Compact keys are ignored here so "lindau" cannot stick to an unrelated word.
        hits = []
        allowed = set(want_order)
        for (ikey, ikind), ags_list in index.items():
            if ikind not in allowed or " " not in ikey:
                continue
            if ikey == key or ikey.startswith(key + " "):
                hits.extend(ags_list)
        hits = list(dict.fromkeys(hits))
        if len(hits) == 1:
            return hits[0], "name"
        return "", "unmatched"

    official_names = dict(zip(pop["ags"], pop["official_name"]))
    matched = []
    known = set(kba["ags"]).union(set(pop["ags"]))
    for row in gdv.itertuples(index=False):
        if row.gdv_name in MANUAL_AGS:
            ags = MANUAL_AGS[row.gdv_name]
            how = "manual_name"
            if ags not in known:
                ags, how = "", "unmatched"
        elif row.gdv_name in RELATED_DISTRICT:
            # Do not attach a part-district class to the whole Kreis.
            ags, how = "", "part_of_kreis"
        else:
            ags, how = pick(row.gdv_name)
        related = "" if ags else RELATED_DISTRICT.get(row.gdv_name, "")
        matched.append(
            {
                "gdv_name": row.gdv_name,
                "ags": ags,
                "gdv_link": how,
                "related_district_ags": related,
                "related_district_name": official_names.get(related, ""),
            }
        )
    link = pd.DataFrame(matched)
    print("GDV link counts:\n", link["gdv_link"].value_counts(dropna=False).to_string())
    print("NOT AUTOMATIC:")
    show = link.loc[link["gdv_link"] != "name", ["gdv_name", "gdv_link", "ags", "related_district_name"]]
    print(show.to_string(index=False))
    used = link.loc[link["ags"] != "", "ags"]
    dupes = set(used[used.duplicated(keep=False)])
    if dupes:
        print("DUPLICATE AGS ASSIGNMENTS:")
        print(link.loc[link["ags"].isin(dupes), ["gdv_name", "ags", "gdv_link"]].to_string(index=False))
        conflict = link["ags"].isin(dupes)
        link.loc[conflict, "ags"] = ""
        link.loc[conflict, "gdv_link"] = "ambiguous"
    return gdv.merge(link, on="gdv_name", how="left")


def read_accidents(year: int) -> pd.DataFrame:
    path = RAW / ACCIDENT_ZIPS[year]
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.lower().endswith((".csv", ".txt")) and "schema" not in name.lower()
        ]
        raw = archive.read(names[0])
    last_error = None
    frame = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            frame = pd.read_csv(BytesIO(raw), sep=";", dtype=str, encoding=encoding)
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    if frame is None:
        raise RuntimeError(f"Cannot read {path.name}: {last_error}")
    frame.columns = [str(col).replace("\ufeff", "").strip() for col in frame.columns]
    for col in ("ULAND", "UREGBEZ", "UKREIS", "UKATEGORIE", "IstPKW"):
        if col not in frame.columns:
            raise RuntimeError(f"{path.name} missing {col}; columns={list(frame.columns)[:12]}")
    frame["ags"] = (
        frame["ULAND"].str.strip().str.zfill(2)
        + frame["UREGBEZ"].str.strip().str.zfill(1)
        + frame["UKREIS"].str.strip().str.zfill(2)
    )
    frame = frame.loc[frame["ags"].str.fullmatch(r"\d{5}")].copy()
    # Unfallatlas publishes Berlin and Hamburg by borough, not as one district.
    # The borough codes are added up to the city code used by GDV, KBA and Destatis.
    frame.loc[frame["ags"].str.startswith("11") & frame["ags"].ne("11000"), "ags"] = "11000"
    frame.loc[frame["ags"].str.startswith("02") & frame["ags"].ne("02000"), "ags"] = "02000"
    frame["severity"] = frame["UKATEGORIE"].str.strip()
    frame["with_car"] = frame["IstPKW"].str.strip().eq("1")
    return frame


def load_accidents() -> tuple[pd.DataFrame, dict[int, set[str]]]:
    pieces = []
    states_by_year = {}
    for year in sorted(ACCIDENT_ZIPS):
        frame = read_accidents(year)
        states = set(frame["ags"].str[:2])
        states_by_year[year] = states
        grouped = frame.groupby("ags", as_index=False).agg(
            total=("ags", "size"),
            fatal=("severity", lambda s: int((s == "1").sum())),
            serious=("severity", lambda s: int((s == "2").sum())),
            slight=("severity", lambda s: int((s == "3").sum())),
            with_car=("with_car", "sum"),
        )
        grouped = grouped.rename(
            columns={
                "total": f"accidents_{year}_total",
                "fatal": f"accidents_{year}_fatal",
                "serious": f"accidents_{year}_serious",
                "slight": f"accidents_{year}_slight",
                "with_car": f"accidents_{year}_with_passenger_car",
            }
        )
        print(
            f"Unfallatlas {year}: {int(grouped[f'accidents_{year}_total'].sum()):,} accidents, "
            f"states {sorted(states)}"
        )
        pieces.append(grouped)
    accidents = pieces[0]
    for part in pieces[1:]:
        accidents = accidents.merge(part, on="ags", how="outer")
    return accidents, states_by_year


def country_name_from_eiopa(name: str) -> str:
    key = str(name).strip().upper()
    if key in EIOPA_ALIASES:
        return EIOPA_ALIASES[key]
    return str(name).strip().title()


def load_eu() -> pd.DataFrame:
    cars = pd.read_csv(RAW / "road_eqs_carhab$defaultview_linear.csv.gz")
    cars = cars.rename(
        columns={
            "geo": "country",
            "TIME_PERIOD": "year",
            "OBS_VALUE": "cars_per_1000_inhabitants",
            "OBS_FLAG": "cars_per_1000_flag",
        }
    )
    cars = cars[["country", "year", "cars_per_1000_inhabitants", "cars_per_1000_flag"]]

    deaths = pd.read_csv(RAW / "sdg_11_40_page_linear.csv.gz")
    deaths = deaths.rename(
        columns={"geo": "country", "TIME_PERIOD": "year", "OBS_VALUE": "road_deaths"}
    )
    deaths = deaths[["country", "year", "road_deaths"]]

    eiopa = pd.read_csv(RAW / "SA_Premiums_Claims_Expenses.csv")
    eiopa["country"] = eiopa["Reporting country"].map(country_name_from_eiopa)
    eiopa["year"] = eiopa["Reference period"].astype(str).str.replace("Y", "", regex=False).astype(int)
    wanted = eiopa["Item code"].isin(["R0110", "R0210", "R0310", "Z0001"])
    eiopa = eiopa.loc[wanted, ["country", "year", "Business type", "Item code", "Value"]]
    eiopa["column"] = eiopa["Business type"].str.lower().str.replace("-", "", regex=False) + "_" + eiopa["Item code"]
    pivot = (
        eiopa.pivot_table(
            index=["country", "year"],
            columns="column",
            values="Value",
            aggfunc="first",
        )
        .reset_index()
    )
    rename = {
        "nonlife_R0110": "nonlife_premiums_written_gross_direct_eur_m",
        "nonlife_R0210": "nonlife_premiums_earned_gross_direct_eur_m",
        "nonlife_R0310": "nonlife_claims_incurred_gross_direct_eur_m",
        "nonlife_Z0001": "nonlife_net_combined_ratio",
        "life_R0110": "life_premiums_written_gross_direct_eur_m",
        "life_R0210": "life_premiums_earned_gross_direct_eur_m",
        "life_R0310": "life_claims_incurred_gross_direct_eur_m",
        "life_Z0001": "life_net_combined_ratio",
    }
    pivot = pivot.rename(columns=rename)

    eu = cars.merge(deaths, on=["country", "year"], how="outer")
    eu = eu.merge(pivot, on=["country", "year"], how="outer")
    eu["year"] = eu["year"].astype(int)
    print(f"EU country-year rows: {len(eu)}, countries {eu['country'].nunique()}")
    return eu


def blank_if_state_missing(row: pd.Series, year: int, states_by_year: dict[int, set[str]], column: str, kreis_ags: set[str]):
    ags = row["ags"]
    if not isinstance(ags, str) or len(ags) != 5:
        return pd.NA
    value = row[column]
    if pd.notna(value):
        return value
    # A blank stays blank when that federal state was not in the file,
    # and also when this code is not a Kreis (accidents are published by Kreis).
    if ags[:2] not in states_by_year[year] or ags not in kreis_ags:
        return pd.NA
    return 0


def build_districts(kba, pop, gdv, accidents, states_by_year) -> pd.DataFrame:
    districts = kba.merge(pop, on="ags", how="outer")
    gdv_matched = gdv.loc[gdv["ags"].fillna("") != ""].copy()
    gdv_unmatched = gdv.loc[gdv["ags"].fillna("") == ""].drop(columns=["ags"])
    districts = districts.merge(gdv_matched, on="ags", how="left")
    districts = districts.merge(accidents, on="ags", how="outer")
    kreis_ags = set(pop["ags"])

    for year in ACCIDENT_ZIPS:
        for suffix in ("total", "fatal", "serious", "slight", "with_passenger_car"):
            column = f"accidents_{year}_{suffix}"
            if column not in districts.columns:
                districts[column] = pd.NA
            districts[column] = districts.apply(
                lambda row, y=year, c=column: blank_if_state_missing(row, y, states_by_year, c, kreis_ags),
                axis=1,
            )

    # GDV rows that did not match a district code stay in the file, with the other fields blank.
    if len(gdv_unmatched):
        gdv_unmatched = gdv_unmatched.copy()
        gdv_unmatched["ags"] = pd.NA
        districts = pd.concat([districts, gdv_unmatched], ignore_index=True)

    districts["record_level"] = "district"
    districts["country"] = "Germany"
    districts["geo_code"] = districts["ags"]
    districts["bundesland"] = districts["bundesland_destatis"].combine_first(
        districts["bundesland_gdv"]
    ).combine_first(districts["bundesland_kba"])
    missing_state = districts["bundesland"].isna() & districts["ags"].notna()
    districts.loc[missing_state, "bundesland"] = districts.loc[missing_state, "ags"].str[:2].map(STATE_BY_CODE)
    districts["geo_name"] = districts["official_name"].combine_first(districts["gdv_name"]).combine_first(
        districts["kba_name"]
    )
    districts["joined_gdv"] = districts["gdv_name"].notna().map({True: "yes", False: "no"})
    districts["joined_population"] = districts["population_total"].notna().map({True: "yes", False: "no"})
    districts["joined_kba_2026"] = districts["passenger_cars_2026"].notna().map({True: "yes", False: "no"})
    districts["source_note"] = pd.NA
    berlin = districts["ags"] == "11000"
    districts.loc[berlin, "source_note"] = (
        "Unfallatlas records Berlin by borough (11001 to 11012). The accident counts on this row are the sum of those boroughs. "
        "They are not estimated."
    )
    hamburg = districts["ags"] == "02000"
    districts.loc[hamburg, "source_note"] = (
        "Unfallatlas records Hamburg by borough. The accident counts on this row are the sum of those boroughs. "
        "They are not estimated."
    )
    trier = districts["ags"] == "07211"
    districts.loc[trier, "source_note"] = (
        "KBA prints code 07211 with the label TRIER-SAARBURG. Destatis uses 07211 for the city of Trier "
        "and 07235 for Trier-Saarburg. The car count stays on the code KBA printed and is not copied to 07235."
    )
    eisenach = districts["ags"] == "16056"
    districts.loc[eisenach, "source_note"] = (
        "Eisenach merged into the Wartburgkreis in 2021. The row is kept because older vehicle and accident "
        "files still use code 16056. Destatis does not list Eisenach separately at 31.12.2024, so population is blank."
    )
    split = districts["related_district_ags"].fillna("").ne("")
    districts.loc[split, "source_note"] = (
        "This GDV registration district is only part of the Kreis in related_district_ags. "
        "Population, cars and accidents of that Kreis are not copied onto this row."
    )
    return districts


def build_eu_rows(eu: pd.DataFrame) -> pd.DataFrame:
    eu = eu.copy()
    eu["record_level"] = "eu_country_year"
    eu["geo_name"] = eu["country"]
    eu["geo_code"] = eu["country"].map(ISO2)
    eu["bundesland"] = pd.NA
    eu["source_note"] = (
        "Eurostat cars are passenger cars per 1,000 inhabitants. Road deaths are the Eurostat total. "
        "EIOPA premiums and claims are the whole non-life or life business, not motor insurance alone."
    )
    return eu


def column_order(frame: pd.DataFrame) -> list[str]:
    id_cols = [
        "record_level",
        "country",
        "year",
        "geo_code",
        "geo_name",
        "bundesland",
        "district_type",
        "nuts3",
        "official_name",
        "kba_name",
        "gdv_name",
        "gdv_link",
        "related_district_ags",
        "related_district_name",
        "source_note",
        "joined_gdv",
        "joined_population",
        "joined_kba_2026",
        "area_km2",
        "population_total",
        "population_male",
        "population_female",
        "population_per_km2",
        "liability_class_2027",
        "liability_change_vs_2026",
        "liability_class_2026",
        "comprehensive_class_2027",
        "comprehensive_change_vs_2026",
        "comprehensive_class_2026",
        "partial_cover_class_2027",
        "partial_cover_change_vs_2026",
        "partial_cover_class_2026",
    ]
    car_cols = [f"passenger_cars_{year}" for year in (2018, 2019, 2020, 2021, 2022, 2023, 2025, 2026)]
    accident_cols = []
    for year in range(2016, 2026):
        for suffix in ("total", "fatal", "serious", "slight", "with_passenger_car"):
            accident_cols.append(f"accidents_{year}_{suffix}")
    eu_cols = [
        "cars_per_1000_inhabitants",
        "cars_per_1000_flag",
        "road_deaths",
        "nonlife_premiums_written_gross_direct_eur_m",
        "nonlife_premiums_earned_gross_direct_eur_m",
        "nonlife_claims_incurred_gross_direct_eur_m",
        "nonlife_net_combined_ratio",
        "life_premiums_written_gross_direct_eur_m",
        "life_premiums_earned_gross_direct_eur_m",
        "life_claims_incurred_gross_direct_eur_m",
        "life_net_combined_ratio",
    ]
    ordered = []
    for col in id_cols + car_cols + accident_cols + eu_cols:
        if col in frame.columns and col not in ordered:
            ordered.append(col)
    return ordered


def copy_pdfs() -> None:
    PDF_DIR.mkdir(exist_ok=True)
    mapping = {
        "European Insurance Overview 2026.pdf": "EIOPA_European_Insurance_Overview_2026.pdf",
        "DSB_Unfallatlas_EN.pdf": "Unfallatlas_metadata_EN.pdf",
        "DSB_Unfallatlas.pdf": "Unfallatlas_metadata_DE.pdf",
    }
    for source, target in mapping.items():
        shutil.copy2(RAW / source, PDF_DIR / target)
        print("PDF", target)


def main() -> None:
    kba = load_kba()
    pop = load_population()
    gdv = load_gdv()
    gdv = match_gdv_to_ags(gdv, kba, pop)
    accidents, states_by_year = load_accidents()
    districts = build_districts(kba, pop, gdv, accidents, states_by_year)
    eu = build_eu_rows(load_eu())
    combined = pd.concat([districts, eu], ignore_index=True, sort=False)
    combined = combined[column_order(combined)]
    combined = combined.sort_values(
        ["record_level", "bundesland", "geo_name", "country", "year"],
        kind="mergesort",
    )
    combined.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("WROTE", OUT, "rows", len(combined), "cols", combined.shape[1])
    copy_pdfs()


if __name__ == "__main__":
    main()
