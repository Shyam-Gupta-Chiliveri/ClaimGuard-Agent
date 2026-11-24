# ClaimGuard data methodology

## The long fact table
motor_insurance_risk_raw.csv holds one published number per row with 13 columns: source_dataset, source_file, geo_level, geo_code, geo_name, state_or_region, year, period, measure, breakdown, value, unit, source_note. It is only ever appended to; existing rows are never rewritten. District codes (AGS, five digits) must be read as text so leading zeros survive.

## German districts (Kreise)
The project uses the 400 districts of the Destatis 2024 population table (04-kreise.xlsx). Eisenach (16056) merged into Wartburgkreis (16063) in July 2021, so older Eisenach figures are added to Wartburgkreis. Hanau (06415) left Main-Kinzig-Kreis on 1 January 2026 and appears separately in KBA data only from 2026; the models use the 2025 KBA stock to avoid the split. KBA prints one passenger-car figure on code 07211 under the name TRIER-SAARBURG, which cannot be split between the city of Trier (07211) and the Landkreis Trier-Saarburg (07235); fleet features for both are left empty.

## Accidents (Unfallatlas)
The Unfallatlas of the statistical offices records road accidents with personal injury only. Property-damage-only accidents, which make up most motor insurance claims, are not included. Coverage before 2020 is incomplete because some Bundeslaender joined later (2016: 233 districts, 2019: 393), so district features use 2020-2025, where all 16 states report. Accident category follows the most serious consequence: killed, seriously injured, slightly injured.

## Vehicle stock (KBA FZ1)
Kraftfahrt-Bundesamt vehicle stock on 1 January of each year, by district: passenger cars, motorcycles, trucks, tractors, buses, trailers, fuel type (petrol, diesel, battery electric, hybrid, gas) and emission standard (Euro 1 to Euro 6).

## GDV Regionalklassen
The Gesamtverband der Deutschen Versicherungswirtschaft (GDV) publishes a Regionalklasse for every registration district each year for motor third-party liability (Kfz-Haftpflicht, classes 1-12), fully comprehensive (Vollkasko, 1-9) and partial cover (Teilkasko, 1-16). A higher class means the district's claims cost per insured vehicle was higher than average. The classes come from insurers' own claims statistics, not from public accident data. Insurers are free to use them in their tariffs. Districts where GDV publishes more than one class are excluded from modelling.

## Europe (Eurostat and EIOPA)
Population: Eurostat demo_pjan, 1 January. Cars per 1,000 inhabitants: Eurostat road_eqs_carhab. Road deaths: Eurostat sdg_11_40. Insurance: EIOPA Solo Annual (SA) premiums, claims and expenses. The non-life claims ratio is claims incurred (R0310) divided by premiums earned (R0210) for the whole non-life business; EIOPA's public file has no separate motor line. Quarterly and group files are not mixed in.

## Fraud data
There is no public claim-level fraud dataset for Germany or Europe. The project uses published aggregates: GDV estimates (about 10 percent of property and casualty claims are suspicious; more than 6 billion euro a year), the BKA Police Crime Statistics key 517400 (insurance fraud and abuse, 1993-2024), Larmtjanst (Sweden), CBV (Netherlands), ALFA (France), ABI (United Kingdom) and Insurance Europe. Police counts measure reported crime, which is a tiny share of the fraud insurers suspect.

## Simulated claims
The 800-claim inbox is SIMULATED. District facts are copied from real tables; every claim fact is generated with seed 2026 so the triage system can be demonstrated. It contains no real person. Its triage band comes from the red-flag rules, so it cannot be used to measure fraud-detection accuracy.
