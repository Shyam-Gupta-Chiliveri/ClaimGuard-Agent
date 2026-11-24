# ClaimGuard — analysis of German motor-insurance risk and claim fraud

All figures are computed by `pipeline/report.py` from the project marts. Claims data is SIMULATED where stated.

## Germany

### Density beats accidents — ρ = 0.74

Population density ranks districts' Haftpflicht class far better (Spearman 0.74) than injury accidents per car do (0.27). Median class: urban 8, rural 4. GDV classes are driven by claim cost, and most claims are property-damage-only accidents the Unfallatlas never records.

### Rural crashes are rarer but harsher — 21% vs 13%

In rural districts 21% of injury accidents kill or seriously injure someone, against 13% in cities, while accidents per 1,000 cars are 4.5 vs 6.4. Frequency and severity point in opposite directions — the core idea of a frequency/severity tariff model.

### State spread — 12.0 → 1.3

Car-weighted Haftpflicht class is highest in Berlin (12.0) and lowest in Mecklenburg-Vorpommern (1.3).

### Teilkasko has a different map — ρ(area) = 0.52

Teilkasko covers theft, glass, storm, hail and collisions with game. Its class rises with district area (Spearman 0.52), consistent with game collisions in large rural districts. Highest median class: Berlin (12) and Mecklenburg-Vorpommern (12) — a city and a rural state at once, so theft and countryside risks both matter; lowest: Nordrhein-Westfalen (5).

### Injury accidents rebound after 2020 — +14.7%

Injury accidents went from 237,994 (2020, pandemic year) to 273,007 (2025). Years before 2020 are left out because not every state reported.

## Europe

### Germany's roads in Europe — 3.32 per 100k

Germany had 3.32 road deaths per 100,000 people in 2024, rank 23 of 33 countries (1 = most dangerous).

### Non-life claims ratio — 61%

German insurers paid out 61% of non-life premiums earned as claims in 2024 (EIOPA Solo Annual); the median of 30 countries is 59%. This is all non-life business, not motor alone.

## Fraud

### The fraud reporting gap — 2,129 cases

Police recorded 2,129 insurance-fraud cases in 2024 (PKS 517400), 82% below the 2004 peak of 11,743. Insurers (GDV) still treat about 10% of claims as suspicious — fraud is handled inside claims departments, rarely by the police.

### Sweden: refused motor claims — +80%

Swedish insurers refused 289 MSEK of motor claims after investigation in 2024, up from 161 MSEK in 2020 (Larmtjänst).

## Machine learning

### EV adoption is uneven — 1.0% – 9.1%

Battery-electric share of the car stock (KBA 1 Jan 2025) ranges from 1.0% to 9.1% (Wolfsburg, Stadt). The 2026 fleet already drifts: share hybrid PSI 1.33 → drift status 'retrain'.

### Spatial leakage is real — MAE 1.08 → 1.50

A random split makes the model look 39% better than it is. Validated on unseen Bundesländer, the gradient_boosting model misses the Haftpflicht class by 1.50 classes on average (median baseline 2.33), 58% within ±1.

### Where public data under-explains the class — +2.0 classes

GDV classes sit above the model most in Bayern (mean residual +2.0) and below it in Mecklenburg-Vorpommern (-2.0). Largest gaps: Kempten (Allgäu) (+5.7), Oberallgäu (+5.2), Miesbach (+5.2), Weilheim-Schongau (+4.8). Hypotheses to test with claims data: tourist and transit traffic, repair-cost levels, theft, fraud.

## Triage

### Triage funnel (SIMULATED) — 24 red / 800

Of 800 simulated claims, 56 go to a handler and 24 to investigators. The anomaly model sends 26 green claims for a second look that no rule caught.

## Method notes

- Districts: 400 Kreise (Destatis 2024 boundaries); Eisenach is folded into Wartburgkreis.
- Accidents: Unfallatlas, injury accidents only, 2020-2025 average.
- Fleet: KBA FZ1, 1 January 2025 (training) and 2026 (drift check).
- Models: spatial GroupKFold by Bundesland; see `reports/model_card_regionalklasse.md`.
