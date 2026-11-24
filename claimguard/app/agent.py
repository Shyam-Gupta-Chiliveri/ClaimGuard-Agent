"""ClaimGuard agent: plans, calls tools, and answers with sources.

`run(question)` yields events for the UI:
  {"type": "plan", "text"}            what the agent intends to do
  {"type": "tool", "name", "args"}    a tool call
  {"type": "observation", "name", "summary"}
  {"type": "answer", "text", "sources", "mode"}
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from app import llm, tools
from app.store import store

SYSTEM = """You are ClaimGuard, an analyst assistant for German motor insurance: regional risk (GDV Regionalklassen),
road accidents (Unfallatlas), vehicle fleet (KBA), European comparison (Eurostat, EIOPA) and claim-fraud triage.
Rules:
- Get every number from a tool. Never invent figures. If a tool has no data, say so.
- Claims in the inbox are SIMULATED; say so whenever you use them.
- Fraud statistics from different countries measure different things; do not rank them as if comparable.
- GDV classes reflect insurers' claims cost; public data explains only part of them. Model gaps are hypotheses.
- Answer in the user's language (German or English), concise, with a short bullet list when useful.
- End with a 'Sources:' line naming the datasets or documents used."""

MAX_STEPS = 6


def _summary(result: dict, lang: str = "en") -> str:
    de = lang == "de"
    if "error" in result:
        return result["error"]
    if "rows" in result:
        n = len(result["rows"])
        return f"{n} Zeilen" if de else f"{n} rows"
    if "hits" in result:
        n = len(result["hits"])
        head = f"{n} Textstellen: " if de else f"{n} passages: "
        return head + ", ".join(f"{h['source']} ({h['locator']})" for h in result["hits"][:3])
    if "district" in result:
        return result["district"]["geo_name"]
    if "result" in result:
        r = result["result"]
        return f"Punktzahl {r['score']} → {r['band']}" if de else f"score {r['score']} → {r['band']}"
    return ", ".join(list(result)[:5])


def _sources(results: list[tuple[str, dict]]) -> list[str]:
    out: list[str] = []
    for _, r in results:
        for s in r.get("sources", []):
            if s not in out:
                out.append(s)
        hits = r.get("hits", [])
        for h in hits if len(results) == 1 else hits[:1]:
            label = f"{h['source']} — {h['locator']}"
            if label not in out:
                out.append(label)
    return out[:8]


# ---------------------------------------------------------------- LLM mode


def run_llm(question: str, history: list[dict], lang: str = "en") -> Iterator[dict]:
    user = question + ("\n\nAntworte auf Deutsch." if lang == "de" else "")
    messages = [{"role": "system", "content": SYSTEM}, *history[-6:], {"role": "user", "content": user}]
    results: list[tuple[str, dict]] = []
    model = llm.describe()["model"]
    n_tools = len(tools.TOOLS)
    yield {"type": "plan", "text": f"Schlussfolgern mit {model} und {n_tools} Werkzeugen." if lang == "de"
           else f"Reasoning with {model} and {n_tools} tools."}
    for _ in range(MAX_STEPS):
        msg = llm.chat(messages, tools.openai_tools())
        calls = msg.get("tool_calls") or []
        if not calls:
            yield {"type": "answer", "text": msg.get("content") or "", "sources": _sources(results), "mode": "llm"}
            return
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool", "name": name, "args": args}
            result = tools.call(name, args)
            results.append((name, result))
            yield {"type": "observation", "name": name, "summary": _summary(result, lang)}
            messages.append({"role": "tool", "tool_call_id": c.get("id", name), "name": name,
                             "content": json.dumps(result, ensure_ascii=False, default=str)[:12000]})
    nudge = "Antworte jetzt mit dem, was du hast. Antworte auf Deutsch." if lang == "de" else "Answer now with what you have."
    final = llm.chat(messages + [{"role": "user", "content": nudge}])
    yield {"type": "answer", "text": final.get("content") or "", "sources": _sources(results), "mode": "llm"}


# ---------------------------------------------------------------- offline planner

METRIC_WORDS = [
    (r"teilkasko|partial", "partial_cover_class_2027"),
    (r"vollkasko|comprehensive", "comprehensive_class_2027"),
    (r"haftpflicht|liability|regionalklass|expensive|teuer|cheap|günstig|guenstig|class", "liability_class_2027"),
    (r"accidents? per|unfälle je|unfallrate|accident rate|dangerous|gefährlich", "accidents_per_1000_cars"),
    (r"bicycle|fahrrad|cycl|rad", "share_with_bicycle"),
    (r"electric|elektro|\bbev\b|\bev\b", "share_bev"),
    (r"densit|dichte", "population_per_km2"),
    (r"night|nacht", "share_night_22_05"),
    (r"severe|serious|schwer|deadly|tödlich", "share_killed_or_serious"),
]
STATES = ["baden-württemberg", "bayern", "berlin", "brandenburg", "bremen", "hamburg", "hessen",
          "mecklenburg-vorpommern", "niedersachsen", "nordrhein-westfalen", "rheinland-pfalz", "saarland",
          "sachsen-anhalt", "sachsen", "schleswig-holstein", "thüringen"]
STATE_ALIASES = {"bavaria": "bayern", "nrw": "nordrhein-westfalen", "hesse": "hessen", "saxony": "sachsen",
                 "lower saxony": "niedersachsen", "thuringia": "thüringen"}


def _find_metric(q: str, default: str = "liability_class_2027") -> str:
    for pattern, metric in METRIC_WORDS:
        if re.search(pattern, q):
            return metric
    return default


def _find_state(q: str) -> str | None:
    for alias, state in STATE_ALIASES.items():
        if alias in q:
            return state
    for s in STATES:
        if s in q:
            return s
    return None


def _find_district(q: str) -> str | None:
    best = None
    for name in store.districts.geo_name:
        short = name.split(",")[0].strip().lower()
        if len(short) >= 4 and re.search(r"(?<![\w-])" + re.escape(short) + r"(?![\w-])", q):
            if best is None or len(short) > len(best):
                best = short
    if best and best in STATES and not re.search(r"stadt|city|kreis|district", q):
        return None
    return best


def plan(question: str) -> list[tuple[str, dict]]:
    q = question.lower()
    steps: list[tuple[str, dict]] = []
    claim = re.search(r"sim-\d{1,4}", q)
    if claim:
        cid = claim.group(0).upper()
        num = cid.split("-")[1].zfill(4)
        return [("claim_lookup", {"claim_id": f"SIM-{num}"}), ("search_documents", {"query": "triage bands red amber rules"})]
    if re.search(r"queue|investigat|red claims|rote|amber|suspicious claims|verdächtig", q):
        band = "amber" if "amber" in q else "red"
        steps.append(("triage_queue", {"band": band, "n": 8}))
    if re.search(r"police|polizei|bka|pks|crime|kriminal", q):
        steps.append(("police_fraud_series", {}))
    if re.search(r"fraud|betrug|missbrauch", q) and not steps:
        country = next((c for c in ("germany", "deutschland", "sweden", "netherlands", "france", "uk", "europe")
                        if c in q), None)
        steps.append(("fraud_facts", {"country": country} if country else {}))
    if re.search(r"over.?priced|under.?priced|higher than|lower than|gap|residual|unexplained|surpris", q):
        direction = "below" if re.search(r"under|lower|below", q) else "above"
        steps.append(("priced_gaps", {"target": _find_metric(q), "direction": direction, "n": 8}))
    elif re.search(r"model|accuracy|genauigkeit|drift|mlops|validation|cross.?valid", q):
        steps.append(("model_info", {}))
    if re.search(r"europ|countr|länder|\beu\b|compare germany|vergleich", q):
        if re.search(r"claims ratio|eiopa|premium|prämie|schadenquote|insurance market", q):
            metric = "nonlife_claims_ratio"
        elif re.search(r"cars per|car ownership|motorisation|pkw je", q):
            metric = "cars_per_1000"
        else:
            metric = "road_deaths_per_100000"
        steps.append(("europe_compare", {"metric": metric}))
    if re.search(r"bundesl|states|länder ranking|by state", q) and not any(s[0] == "europe_compare" for s in steps):
        steps.append(("compare_states", {}))
    district = _find_district(q)
    if district and not steps:
        steps.append(("district_profile", {"district": district}))
    if re.search(r"top|highest|most|lowest|least|cheapest|rank|höchste|niedrigste|teuerste|günstigste", q) and \
            not any(s[0] in ("priced_gaps", "europe_compare", "compare_states") for s in steps):
        order = "asc" if re.search(r"lowest|least|cheapest|niedrigste|günstigste|safest", q) else "desc"
        args: dict[str, Any] = {"metric": _find_metric(q), "order": order, "n": 10}
        state = _find_state(q)
        if state:
            args["bundesland"] = state
        if re.search(r"rural|ländlich|land", q):
            args["area_type"] = "rural"
        elif re.search(r"urban|city|cities|städte|stadt", q):
            args["area_type"] = "urban"
        steps.append(("rank_districts", args))
    if not steps or re.search(r"what is|was ist|what are|define|defin|explain|erklär|why|warum|how|wie|caveat|limitation", q):
        steps.append(("search_documents", {"query": question, "k": 4}))
    return steps[:4]


def _fmt(v: Any, digits: int = 2, lang: str = "en") -> str:
    if v is None:
        return "k. A." if lang == "de" else "n/a"
    if isinstance(v, float):
        if abs(v) < 1 and v != 0:
            text = f"{v:.1%}" if digits == 2 else f"{v:.{digits}f}"
        else:
            text = f"{v:,.{0 if v.is_integer() else 1}f}"
    elif isinstance(v, int):
        text = f"{v:,}"
    else:
        return str(v)
    if lang == "de":
        text = text.replace(",", "§").replace(".", ",").replace("§", ".")
    return text


def compose(question: str, results: list[tuple[str, dict]], lang: str = "en") -> str:
    de = lang == "de"

    def L(en: str, german: str) -> str:
        return german if de else en

    def n(v: Any, digits: int = 2) -> str:
        return _fmt(v, digits, lang)

    parts: list[str] = []
    for name, r in results:
        if "error" in r:
            parts.append(f"⚠️ {r['error']}")
            continue
        if name == "district_profile":
            d = r["district"]
            people = L("people", "Einwohner")
            parts.append(f"**{d['geo_name']}** ({d['bundesland']}, {d['area_type']}, {n(d['population_2024'])} {people})")
            parts.append(f"- GDV Regionalklassen 2027: Haftpflicht **{n(d['liability_class_2027'])}**/12, "
                         f"Vollkasko {n(d['comprehensive_class_2027'])}/9, Teilkasko {n(d['partial_cover_class_2027'])}/16")
            if d.get("liability_class_2027_percentile") is not None:
                parts.append(L(
                    f"- Haftpflicht class is higher than in {d['liability_class_2027_percentile']:.0f}% of districts",
                    f"- Die Haftpflichtklasse liegt höher als in {d['liability_class_2027_percentile']:.0f} % der Kreise",
                ))
            parts.append(L(
                f"- Injury accidents per 1,000 cars: {n(d['accidents_per_1000_cars'], 1)} "
                f"(2025: {n(d['accidents_2025'])} accidents); cars per 1,000 people: {n(d['cars_per_1000_people'], 1)}",
                f"- Verletzungsunfälle je 1.000 Pkw: {n(d['accidents_per_1000_cars'], 1)} "
                f"(2025: {n(d['accidents_2025'])} Unfälle); Pkw je 1.000 Einwohner: {n(d['cars_per_1000_people'], 1)}",
            ))
            parts.append(L(
                f"- Bicycle involvement {n(d['share_with_bicycle'])}, battery-electric cars {n(d['share_bev'])}",
                f"- Anteil mit Fahrrad {n(d['share_with_bicycle'])}, batterieelektrische Pkw {n(d['share_bev'])}",
            ))
            m = r.get("model_explanation")
            if m:
                drivers = ", ".join(f"{x['label']} ({x['effect']:+.1f})" for x in m["drivers"][:4])
                parts.append(L(
                    f"- Model (spatial CV, {m['model']}): predicted {m['predicted']:.1f} vs actual {n(m['actual'])} "
                    f"→ gap {m['gap']:+.1f}. Main drivers: {drivers}",
                    f"- Modell (räumliche Kreuzvalidierung, {m['model']}): Prognose {m['predicted']:.1f} gegen Ist {n(m['actual'])} "
                    f"→ Abweichung {m['gap']:+.1f}. Wichtigste Treiber: {drivers}",
                ))
        elif name == "rank_districts":
            f = r["filters"]
            scope = " ".join(x for x in [f.get("area_type"), f.get("bundesland") and f"in {f['bundesland'].title()}"] if x)
            rank_word = L("Highest" if r["order"] == "desc" else "Lowest", "Höchste" if r["order"] == "desc" else "Niedrigste")
            parts.append(f"**{rank_word} {r['metric_label']}** {scope}".strip())
            for i, row in enumerate(r["rows"], 1):
                parts.append(f"{i}. {row['geo_name']} ({row['bundesland']}) — {n(row[r['metric']])}")
            parts.append(L(f"German median: {n(r['german_median'])}", f"Deutscher Median: {n(r['german_median'])}"))
        elif name == "compare_states":
            parts.append(L("**Bundesländer by car-weighted Haftpflicht class**", "**Bundesländer nach Pkw-gewichteter Haftpflichtklasse**"))
            for row in r["rows"][:16]:
                parts.append(f"- {row['bundesland']}: {n(row[r['metric']], 1) if isinstance(row[r['metric']], float) else row[r['metric']]}")
        elif name == "europe_compare":
            parts.append(L(
                f"**{r['metric_label']}, {r['year']}** — Germany ranks {r['germany_rank']} of {r['countries']} (1 = highest)",
                f"**{r['metric_label']}, {r['year']}** — Deutschland liegt auf Rang {r['germany_rank']} von {r['countries']} (1 = höchster Wert)",
            ))
            rows = r["rows"]
            show = rows[:5] + [x for x in rows if x["geo_code"] == "DE" and x not in rows[:5]] + rows[-3:]
            for row in show:
                v = row[r["metric"]]
                parts.append(f"- {row['country']}: {v:.2f}" if isinstance(v, float) else f"- {row['country']}: {v}")
            if r.get("caveat"):
                parts.append(f"_{r['caveat']}_")
        elif name == "fraud_facts":
            parts.append(L("**Published insurance-fraud figures**", "**Veröffentlichte Zahlen zum Versicherungsbetrug**"))
            for row in r["rows"][:12]:
                value = f"{row['value']:,.2f}".rstrip("0").rstrip(".")
                parts.append(f"- {row['geo_code']} {row['year']}: {row['measure'].replace('_', ' ')} "
                             f"({row['breakdown'].replace('_', ' ')}) = {value} {row['unit'].replace('_', ' ')}")
            parts.append(f"_{r['caveat']}_")
        elif name == "police_fraud_series":
            last, peak = r["latest"], r["peak"]
            parts.append(L(
                f"**German police-recorded insurance fraud (PKS 517400)**: {n(last['recorded_offences'])} cases in "
                f"{int(last['year'])}; peak {n(peak['recorded_offences'])} in {int(peak['year'])}.",
                f"**Polizeilich erfasster Versicherungsbetrug in Deutschland (PKS 517400)**: {n(last['recorded_offences'])} Fälle "
                f"{int(last['year'])}; Höchststand {n(peak['recorded_offences'])} im Jahr {int(peak['year'])}.",
            ))
            parts.append(L(
                "Police figures capture only reported crime — far below the ~10% of claims insurers consider suspicious (GDV).",
                "Die Polizeizahlen erfassen nur angezeigte Taten — weit unter den etwa 10 % der Schäden, die Versicherer als verdächtig einstufen (GDV).",
            ))
        elif name in ("score_claim", "claim_lookup"):
            res = r["result"]
            title = r["claim"].get("claim_id", "Claim")
            parts.append(L(
                f"**{title}**: score **{res['score']}** → **{res['band'].upper()}** — {res['route']}",
                f"**{title}**: Punktzahl **{res['score']}** → **{res['band'].upper()}** — {res['route']}",
            ))
            for f_ in res["fired"]:
                parts.append(f"- {f_['rule_id']} {f_['label']} (+{f_['points']}, {f_['basis']})")
            if not res["fired"]:
                parts.append(L("- No red flag fired.", "- Keine Warnregel ausgelöst."))
            a = res["anomaly"]
            parts.append(L(
                f"- Anomaly score {a['anomaly_score']:.2f} (second look at ≥ {a['threshold']:.2f})",
                f"- Anomaliewert {a['anomaly_score']:.2f} (zweite Prüfung ab {a['threshold']:.2f})",
            ))
            if name == "claim_lookup":
                parts.append(L("_This is a SIMULATED claim._", "_Das ist ein SIMULIERTER Schaden._"))
        elif name == "triage_queue":
            c = r["counts"]
            parts.append(L(
                f"**{r['band'].title()} queue** (SIMULATED inbox: {c.get('red', 0)} red, {c.get('amber', 0)} amber, {c.get('green', 0)} green)",
                f"**Warteschlange {r['band']}** (SIMULIERTER Eingang: {c.get('red', 0)} rot, {c.get('amber', 0)} gelb, {c.get('green', 0)} grün)",
            ))
            for row in r["rows"]:
                parts.append(L(
                    f"- {row['claim_id']} · {row['geo_name']} · €{n(row['claimed_amount_eur'])} · score {row['score']} — {row['reason_summary']}",
                    f"- {row['claim_id']} · {row['geo_name']} · {n(row['claimed_amount_eur'])} € · Punktzahl {row['score']} — {row['reason_summary']}",
                ))
        elif name == "model_info":
            parts.append(L(
                "**Regionalklasse models** (spatial cross-validation by Bundesland)",
                "**Regionalklassen-Modelle** (räumliche Kreuzvalidierung nach Bundesland)",
            ))
            for t in r["targets"].values():
                sp, rd, b = t["spatial_cv"], t["random_cv"], t["baseline"]
                parts.append(f"- {t['label']}: {t['best_model']}, MAE {sp['mae']:.2f} (random split {rd['mae']:.2f}, baseline {b['mae']:.2f}), "
                             f"within ±1 class {sp['within_one_class']:.0%}. Drivers: {', '.join(t['top_drivers'][:3])}")
            parts.append(L(
                f"- Drift status (KBA 2026 vs 2025 fleet): **{r['drift_status']}**",
                f"- Driftstatus (KBA-Bestand 2026 gegen 2025): **{r['drift_status']}**",
            ))
        elif name == "priced_gaps":
            word = "higher" if r["direction"] == "above" else "lower"
            word_de = "höher" if r["direction"] == "above" else "niedriger"
            parts.append(L(
                f"**Districts where the GDV {r['label']} class is {word} than public data predicts**",
                f"**Kreise, in denen die GDV-Klasse {r['label']} {word_de} liegt, als öffentliche Daten erwarten**",
            ))
            for row in r["rows"]:
                parts.append(f"- {row['geo_name']} ({row['bundesland']}): GDV {n(row[r['target']])}, "
                             f"predicted {row['pred_' + r['target']]:.1f} ({row['resid_' + r['target']]:+.1f})")
            parts.append(f"_{r['meaning']}_")
        elif name == "search_documents":
            hits = r["hits"][:3]
            if hits and len(results) == 1:
                parts.append(L("**From the documents:**", "**Aus den Dokumenten:**"))
                for h in hits:
                    text = re.sub(r"\s+", " ", h["text"]).strip()
                    parts.append(f"> {text[:420]}{'…' if len(text) > 420 else ''}\n> — *{h['source']}, {h['locator']}*")
            elif hits:
                text = re.sub(r"\s+", " ", re.sub(r"^#+ .*?\n", "", hits[0]["text"])).strip()
                parts.append(f"\n> {text[:300]}{'…' if len(text) > 300 else ''}\n> — *{hits[0]['source']}, {hits[0]['locator']}*")
            elif len(results) == 1:
                parts.append(L(
                    "I found nothing in the data or documents for that. Try a district, a country, a claim id (SIM-0042) or a topic like Regionalklasse, fraud, drift.",
                    "Dazu steht nichts in den Daten oder Dokumenten. Versuchen Sie einen Kreis, ein Land, eine Schadennummer (SIM-0042) oder ein Thema wie Regionalklasse, Betrug, Drift.",
                ))
    return "\n".join(parts)


def run_offline(question: str, lang: str = "en") -> Iterator[dict]:
    steps = plan(question)
    names = " → ".join(s[0] for s in steps)
    yield {"type": "plan", "text": (f"Offline-Planer: {names}" if lang == "de" else f"Offline planner: {names}")}
    results = []
    for name, args in steps:
        yield {"type": "tool", "name": name, "args": args}
        result = tools.call(name, args)
        results.append((name, result))
        yield {"type": "observation", "name": name, "summary": _summary(result, lang)}
    yield {"type": "answer", "text": compose(question, results, lang), "sources": _sources(results), "mode": "offline"}


def run(question: str, history: list[dict] | None = None, lang: str = "en") -> Iterator[dict]:
    lang = "de" if lang == "de" else "en"
    if llm.configured():
        try:
            yield from run_llm(question, history or [], lang)
            return
        except Exception as exc:
            note = (f"Sprachmodell nicht erreichbar ({type(exc).__name__}); Wechsel zum Offline-Planer."
                    if lang == "de" else f"LLM unavailable ({type(exc).__name__}); switching to the offline planner.")
            yield {"type": "plan", "text": note}
    yield from run_offline(question, lang)


def investigator_brief(claim_id: str, lang: str = "en") -> dict:
    """Short case note for a claim in the SIMULATED inbox."""
    r = tools.claim_lookup(claim_id)
    if "error" in r:
        return r
    return brief_for(r["claim"], r["result"], simulated=True, lang=lang)


RULE_DE = {
    "Claim soon after the policy started": "Schaden kurz nach Versicherungsbeginn",
    "Claim just before the policy expires": "Schaden kurz vor Vertragsende",
    "Late notification (>30 days)": "Späte Meldung (über 30 Tage)",
    "Repeat claimant (2+ claims in 12 months)": "Wiederholung (2 oder mehr Schäden in 12 Monaten)",
    "Description does not match the damage": "Schilderung passt nicht zum Schadenbild",
    "Amount higher than the repair estimate": "Betrag höher als der Reparaturvoranschlag",
    "Receipt or photo looks manipulated": "Beleg oder Foto wirkt manipuliert",
    "Serious claim and no police report": "Schwerer Schaden ohne Polizeimeldung",
    "Injury claim with no witness": "Personenschaden ohne Zeugen",
    "Vehicle older than 15 years": "Fahrzeug älter als 15 Jahre",
}


def brief_for(c: dict, res: dict | None = None, simulated: bool = False, lang: str = "en") -> dict:
    """Short case note for the investigator queue (used by the UI and n8n)."""
    res = res or store.score(c)
    de = lang == "de"
    flags = "; ".join(
        f"{f['rule_id']} {RULE_DE.get(f['label'], f['label']) if de else f['label']}" for f in res["fired"]
    ) or ("keine" if de else "none")
    where = f" in {c['geo_name']} ({c['bundesland']})" if c.get("geo_name") else ""
    district = store.find_district(c["geo_code"]) if c.get("geo_code") else None
    if district is not None and not where:
        where = f" in {district.geo_name} ({district.bundesland})"
    claimed = float(c.get("claimed_amount_eur", 0))
    repair = float(c.get("repair_estimate_eur", 0))
    anomaly = res["anomaly"]["anomaly_score"]
    if de:
        label = "SIMULIERTER Schaden" if simulated else "Schaden"
        an_txt = f"{anomaly:.2f}".replace(".", ",")
        text = (f"{label} {c.get('claim_id') or '(neu)'}{where}. Gefordert {_fmt(claimed, lang='de')} € "
                f"gegen Reparaturschätzung {_fmt(repair, lang='de')} €. Punktzahl {res['score']} → {res['band'].upper()}. "
                f"Warnregeln: {flags}. Anomaliewert {an_txt}. "
                f"Nächste Schritte: Unfallschilderung mit den Schadenfotos abgleichen, fehlenden Polizeibericht anfordern, "
                f"Vorschäden im HIS (Hinweis- und Informationssystem) prüfen. Eine rote Einstufung ist ein Grund zur Prüfung, kein Betrugsnachweis.")
    else:
        label = "SIMULATED claim" if simulated else "Claim"
        text = (f"{label} {c.get('claim_id') or '(new)'}{where}. Claimed €{claimed:,.0f} "
                f"vs repair estimate €{repair:,.0f}. Score {res['score']} → {res['band'].upper()}. "
                f"Red flags: {flags}. Anomaly score {anomaly:.2f}. "
                f"Next steps: verify the accident story against the damage photos, request the police report if missing, "
                f"check prior claims in HIS (Hinweis- und Informationssystem). A red band is a reason to investigate, not a finding of fraud.")
    if llm.configured():
        try:
            ask = ("Formuliere eine knappe Notiz in vier Zeilen auf Deutsch und behalte alle Fakten:\n" if de
                   else "Rewrite as a crisp 4-line investigator note, keep all facts:\n")
            msg = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": ask + text}])
            text = msg.get("content") or text
        except Exception:
            pass
    return {"claim_id": c.get("claim_id"), "band": res["band"], "score": res["score"], "route": res["route"], "brief": text}
