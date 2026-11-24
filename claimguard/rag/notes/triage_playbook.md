# Claim triage playbook

## Bands
- Green, score 0-14: pay or handle in the normal queue.
- Amber, score 15-34: second look by a claims handler before payment.
- Red, score 35 or more: investigator queue (Spezialabteilung / SIU).

The points are project points chosen so ten rules can be added up. They are not the official IVASS indicator scores; IVASS grades its own 22-indicator total as none at 0, low at 1-19, medium at 20-49 and high above 49.

## Rules
- R1 Claim soon after the policy started (15 points): incident 1 to 30 days after inception. IVASS indicator CON1.
- R2 Claim just before the policy expires (10): incident 1 to 30 days before expiry. IVASS CON1.
- R3 Late notification (10): reported more than 30 days after the incident. IVASS VEI4 and SCO4.
- R4 Repeat claimant (15): two or more other claims in the previous 12 months. IVASS VEI2 and SCO2.
- R5 Description does not match the damage (20): GDV definition of a dubious claim; in the GDV 2017 review 65 percent of problematic claims had happened, but not as described.
- R6 Amount looks exaggerated (15): claimed amount above the repair estimate; about one in three problematic claims in the GDV 2017 review.
- R7 Receipt or photo looks manipulated (20): GDV press release of 2 May 2024.
- R8 Serious claim and no police report (10): injury, or 5,000 euro or more, without a police report. GDV advises calling the police when a provoked accident is suspected.
- R9 Injury claim with no witness (8).
- R10 Old vehicle (5): more than 15 years old. IVASS VEI8.

## Anomaly second opinion
An Isolation Forest scores how unusual a claim's numbers are (timing, amount versus estimate, prior claims, vehicle age, injury, police report, witness). The top 5 percent get a "second look" flag even when no rule fires. It is not a fraud classifier and has no fraud labels.

## Fair handling
A red band is a reason to investigate, not an accusation. The handler records the reason, the customer keeps normal rights, and the decision stays with a person. Automated decisions that significantly affect a customer fall under GDPR Article 22, and BaFin expects explainable, documented algorithmic processes.
