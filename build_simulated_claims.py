"""Red-flag rulebook and a simulated German claims inbox.

Does not modify motor_insurance_risk_raw.csv.
District names and risk figures are copied from analysis/germany_districts.csv.
Every claim fact is simulated and labelled as such.
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path("/Users/shyam/Downloads/Insurance project")
DISTRICTS = ROOT / "analysis" / "germany_districts.csv"
RULES = ROOT / "analysis" / "fraud_red_flag_rules.csv"
INBOX = ROOT / "analysis" / "simulated_claims_inbox.csv"
RAW = ROOT / "motor_insurance_risk_raw.csv"

RULEBOOK = [
    ("R1", "Claim soon after the policy started", 15, "Incident is 1 to 30 days after the policy start", "IVASS indicator CON1: a claim in the days after inception", "IVASS Provvedimento 47, Annex 1"),
    ("R2", "Claim just before the policy expires", 10, "Incident is 1 to 30 days before expiry", "IVASS indicator CON1: a claim in the days before expiry", "IVASS Provvedimento 47, Annex 1"),
    ("R3", "Late notification", 10, "Claim is reported more than 30 days after the incident", "IVASS indicators VEI4 and SCO4: late reports", "IVASS Provvedimento 47, Annex 1"),
    ("R4", "Repeat claimant", 15, "Two or more other claims in the previous 12 months", "IVASS indicators VEI2 and SCO2: several claims in a short period", "IVASS Provvedimento 47, Annex 1"),
    ("R5", "Description does not match the damage", 20, "The stated accident story does not fit the damage", "GDV definition of a dubious claim. In the 2017 review, 65 percent of problematic claims had happened, but not as described", "GDV dossier and 2017 special review"),
    ("R6", "Amount looks exaggerated", 15, "The claimed amount is higher than the repair estimate", "GDV 2017 review: about one in three problematic claims had an inflated amount", "GDV special review, 5 May 2017"),
    ("R7", "Receipt or photo looks manipulated", 20, "A receipt or photo shows signs of alteration", "GDV: manipulated receipts are a stated mark of a dubious claim", "GDV press release, 2 May 2024"),
    ("R8", "Serious claim and no police report", 10, "Injury, or a claim of at least 5,000 euro, with no police report", "GDV advises calling the police when a provoked accident is suspected. In 2024 the police recorded 2,129 insurance-fraud cases", "GDV dossier; BKA PKS 2024, key 517400"),
    ("R9", "Injury claim with no witness", 8, "Someone is injured and no witness is named", "A check used with the GDV description test. IVASS scores a witness who appears in many claims (SCO6); this demo flags the simpler missing-witness case", "GDV description test; IVASS SCO6"),
    ("R10", "Old vehicle", 5, "Vehicle is more than 15 years old", "IVASS indicator VEI8 flags vehicles registered more than N years. This demo sets N at 15", "IVASS Provvedimento 47, Annex 1"),
]

BANDS = [
    ("green", 0, 14, "Pay or handle in the normal queue"),
    ("amber", 15, 34, "Second look by a claims handler"),
    ("red", 35, 999, "Investigator queue"),
]
POINTS = {rule_id: points for rule_id, _, points, *_ in RULEBOOK}


def load_districts():
    with DISTRICTS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    usable = [row for row in rows if row["geo_code"] and row["population_2024"]]
    weights = [float(row["population_2024"]) for row in usable]
    return usable, weights


def band_for(score):
    for name, low, high, _ in BANDS:
        if low <= score <= high:
            return name
    return "red"


def choose_rules(target):
    red_sets = [
        ["R5", "R7"],
        ["R1", "R5"],
        ["R4", "R6", "R8"],
        ["R5", "R6", "R10"],
        ["R7", "R8", "R4"],
        ["R1", "R7", "R3"],
    ]
    amber_sets = [
        ["R1"],
        ["R5"],
        ["R6"],
        ["R4"],
        ["R7"],
        ["R6", "R8"],
        ["R2", "R3"],
        ["R4", "R10"],
        ["R9", "R3"],
        ["R1", "R10"],
    ]
    green_sets = [
        [],
        [],
        [],
        ["R10"],
        ["R3"],
        ["R2"],
        ["R9"],
        ["R8"],
    ]
    pool = {"red": red_sets, "amber": amber_sets, "green": green_sets}[target]
    chosen = set(random.choice(pool))
    if "R1" in chosen and "R2" in chosen:
        chosen.remove("R2")
    return chosen


def build_claim(number, district, rules):
    incident_date = date(2025, 1, 1) + timedelta(days=random.randrange(0, 365))
    if "R1" in rules:
        days_after_start = random.randint(1, 30)
    elif "R2" in rules:
        days_before_expiry = random.randint(1, 30)
        days_after_start = 365 - days_before_expiry
    else:
        days_after_start = random.randint(60, 300)
    policy_start = incident_date - timedelta(days=days_after_start)
    policy_end = policy_start + timedelta(days=365)
    days_before_expiry = (policy_end - incident_date).days
    days_to_report = random.randint(31, 90) if "R3" in rules else random.randint(0, 10)
    report_date = incident_date + timedelta(days=days_to_report)
    prior_claims = random.randint(2, 4) if "R4" in rules else random.randint(0, 1)
    description_matches = "no" if "R5" in rules else "yes"
    amount_inflated = "yes" if "R6" in rules else "no"
    document_manipulated = "yes" if "R7" in rules else "no"
    vehicle_age = random.randint(16, 28) if "R10" in rules else random.randint(1, 12)
    injury = "yes" if "R9" in rules or ("R8" in rules and random.random() < 0.5) else "no"
    witness = "no" if "R9" in rules else "yes"
    if amount_inflated == "yes":
        repair_estimate = random.randrange(800, 4500, 50)
        claimed = int(round(repair_estimate * random.uniform(1.6, 2.4), -1))
    elif injury == "yes":
        repair_estimate = random.randrange(1500, 6000, 50)
        claimed = random.randrange(5000, 18000, 100)
    else:
        repair_estimate = random.randrange(350, 3200, 50)
        claimed = repair_estimate
    if "R8" in rules and injury == "no" and claimed < 5000:
        claimed = random.randrange(5000, 12000, 100)
    police = "no" if "R8" in rules else ("yes" if claimed >= 5000 or injury == "yes" else random.choice(["yes", "no"]))
    fired = []
    if days_after_start <= 30:
        fired.append("R1")
    if 1 <= days_before_expiry <= 30:
        fired.append("R2")
    if days_to_report > 30:
        fired.append("R3")
    if prior_claims >= 2:
        fired.append("R4")
    if description_matches == "no":
        fired.append("R5")
    if amount_inflated == "yes":
        fired.append("R6")
    if document_manipulated == "yes":
        fired.append("R7")
    if police == "no" and (injury == "yes" or claimed >= 5000):
        fired.append("R8")
    if injury == "yes" and witness == "no":
        fired.append("R9")
    if vehicle_age > 15:
        fired.append("R10")
    score = sum(POINTS[rule_id] for rule_id in fired)
    reasons = {
        "R1": "filed within 30 days of the policy start",
        "R2": "filed within 30 days of expiry",
        "R3": "reported more than 30 days after the incident",
        "R4": "two or more earlier claims in 12 months",
        "R5": "the description does not match the damage",
        "R6": "the amount is higher than the repair estimate",
        "R7": "a receipt or photo looks manipulated",
        "R8": "serious claim with no police report",
        "R9": "injury claim with no witness",
        "R10": "vehicle is more than 15 years old",
    }
    summary = "No red flag fired." if not fired else "; ".join(reasons[rule_id] for rule_id in fired)
    return {
        "record_type": "simulated",
        "simulation_label": "SIMULATED. Not a real claim and not a real person. District facts are copied from the German district table. Claim facts are generated for the triage demo.",
        "claim_id": f"SIM-{number:04d}",
        "claimant_id": f"SIM-PERSON-{number:04d}",
        "policy_id": f"SIM-POLICY-{number:04d}",
        "geo_code": district["geo_code"],
        "geo_name": district["geo_name"],
        "bundesland": district["bundesland"],
        "area_type": district["area_type"],
        "liability_class_2027": district["liability_class_2027"],
        "accidents_2025_per_1000_cars": district["accidents_2025_per_1000_cars"],
        "policy_start": policy_start.isoformat(),
        "policy_end": policy_end.isoformat(),
        "incident_date": incident_date.isoformat(),
        "report_date": report_date.isoformat(),
        "days_after_policy_start": days_after_start,
        "days_before_policy_expiry": days_before_expiry,
        "days_to_report": days_to_report,
        "prior_claims_12_months": prior_claims,
        "description_matches_damage": description_matches,
        "amount_inflated": amount_inflated,
        "document_manipulated": document_manipulated,
        "police_report": police,
        "injury": injury,
        "witness": witness,
        "vehicle_age_years": vehicle_age,
        "repair_estimate_eur": repair_estimate,
        "claimed_amount_eur": claimed,
        "rules_fired": ";".join(fired),
        "score": score,
        "triage": band_for(score),
        "reason_summary": summary,
    }


def main():
    before = RAW.stat().st_size
    random.seed(2026)
    districts, weights = load_districts()
    targets = ["red"] * 24 + ["amber"] * 56 + ["green"] * 720
    random.shuffle(targets)
    claims = []
    for number, target in enumerate(targets, start=1):
        district = random.choices(districts, weights=weights, k=1)[0]
        claims.append(build_claim(number, district, choose_rules(target)))

    with RULES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "rule_id", "indicator", "points", "applies_when", "published_basis", "source",
            "green_max_score", "amber_min_score", "amber_max_score", "red_min_score", "scale_note",
        ])
        scale_note = (
            "Project points for this demo, so the ten rules can be added up. "
            "They are not the official IVASS indicator scores. "
            "IVASS classifies its own 22-indicator total as none at 0, low at 1-19, medium at 20-49 and high above 49. "
            "This demo uses green 0-14, amber 15-34 and red 35 or more."
        )
        for rule in RULEBOOK:
            writer.writerow([*rule, 14, 15, 34, 35, scale_note])

    with INBOX.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(claims[0].keys()))
        writer.writeheader()
        writer.writerows(claims)

    counts = {name: sum(claim["triage"] == name for claim in claims) for name, *_ in BANDS}
    if RAW.stat().st_size != before:
        raise SystemExit("The long CSV changed")
    print(len(claims), counts)


if __name__ == "__main__":
    main()
