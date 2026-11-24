"""Analysis tables and PDF copies. Does not rewrite motor_insurance_risk_raw.csv."""

import hashlib
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
from pypdf import PdfReader, PdfWriter

import build_raw_dataset as raw

ROOT = Path("/Users/shyam/Downloads/Insurance project")
RAW_CSV = ROOT / "motor_insurance_risk_raw.csv"
POP_CSV = ROOT / "Dataset" / "eurostat_demo_pjan_total.csv"
OUT = ROOT / "analysis"
PDF_OUT = ROOT / "PDFs"

PARTS = {
    "GDV:Moosburg": "09178",
    "GDV:Wetzlar": "06532",
    "GDV:Greifswald": "13075",
    "GDV:Neubrandenburg": "13071",
    "GDV:Stralsund": "13073",
    "GDV:Wismar": "13074",
    "GDV:Göttingen (Land)": "03159",
    "GDV:Göttingen (Stadt)": "03159",
    "GDV:Hannover (Land)": "03241",
    "GDV:Hannover (Stadt)": "03241",
    "GDV:Bad Kreuznach (Land)": "07133",
    "GDV:Bad Kreuznach (Stadt)": "07133",
    "GDV:Idar-Oberstein": "07134",
    "GDV:Neuwied (Land)": "07138",
    "GDV:Neuwied (Stadt)": "07138",
    "GDV:Sankt Ingbert": "10045",
    "GDV:Völklingen": "10041",
}

NO_SINGLE_CLASS = {"03159", "03241", "07133", "07138", "07235"}
BLANK_PAGES = {
    "fz1_2007_pdf.pdf": {1},
    "fz1_2012_pdf.pdf": {1},
    "fz1_2013_pdf.pdf": {1},
}


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classes_for(df: pd.DataFrame, code: str) -> dict:
    out = {}
    sub = df[(df.source_dataset == "gdv_regionalklassen") & (df.geo_code == code)]
    for measure in (
        "liability_class",
        "comprehensive_class",
        "partial_cover_class",
    ):
        for year in ("2026", "2027"):
            values = sub.loc[(sub.measure == measure) & (sub.year == year), "value"]
            out[f"{measure}_{year}"] = float(values.iloc[0]) if len(values) else None
    return out


def build_germany(df: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    cars = df[
        (df.source_dataset == "kba_vehicle_stock") & (df.measure == "passenger_cars")
    ].copy()
    cars["value"] = pd.to_numeric(cars["value"])
    cars_2025 = cars.loc[cars.year == "2025"].set_index("geo_code")["value"]
    cars_2026 = cars.loc[cars.year == "2026"].set_index("geo_code")["value"]

    accidents = df[
        (df.source_dataset == "unfallatlas")
        & (df.measure == "accidents_total")
        & (df.breakdown == "all")
        & (df.year.isin(["2020", "2021", "2022", "2023", "2024", "2025"]))
    ].copy()
    accidents["value"] = pd.to_numeric(accidents["value"])
    accident_wide = accidents.pivot_table(
        index="geo_code", columns="year", values="value", aggfunc="sum"
    )

    rows = []
    for district in districts.itertuples(index=False):
        code = district.ags
        gdv = classes_for(df, code)
        published_2026 = None if code == "07211" else cars_2026.get(code)
        published_2025 = None if code == "07211" else cars_2025.get(code)
        if pd.isna(published_2026):
            published_2026 = None
        if pd.isna(published_2025):
            published_2025 = None
        cars_for_rate = published_2026
        note = ""
        if code == "06435":
            hanau = cars_2026.get("06415")
            cars_for_rate = (published_2026 or 0) + (0 if pd.isna(hanau) else hanau)
            note = (
                "2026 cars used for the rate add Hanau (06415, 53,997 cars) to "
                "Main-Kinzig-Kreis. Destatis population includes Hanau; KBA reports "
                "Hanau separately. The two GDV classes are not averaged."
            )
        elif code == "07211":
            note = (
                "KBA prints one car stock on code 07211 under the name TRIER-SAARBURG. "
                "That figure is not used as the city's car count. See district_mapping."
            )
        elif code == "07235":
            note = (
                "No separate GDV class and no separate KBA car stock. The KBA figure "
                "printed on code 07211 is named TRIER-SAARBURG and is not split."
            )
        elif code == "16063":
            note = (
                "Eisenach (16056) merged into Wartburgkreis in 2021. The 2026 car "
                "stock already includes it, so the old Eisenach counts are not added."
            )
        elif code in NO_SINGLE_CLASS:
            note = "City and surrounding area have different GDV classes. See district_mapping."

        accident_values = {}
        for year in ("2020", "2021", "2022", "2023", "2024", "2025"):
            if code in accident_wide.index and year in accident_wide.columns:
                value = accident_wide.at[code, year]
                accident_values[year] = None if pd.isna(value) else int(value)
            else:
                accident_values[year] = None
        accidents_2025 = accident_values["2025"]
        rate = None
        if accidents_2025 is not None and cars_for_rate:
            rate = round(accidents_2025 / cars_for_rate * 1000, 2)
        cars_per_person = None
        if cars_for_rate and district.population_total:
            cars_per_person = round(cars_for_rate / district.population_total, 3)

        district_type = district.district_type or ""
        if code in {"03159", "03241", "07133", "07138", "07235"}:
            area = "mixed"
        elif "stadt" in district_type.lower():
            area = "urban"
        else:
            area = "rural"

        rows.append(
            {
                "geo_code": code,
                "geo_name": district.official_name,
                "bundesland": district.bundesland_destatis,
                "nuts3": district.nuts3,
                "district_type": district.district_type,
                "area_type": area,
                "area_km2": district.area_km2,
                "population_2024": district.population_total,
                "population_male": district.population_male,
                "population_female": district.population_female,
                "population_per_km2": district.population_per_km2,
                "gdv_coverage": (
                    "no_single_class" if code in NO_SINGLE_CLASS else "single_class"
                ),
                "liability_class_2026": gdv["liability_class_2026"],
                "liability_class_2027": gdv["liability_class_2027"],
                "comprehensive_class_2026": gdv["comprehensive_class_2026"],
                "comprehensive_class_2027": gdv["comprehensive_class_2027"],
                "partial_cover_class_2026": gdv["partial_cover_class_2026"],
                "partial_cover_class_2027": gdv["partial_cover_class_2027"],
                "passenger_cars_2025": published_2025,
                "passenger_cars_2026": published_2026,
                "passenger_cars_2026_for_rate": cars_for_rate,
                "accidents_2020": accident_values["2020"],
                "accidents_2021": accident_values["2021"],
                "accidents_2022": accident_values["2022"],
                "accidents_2023": accident_values["2023"],
                "accidents_2024": accident_values["2024"],
                "accidents_2025": accident_values["2025"],
                "accidents_2025_per_1000_cars": rate,
                "cars_per_person_2026": cars_per_person,
                "map_note": note,
            }
        )
    out = pd.DataFrame(rows)
    assert len(out) == 400
    assert int(out.population_2024.sum()) == 83577140
    return out


def build_mapping(df: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    names = districts.set_index("ags")["official_name"]
    states = districts.set_index("ags")["bundesland_destatis"]
    rows = []
    gdv = df[df.source_dataset == "gdv_regionalklassen"]
    for code, parent in PARTS.items():
        classes = classes_for(df, code)
        name = gdv.loc[gdv.geo_code == code, "geo_name"].iloc[0]
        state = gdv.loc[gdv.geo_code == code, "state_or_region"].iloc[0]
        rows.append(
            {
                "kind": "registration_part",
                "source_code": code,
                "source_name": name,
                "bundesland": state,
                "current_ags": parent,
                "current_district": names[parent],
                "liability_class_2026": classes["liability_class_2026"],
                "liability_class_2027": classes["liability_class_2027"],
                "comprehensive_class_2026": classes["comprehensive_class_2026"],
                "comprehensive_class_2027": classes["comprehensive_class_2027"],
                "partial_cover_class_2026": classes["partial_cover_class_2026"],
                "partial_cover_class_2027": classes["partial_cover_class_2027"],
                "how_to_use": (
                    "This registration area sits inside the current district. "
                    "Keep its own class. Do not copy the parent's population onto it "
                    "and do not average it with the other part."
                ),
            }
        )

    eisenach = classes_for(df, "16056")
    rows.append(
        {
            "kind": "boundary_change",
            "source_code": "16056",
            "source_name": "Eisenach",
            "bundesland": states["16063"],
            "current_ags": "16063",
            "current_district": names["16063"],
            "liability_class_2026": eisenach["liability_class_2026"],
            "liability_class_2027": eisenach["liability_class_2027"],
            "comprehensive_class_2026": eisenach["comprehensive_class_2026"],
            "comprehensive_class_2027": eisenach["comprehensive_class_2027"],
            "partial_cover_class_2026": eisenach["partial_cover_class_2026"],
            "partial_cover_class_2027": eisenach["partial_cover_class_2027"],
            "how_to_use": (
                "Eisenach merged into Wartburgkreis in July 2021. Map the old code "
                "to 16063. Do not add its 2018-2021 car counts on top of Wartburgkreis."
            ),
        }
    )

    hanau = classes_for(df, "06415")
    rows.append(
        {
            "kind": "boundary_change",
            "source_code": "06415",
            "source_name": "Hanau",
            "bundesland": states["06435"],
            "current_ags": "06435",
            "current_district": names["06435"],
            "liability_class_2026": hanau["liability_class_2026"],
            "liability_class_2027": hanau["liability_class_2027"],
            "comprehensive_class_2026": hanau["comprehensive_class_2026"],
            "comprehensive_class_2027": hanau["comprehensive_class_2027"],
            "partial_cover_class_2026": hanau["partial_cover_class_2026"],
            "partial_cover_class_2027": hanau["partial_cover_class_2027"],
            "how_to_use": (
                "Hanau is a 2026 KBA code and is not a Destatis 2024 district. "
                "Its population is inside Main-Kinzig-Kreis. Add its 2026 cars to "
                "Main-Kinzig only when calculating cars for that map area. Keep Hanau's "
                "own GDV class; do not average it with Main-Kinzig."
            ),
        }
    )

    rows.append(
        {
            "kind": "kba_name_conflict",
            "source_code": "07211",
            "source_name": "TRIER-SAARBURG (printed by KBA on the city code)",
            "bundesland": states["07211"],
            "current_ags": "07211",
            "current_district": names["07211"],
            "liability_class_2026": None,
            "liability_class_2027": None,
            "comprehensive_class_2026": None,
            "comprehensive_class_2027": None,
            "partial_cover_class_2026": None,
            "partial_cover_class_2027": None,
            "how_to_use": (
                "KBA code 07211 is named TRIER-SAARBURG, while Destatis 07211 is the "
                "city of Trier and 07235 is Trier-Saarburg. The car stock is left on "
                "the published code in the raw file and is not used for either rate."
            ),
        }
    )
    return pd.DataFrame(rows)


def build_europe(df: pd.DataFrame) -> pd.DataFrame:
    population = pd.read_csv(POP_CSV)
    population = population.rename(
        columns={"geo": "geo_code", "TIME_PERIOD": "year", "OBS_VALUE": "population", "OBS_FLAG": "population_flag"}
    )
    population["year"] = population["year"].astype(str)
    population = population[["geo_code", "year", "population", "population_flag"]]

    names = (
        df.loc[df.geo_level == "country", ["geo_code", "geo_name"]]
        .drop_duplicates()
        .groupby("geo_code")["geo_name"]
        .agg(lambda values: sorted(values, key=len)[-1])
    )

    def wide(source, measure):
        sub = df[(df.source_dataset == source) & (df.measure == measure)].copy()
        sub["value"] = pd.to_numeric(sub["value"])
        sub = sub[["geo_code", "geo_name", "year", "value"]].drop_duplicates(["geo_code", "year"])
        return sub

    cars = wide("eurostat_cars", "passenger_cars_per_1000_inhabitants").rename(
        columns={"value": "cars_per_1000"}
    )
    deaths = wide("eurostat_road_deaths", "road_deaths").rename(columns={"value": "road_deaths"})

    sa = df[df.source_file.str.startswith("SA_")].copy()
    sa["value"] = pd.to_numeric(sa["value"])
    wanted = {
        "non-life__gross_direct_business__R0110": "nonlife_premiums_written_eur_million",
        "non-life__gross_direct_business__R0210": "nonlife_premiums_earned_eur_million",
        "non-life__gross_direct_business__R0310": "nonlife_claims_incurred_eur_million",
    }
    sa = sa[sa.measure.isin(wanted)]
    sa["measure"] = sa["measure"].map(wanted)
    sa = sa.pivot_table(
        index=["geo_code", "geo_name", "year"], columns="measure", values="value", aggfunc="first"
    ).reset_index()

    europe = population.merge(cars.drop(columns="geo_name"), on=["geo_code", "year"], how="outer")
    europe = europe.merge(deaths.drop(columns="geo_name"), on=["geo_code", "year"], how="outer")
    europe = europe.merge(sa.drop(columns="geo_name"), on=["geo_code", "year"], how="outer")
    europe["country"] = europe["geo_code"].map(names).fillna(europe["geo_code"])
    europe["country"] = europe["country"].replace({"Eea": "EEA", "EEA": "EEA"})
    earned = europe["nonlife_premiums_earned_eur_million"]
    claims = europe["nonlife_claims_incurred_eur_million"]
    europe["nonlife_claims_ratio"] = (claims / earned).where(earned.notna() & (earned != 0))
    europe["nonlife_claims_ratio"] = europe["nonlife_claims_ratio"].round(4)
    europe["road_deaths_per_100000"] = (
        europe["road_deaths"] / europe["population"] * 100000
    ).round(2)
    europe["note"] = (
        "Solo Annual only. Claims ratio is R0310 divided by R0210 for the whole "
        "non-life business, not motor insurance. Quarterly and group files are excluded. "
        "EEA and Eea are the same area and are not mixed into these country rows."
    )
    columns = [
        "country",
        "geo_code",
        "year",
        "population",
        "population_flag",
        "cars_per_1000",
        "road_deaths",
        "road_deaths_per_100000",
        "nonlife_premiums_written_eur_million",
        "nonlife_premiums_earned_eur_million",
        "nonlife_claims_incurred_eur_million",
        "nonlife_claims_ratio",
        "note",
    ]
    europe = europe[columns].sort_values(["country", "year"])
    germany = europe[(europe.geo_code == "DE") & (europe.year == "2024")].iloc[0]
    assert int(germany.road_deaths) == 2770
    assert int(germany.cars_per_1000) == 590
    return europe


def copy_pdfs() -> None:
    PDF_OUT.mkdir(exist_ok=True)
    for path in sorted((ROOT / "Dataset").glob("*.pdf")):
        blank = BLANK_PAGES.get(path.name, set())
        target = PDF_OUT / path.name
        if not blank:
            shutil.copy2(path, target)
            continue
        reader = PdfReader(str(path))
        writer = PdfWriter()
        for index, page in enumerate(reader.pages):
            if index in blank:
                continue
            writer.add_page(page)
        with target.open("wb") as handle:
            writer.write(handle)
        print(f"{path.name}: removed blank page(s) {[n + 1 for n in sorted(blank)]}")


def main() -> None:
    before = checksum(RAW_CSV)
    districts = raw.load_population()
    df = pd.read_csv(RAW_CSV, dtype=str, low_memory=False)
    OUT.mkdir(exist_ok=True)

    germany = build_germany(df, districts)
    mapping = build_mapping(df, districts)
    europe = build_europe(df)
    germany.to_csv(OUT / "germany_districts.csv", index=False)
    mapping.to_csv(OUT / "district_mapping.csv", index=False)
    europe.to_csv(OUT / "eu_countries.csv", index=False)

    database = OUT / "motor_insurance_risk.sqlite"
    if database.exists():
        database.unlink()
    with sqlite3.connect(database) as connection:
        germany.to_sql("germany_districts", connection, index=False)
        mapping.to_sql("district_mapping", connection, index=False)
        europe.to_sql("eu_countries", connection, index=False)
        population = pd.read_csv(POP_CSV)
        population.to_sql("eurostat_population", connection, index=False)

    copy_pdfs()
    after = checksum(RAW_CSV)
    if before != after:
        raise SystemExit("The raw CSV changed. That is not allowed.")
    print(f"germany_districts {len(germany)}")
    print(f"district_mapping {len(mapping)}")
    print(f"eu_countries {len(europe)}")
    print("raw csv unchanged", before[:16])


if __name__ == "__main__":
    main()
