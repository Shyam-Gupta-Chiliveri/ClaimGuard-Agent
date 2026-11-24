"""Transparent red-flag triage for motor claims.

Same ten rules, points and bands as analysis/fraud_red_flag_rules.csv. The points are
project points, not official IVASS scores (IVASS: none 0, low 1-19, medium 20-49, high >49).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RULES: dict[str, dict[str, Any]] = {
    "R1": {"points": 15, "label": "Claim soon after the policy started", "basis": "IVASS CON1"},
    "R2": {"points": 10, "label": "Claim just before the policy expires", "basis": "IVASS CON1"},
    "R3": {"points": 10, "label": "Late notification (>30 days)", "basis": "IVASS VEI4 / SCO4"},
    "R4": {"points": 15, "label": "Repeat claimant (2+ claims in 12 months)", "basis": "IVASS VEI2 / SCO2"},
    "R5": {"points": 20, "label": "Description does not match the damage", "basis": "GDV dubious-claim definition, 2017 review"},
    "R6": {"points": 15, "label": "Amount higher than the repair estimate", "basis": "GDV 2017 review"},
    "R7": {"points": 20, "label": "Receipt or photo looks manipulated", "basis": "GDV press release 2 May 2024"},
    "R8": {"points": 10, "label": "Serious claim and no police report", "basis": "GDV dossier; BKA PKS key 517400"},
    "R9": {"points": 8, "label": "Injury claim with no witness", "basis": "GDV description test; IVASS SCO6"},
    "R10": {"points": 5, "label": "Vehicle older than 15 years", "basis": "IVASS VEI8"},
}

BANDS = [
    ("green", 0, 14, "Pay or handle in the normal queue"),
    ("amber", 15, 34, "Second look by a claims handler"),
    ("red", 35, 10_000, "Investigator queue"),
]

YES = {"yes", "true", "1", "ja", "y"}


def _yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in YES


def band_for(score: int) -> str:
    for name, low, high, _ in BANDS:
        if low <= score <= high:
            return name
    return "red"


@dataclass
class TriageResult:
    score: int
    band: str
    action: str
    fired: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score, "band": self.band, "action": self.action, "fired": self.fired}


def fired_rules(claim: dict[str, Any]) -> list[str]:
    after = int(claim.get("days_after_policy_start", 999))
    before = int(claim.get("days_before_policy_expiry", 999))
    report = int(claim.get("days_to_report", 0))
    prior = int(claim.get("prior_claims_12_months", 0))
    claimed = float(claim.get("claimed_amount_eur", 0))
    injury = _yes(claim.get("injury", "no"))
    police = _yes(claim.get("police_report", "no"))
    witness = _yes(claim.get("witness", "yes"))
    inflated = _yes(claim.get("amount_inflated", "no"))

    fired = []
    if after <= 30:
        fired.append("R1")
    if 1 <= before <= 30:
        fired.append("R2")
    if report > 30:
        fired.append("R3")
    if prior >= 2:
        fired.append("R4")
    if not _yes(claim.get("description_matches_damage", "yes")):
        fired.append("R5")
    if inflated:
        fired.append("R6")
    if _yes(claim.get("document_manipulated", "no")):
        fired.append("R7")
    if not police and (injury or claimed >= 5000):
        fired.append("R8")
    if injury and not witness:
        fired.append("R9")
    if int(claim.get("vehicle_age_years", 0)) > 15:
        fired.append("R10")
    return fired


def score_claim(claim: dict[str, Any]) -> TriageResult:
    fired = fired_rules(claim)
    score = sum(RULES[r]["points"] for r in fired)
    band = band_for(score)
    action = next(a for name, *_, a in BANDS if name == band)
    details = [{"rule_id": r, **RULES[r]} for r in fired]
    return TriageResult(score=score, band=band, action=action, fired=details)
