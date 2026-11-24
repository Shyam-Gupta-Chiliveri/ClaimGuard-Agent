# Model card: Regionalklasse predictor (v5cd4340c2319)

Predict the GDV Regionalklasse 2027 of a German district from public accident, fleet and population data.

## Data

- 400 German districts (Destatis 2024 boundaries). Districts without a single GDV class are excluded.
- Features: Unfallatlas accidents with personal injury 2020-2025 (Destatis), KBA vehicle stock 1 Jan 2025, Destatis population 2024.
- Target: GDV Regionalklassen 2027. GDV sets classes from insurers' claims experience, which includes property-damage-only claims that the Unfallatlas does not record.
- Trier (07211) and Trier-Saarburg (07235) have no fleet features because KBA reports them as one figure.

## Validation

Spatial cross-validation: GroupKFold over the 16 Bundeslaender (8 folds). Random 5-fold is shown only to measure leakage.

### Kfz-Haftpflicht (liability_class_2027, n=395)

| model | spatial MAE | spatial within ±1 | random MAE | spearman (spatial) |
|---|---|---|---|---|
| baseline_median | 2.33 | 36% | 2.19 | -0.36 |
| ridge | 1.60 | 57% | 1.10 | 0.68 |
| gradient_boosting | 1.50 | 58% | 1.08 | 0.70 |
| last year's class (2026) | 0.26 | 100% | - | 0.98 |

Best model: **gradient_boosting**. Top drivers (held-out permutation importance): log_density, share_hybrid, share_with_bicycle, share_with_pedestrian, share_bev.
Gate: passed.

### Vollkasko (comprehensive_class_2027, n=395)

| model | spatial MAE | spatial within ±1 | random MAE | spearman (spatial) |
|---|---|---|---|---|
| baseline_median | 1.55 | 53% | 1.55 | 0.00 |
| ridge | 1.22 | 68% | 1.06 | 0.62 |
| gradient_boosting | 1.37 | 60% | 1.11 | 0.46 |
| last year's class (2026) | 0.12 | 100% | - | 0.98 |

Best model: **ridge**. Top drivers (held-out permutation importance): share_with_bicycle, motorcycles_per_1000_people, accidents_per_1000_cars, log_density, share_hybrid.
Gate: passed.

### Teilkasko (partial_cover_class_2027, n=395)

| model | spatial MAE | spatial within ±1 | random MAE | spearman (spatial) |
|---|---|---|---|---|
| baseline_median | 2.88 | 33% | 2.78 | -0.30 |
| ridge | 2.14 | 42% | 1.89 | 0.68 |
| gradient_boosting | 2.28 | 37% | 1.83 | 0.59 |
| last year's class (2026) | 0.18 | 100% | - | 0.99 |

Best model: **ridge**. Top drivers (held-out permutation importance): area_km2, share_with_bicycle, is_urban, accidents_per_1000_cars, share_bev.
Gate: passed.

## Intended use and limits

- Explains which public factors line up with GDV classes and flags districts whose class is higher or lower than public data suggests.
- Not a pricing model. It does not use insurer claims data, and residuals are hypotheses for an actuary to check, not evidence of mispricing.
- The 2026 class predicts the 2027 class almost perfectly; the model is built without it on purpose, to learn drivers rather than persistence.
