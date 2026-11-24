"""One row per published figure, so every column on every row is filled.

Germany and Europe are not forced into the same wide columns. A blank in the
old file was usually another table's column. Here a figure that the source
does not publish is simply absent, which is different from an empty cell.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path

import pandas as pd

import build_raw_dataset as raw

OUT = raw.ROOT / "motor_insurance_risk_raw.csv"

FZ11_MEASURES = {
    4: "motorcycles",
    9: "passenger_cars",
    10: "passenger_cars_engine_to_1399cc",
    11: "passenger_cars_engine_1400_to_1999cc",
    12: "passenger_cars_engine_2000cc_or_more",
    21: "buses",
    22: "trucks",
    31: "tractors",
    33: "agricultural_tractors",
    36: "commercial_vehicles",
    37: "motor_vehicles",
    39: "trailers",
}

SEVERITY = {
    "1": "persons_killed",
    "2": "seriously_injured",
    "3": "slightly_injured",
}
WEEKDAY = {
    "1": "sunday",
    "2": "monday",
    "3": "tuesday",
    "4": "wednesday",
    "5": "thursday",
    "6": "friday",
    "7": "saturday",
}
LIGHT = {"0": "daylight", "1": "twilight", "2": "darkness"}
SURFACE = {"0": "dry", "1": "wet_or_damp", "2": "winter_slippery"}
KIND = {
    "0": "other_kind",
    "1": "collision_with_vehicle_starting_stopping_or_stationary",
    "2": "collision_with_vehicle_ahead",
    "3": "collision_with_vehicle_moving_laterally",
    "4": "collision_with_oncoming_vehicle",
    "5": "collision_while_turning_or_crossing",
    "6": "collision_with_pedestrian",
    "7": "collision_with_obstacle",
    "8": "left_the_road_to_the_right",
    "9": "left_the_road_to_the_left",
}
ACCIDENT_TYPE = {
    "1": "driving_accident",
    "2": "turning_off",
    "3": "turning_into_or_crossing",
    "4": "crossing_the_road",
    "5": "involving_stationary_vehicle",
    "6": "vehicles_moving_along",
    "7": "other_accident_type",
}
MONTH = {
    "01": "january",
    "02": "february",
    "03": "march",
    "04": "april",
    "05": "may",
    "06": "june",
    "07": "july",
    "08": "august",
    "09": "september",
    "10": "october",
    "11": "november",
    "12": "december",
}

NOTE_ACCIDENT = (
    "Each row counts Unfallatlas accidents with personal injury. "
    "Berlin and Hamburg boroughs are summed to the city code. "
    "GPS coordinates and the internal accident id stay in the original zip."
)
NOTE_KBA = "KBA vehicle stock on 1 January of the year. There is no KBA file for 1 January 2024 in the source folder."
NOTE_POP = "Destatis districts at 31 December 2024, census 2022 base. State and region total rows are not included."
NOTE_GDV = (
    "GDV regional class. A higher class is a worse claims record. "
    "2026 is the published class minus the published change. "
    "A registration district that is only part of a Kreis keeps its own class."
)
NOTE_CARS = "Eurostat passenger cars per 1,000 inhabitants. The breakdown holds the Eurostat flag when one was published."
NOTE_DEATHS = "Eurostat road deaths, total roads, number of people."
NOTE_EIOPA = (
    "EIOPA premiums, claims and expenses as published. "
    "These are the whole life or non-life business, not motor insurance alone. "
    "Rows with no published value are section headers and are not included."
)


def slug(text: str) -> str:
    value = str(text).strip().lower()
    for old, new in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        value = value.replace(old, new)
    value = value.replace("\n", " ")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def row(
    source_dataset: str,
    source_file: str,
    geo_level: str,
    geo_code: str,
    geo_name: str,
    state_or_region: str,
    year: int,
    period: str,
    measure: str,
    breakdown: str,
    value: float,
    unit: str,
    source_note: str,
) -> dict:
    return {
        "source_dataset": source_dataset,
        "source_file": source_file,
        "geo_level": geo_level,
        "geo_code": str(geo_code),
        "geo_name": str(geo_name),
        "state_or_region": str(state_or_region),
        "year": int(year),
        "period": str(period),
        "measure": measure,
        "breakdown": breakdown,
        "value": value,
        "unit": unit,
        "source_note": source_note,
    }


def district_name_lookup(pop: pd.DataFrame, kba_names: dict[str, str]) -> dict[str, str]:
    names = dict(zip(pop["ags"], pop["official_name"]))
    for code, name in kba_names.items():
        names.setdefault(code, name)
    return names


def kba_stock_rows(names: dict[str, str]) -> list[dict]:
    records = []
    for year, filename in raw.KBA_FILES.items():
        path = raw.RAW / filename
        engine = "xlrd" if path.suffix == ".xls" else "openpyxl"
        sheet = "FZ1.1" if "FZ1.1" in pd.ExcelFile(path, engine=engine).sheet_names else "Kfz_u_Kfz_Anh"
        frame = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
        header = None
        for i in range(min(15, len(frame))):
            if frame.iloc[i].astype(str).str.contains("Kennziffer").any():
                header = i
                break
        land = None
        kept = 0
        for i in range(header + 1, len(frame)):
            land_cell = frame.iat[i, 1]
            if pd.notna(land_cell):
                text = re.sub(r"\s+", " ", str(land_cell)).strip().upper()
                if text and "INHALT" not in text and text != "LAND":
                    land = text
            code_cell = frame.iat[i, 3]
            if pd.isna(code_cell):
                continue
            text = re.sub(r"\s+", " ", str(code_cell)).strip()
            match = re.match(r"^(\d{5})\s+(.+)$", text)
            if not match:
                continue
            code, district = match.group(1), match.group(2).strip(" .")
            state = raw.LAND_NAME.get(land) or raw.STATE_BY_CODE.get(code[:2], land or "Germany")
            names.setdefault(code, district)
            for column, measure in FZ11_MEASURES.items():
                if column >= frame.shape[1]:
                    continue
                value = pd.to_numeric(frame.iat[i, column], errors="coerce")
                if pd.isna(value):
                    continue
                records.append(
                    row(
                        "kba_vehicle_stock",
                        filename,
                        "district",
                        code,
                        district,
                        state,
                        year,
                        f"01.01.{year}",
                        measure,
                        "all",
                        float(value),
                        "vehicles",
                        NOTE_KBA,
                    )
                )
                kept += 1
        print(f"KBA stock {year}: {kept:,} figures")
    return records


def fuel_sheet_name(path: Path, engine: str) -> str | None:
    sheets = pd.ExcelFile(path, engine=engine).sheet_names
    for candidate in ("FZ1.2", "Pkw"):
        if candidate in sheets:
            return candidate
    return None


def kba_fuel_rows() -> list[dict]:
    records = []
    for year, filename in raw.KBA_FILES.items():
        path = raw.RAW / filename
        engine = "xlrd" if path.suffix == ".xls" else "openpyxl"
        sheet = fuel_sheet_name(path, engine)
        if sheet is None:
            print(f"KBA fuel {year}: no sheet")
            continue
        frame = pd.read_excel(path, sheet_name=sheet, header=None, engine=engine)
        header = None
        for i in range(min(20, len(frame))):
            if frame.iloc[i].astype(str).str.contains("Benzin", case=False).any():
                header = i
                break
        if header is None:
            print(f"KBA fuel {year}: header not found")
            continue
        group = ""
        columns = []
        for j in range(4, frame.shape[1]):
            group_cell = frame.iat[header - 1, j] if header else None
            if pd.notna(group_cell) and str(group_cell).strip():
                group = str(group_cell)
            label = frame.iat[header, j]
            if pd.isna(label) or not str(label).strip():
                continue
            label_text = str(label).strip()
            if label_text.lower().startswith("insgesamt"):
                continue
            group_key = group.lower()
            if "diesel" in group_key:
                measure = "passenger_cars_diesel_by_euro_standard"
            elif "emission" in group_key:
                measure = "passenger_cars_by_euro_standard"
            else:
                measure = "passenger_cars_by_fuel"
            lowered = label_text.lower()
            if lowered.startswith("darunter"):
                measure += "_of_which"
            elif "schadstoff" in lowered:
                measure += "_subtotal"
            columns.append((j, measure, slug(label_text)))
        land = None
        kept = 0
        for i in range(header + 1, len(frame)):
            land_cell = frame.iat[i, 1]
            if pd.notna(land_cell):
                text = re.sub(r"\s+", " ", str(land_cell)).strip().upper()
                if text and "INHALT" not in text and text != "LAND":
                    land = text
            code_cell = frame.iat[i, 3]
            if pd.isna(code_cell):
                continue
            text = re.sub(r"\s+", " ", str(code_cell)).strip()
            match = re.match(r"^(\d{5})\s+(.+)$", text)
            if not match:
                continue
            code, district = match.group(1), match.group(2).strip(" .")
            state = raw.LAND_NAME.get(land) or raw.STATE_BY_CODE.get(code[:2], "Germany")
            for column, measure, breakdown in columns:
                value = pd.to_numeric(frame.iat[i, column], errors="coerce")
                if pd.isna(value):
                    continue
                records.append(
                    row(
                        "kba_passenger_car_detail",
                        filename,
                        "district",
                        code,
                        district,
                        state,
                        year,
                        f"01.01.{year}",
                        measure,
                        breakdown,
                        float(value),
                        "vehicles",
                        NOTE_KBA + " Fuel shares and Euro classes come from the passenger-car sheet.",
                    )
                )
                kept += 1
        print(f"KBA fuel {year}: {kept:,} figures from {sheet}")
    return records


def population_rows(pop: pd.DataFrame) -> list[dict]:
    measures = [
        ("population_total", "population_total", "persons"),
        ("population_male", "population_male", "persons"),
        ("population_female", "population_female", "persons"),
        ("area_km2", "area_km2", "square_kilometres"),
        ("population_per_km2", "population_per_km2", "persons_per_square_kilometre"),
    ]
    records = []
    for item in pop.itertuples(index=False):
        state = item.bundesland_destatis or raw.STATE_BY_CODE.get(item.ags[:2], "Germany")
        for measure, attribute, unit in measures:
            value = getattr(item, attribute)
            if pd.isna(value):
                continue
            records.append(
                row(
                    "destatis_population",
                    "04-kreise.xlsx",
                    "district",
                    item.ags,
                    item.official_name,
                    state,
                    2024,
                    "31.12.2024",
                    measure,
                    "all",
                    float(value),
                    unit,
                    NOTE_POP,
                )
            )
    print(f"Population figures: {len(records):,}")
    return records


def gdv_rows(gdv: pd.DataFrame, pop: pd.DataFrame) -> list[dict]:
    official = dict(zip(pop["ags"], pop["official_name"]))
    fields = [
        (2027, "liability_class", "liability_class_2027", "class"),
        (2026, "liability_class", "liability_class_2026", "class"),
        (2027, "liability_class_change_vs_2026", "liability_change_vs_2026", "class_change"),
        (2027, "comprehensive_class", "comprehensive_class_2027", "class"),
        (2026, "comprehensive_class", "comprehensive_class_2026", "class"),
        (2027, "comprehensive_class_change_vs_2026", "comprehensive_change_vs_2026", "class_change"),
        (2027, "partial_cover_class", "partial_cover_class_2027", "class"),
        (2026, "partial_cover_class", "partial_cover_class_2026", "class"),
        (2027, "partial_cover_class_change_vs_2026", "partial_cover_change_vs_2026", "class_change"),
    ]
    records = []
    for item in gdv.itertuples(index=False):
        code = item.ags if isinstance(item.ags, str) and item.ags else f"GDV:{item.gdv_name}"
        state = item.bundesland_gdv or "Germany"
        if item.gdv_link == "part_of_kreis" and item.related_district_name:
            breakdown = f"part_of:{item.related_district_name}"
        else:
            breakdown = "all"
        label = official.get(item.ags, item.gdv_name) if item.ags else item.gdv_name
        for year, measure, attribute, unit in fields:
            value = getattr(item, attribute)
            if pd.isna(value):
                continue
            records.append(
                row(
                    "gdv_regionalklassen",
                    "gdv_regionalklassen_2027.csv",
                    "registration_district",
                    code,
                    label,
                    state,
                    year,
                    str(year),
                    measure,
                    breakdown,
                    float(value),
                    unit,
                    NOTE_GDV,
                )
            )
    print(f"GDV figures: {len(records):,}")
    return records


def read_accidents(year: int) -> pd.DataFrame:
    path = raw.RAW / raw.ACCIDENT_ZIPS[year]
    with zipfile.ZipFile(path) as archive:
        name = [
            item
            for item in archive.namelist()
            if item.lower().endswith((".csv", ".txt")) and "schema" not in item.lower()
        ][0]
        payload = archive.read(name)
    frame = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            frame = pd.read_csv(BytesIO(payload), sep=";", dtype=str, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    frame.columns = [str(column).replace("\ufeff", "").strip() for column in frame.columns]
    frame["ags"] = (
        frame["ULAND"].str.strip().str.zfill(2)
        + frame["UREGBEZ"].str.strip().str.zfill(1)
        + frame["UKREIS"].str.strip().str.zfill(2)
    )
    frame = frame.loc[frame["ags"].str.fullmatch(r"\d{5}")].copy()
    city = frame["ags"].str.startswith("11") & frame["ags"].ne("11000")
    frame.loc[city, "ags"] = "11000"
    city = frame["ags"].str.startswith("02") & frame["ags"].ne("02000")
    frame.loc[city, "ags"] = "02000"
    return frame


def add_counts(records, counts, year, measure, breakdown, names) -> None:
    for code, value in counts.items():
        if pd.isna(value):
            continue
        records.append(
            row(
                "unfallatlas",
                raw.ACCIDENT_ZIPS[year],
                "district",
                code,
                names.get(code, f"District {code}"),
                raw.STATE_BY_CODE.get(str(code)[:2], "Germany"),
                year,
                str(year),
                measure,
                breakdown,
                float(value),
                "accidents",
                NOTE_ACCIDENT,
            )
        )


def accident_rows(names: dict[str, str]) -> list[dict]:
    records = []
    for year in sorted(raw.ACCIDENT_ZIPS):
        frame = read_accidents(year)
        print(f"Unfallatlas {year}: {len(frame):,} accidents")
        add_counts(records, frame.groupby("ags").size(), year, "accidents_total", "all", names)
        severity = frame.groupby(["ags", "UKATEGORIE"]).size()
        for (code, level), value in severity.items():
            label = SEVERITY.get(str(level).strip())
            if label:
                add_counts(records, pd.Series({code: value}), year, "accidents_by_severity", label, names)
        for column, measure, labels in (
            ("UMONAT", "accidents_by_month", MONTH),
            ("UWOCHENTAG", "accidents_by_weekday", WEEKDAY),
            ("ULICHTVERH", "accidents_by_light", LIGHT),
            ("UART", "accidents_by_kind", KIND),
            ("UTYP1", "accidents_by_type", ACCIDENT_TYPE),
        ):
            if column not in frame.columns:
                continue
            grouped = frame.groupby(["ags", column]).size()
            for (code, level), value in grouped.items():
                label = labels.get(str(level).strip().zfill(2) if column == "UMONAT" else str(level).strip())
                if column == "UMONAT":
                    label = MONTH.get(str(level).strip().zfill(2))
                if label:
                    add_counts(records, pd.Series({code: value}), year, measure, label, names)
        surface_column = next(
            (
                column
                for column in frame.columns
                if column.lower() in {"iststrasse", "iststrassenzustand", "ustrzustand", "strzustand"}
            ),
            None,
        )
        if surface_column:
            grouped = frame.groupby(["ags", surface_column]).size()
            for (code, level), value in grouped.items():
                label = SURFACE.get(str(level).strip())
                if label:
                    add_counts(
                        records,
                        pd.Series({code: value}),
                        year,
                        "accidents_by_road_surface",
                        label,
                        names,
                    )
        for column, label in (
            ("IstPKW", "passenger_car"),
            ("IstRad", "bicycle"),
            ("IstFuss", "pedestrian"),
            ("IstKrad", "motorcycle"),
            ("IstGkfz", "goods_vehicle"),
        ):
            other = "IstSonstige" if "IstSonstige" in frame.columns else "IstSonstig" if "IstSonstig" in frame.columns else None
            use = other if column == "IstGkfz" and column not in frame.columns else column
            if use not in frame.columns:
                continue
            involved = frame.loc[frame[use].str.strip().eq("1")]
            if len(involved):
                add_counts(records, involved.groupby("ags").size(), year, "accidents_involving", label, names)
        if "USTUNDE" in frame.columns:
            hour = frame["USTUNDE"].str.strip().str.zfill(2)
            grouped = frame.groupby(["ags", hour]).size()
            for (code, level), value in grouped.items():
                if re.fullmatch(r"\d{2}", str(level)):
                    add_counts(records, pd.Series({code: value}), year, "accidents_by_hour", f"hour_{level}", names)
    print(f"Accident figures: {len(records):,}")
    return records


def eurostat_rows() -> list[dict]:
    records = []
    cars = pd.read_csv(raw.RAW / "road_eqs_carhab$defaultview_linear.csv.gz")
    for item in cars.itertuples(index=False):
        if pd.isna(item.OBS_VALUE):
            continue
        flag = item.OBS_FLAG if isinstance(item.OBS_FLAG, str) and item.OBS_FLAG.strip() else ""
        breakdown = f"eurostat_flag:{flag}" if flag else "all"
        records.append(
            row(
                "eurostat_cars",
                "road_eqs_carhab.csv",
                "country",
                raw.ISO2.get(item.geo, item.geo),
                item.geo,
                item.geo,
                int(item.TIME_PERIOD),
                str(int(item.TIME_PERIOD)),
                "passenger_cars_per_1000_inhabitants",
                breakdown,
                float(item.OBS_VALUE),
                "cars_per_1000_inhabitants",
                NOTE_CARS,
            )
        )
    deaths = pd.read_csv(raw.RAW / "sdg_11_40_page_linear.csv.gz")
    for item in deaths.itertuples(index=False):
        if pd.isna(item.OBS_VALUE):
            continue
        records.append(
            row(
                "eurostat_road_deaths",
                "sdg_11_40.csv",
                "country",
                raw.ISO2.get(item.geo, item.geo),
                item.geo,
                item.geo,
                int(item.TIME_PERIOD),
                str(int(item.TIME_PERIOD)),
                "road_deaths",
                "roads:total",
                float(item.OBS_VALUE),
                "persons",
                NOTE_DEATHS,
            )
        )
    print(f"Eurostat figures: {len(records):,}")
    return records


def eiopa_unit(code: str) -> str:
    if str(code).startswith("Z"):
        return "ratio"
    return "eur_million"


def eiopa_rows() -> list[dict]:
    files = [
        ("SA_Premiums_Claims_Expenses.csv", "country", "Reporting country"),
        ("SQ_Premiums_Claims_Expenses.csv", "country", "Reporting country"),
        ("GA_Premiums_Claims_Expenses.csv", "region", "Region"),
        ("GQ_Premiums_Claims_Expenses.csv", "region", "Region"),
    ]
    records = []
    for filename, level, place_column in files:
        frame = pd.read_csv(raw.RAW / filename)
        frame = frame.loc[frame["Value"].notna()].copy()
        for record in frame.to_dict(orient="records"):
            place = str(record[place_column]).strip()
            if level == "country":
                geo_name = raw.country_name_from_eiopa(place)
                geo_code = raw.ISO2.get(geo_name, geo_name)
                region = geo_name
            else:
                geo_name = place
                geo_code = place
                region = place
            period_text = str(record["Reference period"]).strip()
            if period_text.startswith("Y"):
                year = int(period_text[1:5])
                period = str(year)
            else:
                year = int(period_text[:4])
                period = period_text.replace(" ", "-")
            business = str(record["Business type"]).strip()
            item_name = str(record["Item"]).strip()
            code = str(record["Item code"]).strip()
            records.append(
                row(
                    "eiopa_premiums_claims_expenses",
                    filename,
                    level,
                    geo_code,
                    geo_name,
                    region,
                    year,
                    period,
                    f"{business.lower()}__{slug(item_name)}__{code}",
                    "all",
                    float(record["Value"]),
                    eiopa_unit(code),
                    NOTE_EIOPA,
                )
            )
        print(f"EIOPA {filename}: {frame['Value'].notna().sum():,} figures")
    return records


def main() -> None:
    pop = raw.load_population()
    names = district_name_lookup(pop, {})
    kba = kba_stock_rows(names)
    fuel = kba_fuel_rows()
    population = population_rows(pop)
    gdv = raw.match_gdv_to_ags(raw.load_gdv(), raw.load_kba(), pop)
    classes = gdv_rows(gdv, pop)
    accidents = accident_rows(names)
    europe_stats = eurostat_rows()
    insurance = eiopa_rows()
    frame = pd.DataFrame(kba + fuel + population + classes + accidents + europe_stats + insurance)
    empty = frame.columns[frame.isna().any() | frame.astype(str).eq("").any()]
    if len(empty):
        raise SystemExit(f"Empty cells remain in {list(empty)}")
    frame = frame.sort_values(
        ["source_dataset", "state_or_region", "geo_name", "year", "measure", "breakdown"],
        kind="mergesort",
    )
    frame.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("WROTE", OUT)
    print("rows", len(frame), "cols", frame.shape[1])
    print(frame.groupby("source_dataset").size().to_string())
    print("MB", round(OUT.stat().st_size / 1e6, 1))


if __name__ == "__main__":
    main()
