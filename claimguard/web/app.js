/* ClaimGuard frontend. Plain JavaScript and ECharts: no framework, no build step, no third-party requests. */
(() => {
  "use strict";

  // ------------------------------------------------------------------ helpers
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const cache = new Map();
  const api = async (path, opts) => {
    if (!opts && cache.has(path)) return cache.get(path);
    const res = await fetch(path, opts);
    if (!res.ok) throw new Error(`${path} returned ${res.status}`);
    const data = await res.json();
    if (!opts) cache.set(path, data);
    return data;
  };
  const postJson = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const i18n = window.CG_I18N;
  const t = (s, vars) => i18n.t(s, vars);
  const getLang = () => i18n.lang;
  const loc = () => (getLang() === "de" ? "de-DE" : "en-US");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const nf = (v, d = 0) => (v == null || Number.isNaN(v) ? "–" : Number(v).toLocaleString(loc(), { maximumFractionDigits: d, minimumFractionDigits: d }));
  const pct = (v, d = 1) => {
    if (v == null || Number.isNaN(v)) return "–";
    const n = (v * 100).toLocaleString(loc(), { maximumFractionDigits: d, minimumFractionDigits: d });
    return getLang() === "de" ? `${n} %` : `${n}%`;
  };
  const signed = (v, d = 1) => {
    if (v == null || Number.isNaN(v)) return "–";
    const r = Number(Number(v).toFixed(d));
    return `${r > 0 ? "+" : r < 0 ? "−" : ""}${nf(Math.abs(r), d)}`;
  };
  const compact = (v) => {
    if (v == null) return "–";
    const unit = getLang() === "de" ? ["Mrd.", "Mio.", "Tsd."] : ["bn", "M", "k"];
    const n = (x) => (x).toLocaleString(loc(), { maximumFractionDigits: 1, minimumFractionDigits: 1 });
    if (v >= 1e9) return `${n(v / 1e9)} ${unit[0]}`;
    if (v >= 1e6) return `${n(v / 1e6)} ${unit[1]}`;
    if (v >= 1e4) return `${n(v / 1e3)} ${unit[2]}`;
    return nf(v);
  };
  const cap = (s) => String(s || "").charAt(0).toUpperCase() + String(s || "").slice(1);
  const words = (s) => cap(String(s || "").replaceAll("_", " "));
  const fold = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ß/g, "ss");
  const shortName = (n) => String(n || "").split(",")[0];
  const jitter = (code) => ((parseInt(code, 10) * 9301 + 49297) % 233280) / 233280 - 0.5;
  const download = (name, href) => { const a = document.createElement("a"); a.href = href; a.download = name; document.body.appendChild(a); a.click(); a.remove(); };
  let regionNames = null;
  const ISO_FIX = { EL: "GR", UK: "GB" };
  const countryName = (code, fallback) => {
    if (code === "XK") return "Kosovo";
    if (!regionNames && typeof Intl !== "undefined" && Intl.DisplayNames) regionNames = new Intl.DisplayNames([getLang() === "de" ? "de" : "en"], { type: "region" });
    try { return regionNames?.of(ISO_FIX[code] || code) || fallback || code; } catch { return fallback || code; }
  };
  function spearman(xs, ys) {
    const rank = (a) => {
      const idx = a.map((v, i) => [v, i]).sort((p, q) => p[0] - q[0]);
      const r = Array(a.length);
      for (let i = 0; i < idx.length;) {
        let j = i;
        while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
        for (let k = i; k <= j; k++) r[idx[k][1]] = (i + j) / 2 + 1;
        i = j + 1;
      }
      return r;
    };
    const rx = rank(xs), ry = rank(ys), n = xs.length;
    const mx = rx.reduce((a, b) => a + b, 0) / n, my = ry.reduce((a, b) => a + b, 0) / n;
    let num = 0, dx = 0, dy = 0;
    for (let i = 0; i < n; i++) { num += (rx[i] - mx) * (ry[i] - my); dx += (rx[i] - mx) ** 2; dy += (ry[i] - my) ** 2; }
    return num / Math.sqrt(dx * dy);
  }

  // ------------------------------------------------------------------ theme
  const RAMPS = {
    light: {
      seq: ["#fff6dc", "#fde2a0", "#fbc46a", "#f59f4b", "#e87539", "#d14a35", "#aa2743", "#77124a"],
      div: ["#2565ae", "#6fa5d8", "#c9dcee", "#f3f1ee", "#f4cdbf", "#e08a72", "#bf3b2c"],
    },
    dark: {
      seq: ["#1f2a45", "#2c4175", "#514a9c", "#84499f", "#b84f8f", "#e06472", "#f58c5a", "#fbc55f"],
      div: ["#62a8f7", "#3672ba", "#283b57", "#272c38", "#59313b", "#b8524b", "#ff8172"],
    },
  };
  let C = {};
  let RAMP = RAMPS.light.seq;
  let DIV = RAMPS.light.div;
  function readTheme() {
    const s = getComputedStyle(document.documentElement);
    const v = (n) => s.getPropertyValue(n).trim();
    const mode = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    C = {
      text: v("--text"), text2: v("--text-2"), text3: v("--text-3"), line: v("--border"), lineStrong: v("--border-strong"),
      surface: v("--surface"), surface2: v("--surface-2"), accent: v("--accent"), green: v("--green"), amber: v("--amber"), red: v("--red"),
      muted: v("--bar-muted"), nodata: v("--nodata"), blue: v("--d1"), orange: v("--d2"), teal: v("--d3"), violet: v("--d4"), magenta: v("--d5"), slate: v("--d6"),
    };
    RAMP = RAMPS[mode].seq;
    DIV = RAMPS[mode].div;
  }
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  function rampColor(t, ramp) {
    if (t == null || Number.isNaN(t)) return { bg: C.nodata, ink: C.text2 };
    const x = Math.min(1, Math.max(0, t)) * (ramp.length - 1);
    const i = Math.min(ramp.length - 2, Math.floor(x));
    const a = hex(ramp[i]), b = hex(ramp[i + 1]);
    const c = a.map((u, j) => Math.round(u + (b[j] - u) * (x - i)));
    const lum = (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255;
    return { bg: `rgb(${c.join(",")})`, ink: lum > 0.58 ? "#101828" : "#ffffff" };
  }

  // ------------------------------------------------------------------ chart kit
  // Canvas text is measured when a chart is drawn. Charts therefore use the system font until Inter has
  // loaded, then switch and repaint, so label widths are never measured with the wrong font.
  const FALLBACK_FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
  let FONT = FALLBACK_FONT;
  const ro = new ResizeObserver((entries) => entries.forEach((e) => { if (e.contentRect.width > 0) echarts.getInstanceByDom(e.target)?.resize(); }));
  const chart = (id) => {
    const node = typeof id === "string" ? document.getElementById(id) : id;
    let c = echarts.getInstanceByDom(node);
    if (!c) { c = echarts.init(node, null, { renderer: "canvas" }); ro.observe(node); }
    return c;
  };
  const base = (extra = {}) => ({
    backgroundColor: "transparent",
    textStyle: { fontFamily: FONT, color: C.text },
    animationDuration: 350, animationDurationUpdate: 250, animationEasing: "cubicOut",
    ...extra,
    tooltip: {
      backgroundColor: C.surface, borderColor: C.lineStrong, borderWidth: 1, padding: [8, 11], confine: true,
      textStyle: { color: C.text, fontSize: 12, fontFamily: FONT },
      extraCssText: "border-radius:8px;box-shadow:0 10px 28px rgba(0,0,0,.16);line-height:1.5;",
      ...(extra.tooltip || {}),
    },
  });
  const ax = (type, extra = {}) => {
    const cat = type === "category";
    const { axisLabel, ...rest } = extra;
    return {
      type, axisLine: { show: cat, lineStyle: { color: C.lineStrong } }, axisTick: { show: false },
      axisLabel: { color: cat ? C.text2 : C.text3, fontSize: 11, ...axisLabel },
      splitLine: { show: !cat, lineStyle: { color: C.line } }, nameTextStyle: { color: C.text3, fontSize: 11 }, ...rest,
    };
  };
  const yCat = (data, extra = {}) => ax("category", { data, axisLine: { show: false }, axisLabel: { color: C.text, fontSize: 12 }, ...extra });
  const yName = (name) => ({ name, nameGap: 12, nameTextStyle: { color: C.text3, fontSize: 11, align: "left" } });
  const grid = (extra = {}) => ({ left: 4, right: 18, top: 10, bottom: 4, containLabel: true, ...extra });
  const legend = (extra = {}) => ({ top: 0, left: 0, icon: "circle", itemWidth: 8, itemHeight: 8, itemGap: 16, textStyle: { color: C.text2, fontSize: 12 }, ...extra });
  const shadowTip = (extra = {}) => ({ trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: C.line, opacity: 0.45 } }, ...extra });
  const lineTip = (extra = {}) => ({ trigger: "axis", axisPointer: { type: "line", lineStyle: { color: C.lineStrong } }, ...extra });
  const barLabel = (fmt) => ({ show: true, position: "right", color: C.text2, fontSize: 11, formatter: (p) => fmt(p.value) });
  const dim = (s) => `<span style="color:${C.text2}">${s}</span>`;

  // ------------------------------------------------------------------ districts and map
  let districtIndex = {};
  let districtRows = [];
  let districtsReady = null;
  let geoReady = null;
  const loadDistricts = () => (districtsReady ??= api("/api/districts").then((rows) => {
    districtRows = rows;
    rows.forEach((r) => { districtIndex[r.geo_code] = r; });
    return rows;
  }));
  const loadGeo = () => (geoReady ??= (async () => {
    const [geo] = await Promise.all([api("/api/geo/districts"), loadDistricts()]);
    geo.features.forEach((f) => { f.properties.name = f.properties.code; });
    echarts.registerMap("DE", geo);
    const centroids = {};
    geo.features.forEach((f) => {
      const polys = f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates;
      const ring = polys.reduce((a, p) => (p[0].length > a.length ? p[0] : a), []);
      centroids[f.properties.code] = [ring.reduce((s, p) => s + p[0], 0) / ring.length, ring.reduce((s, p) => s + p[1], 0) / ring.length];
    });
    return { centroids };
  })());

  const MAP_METRICS = {
    liability_class_2027: { chip: "Haftpflicht", head: "Kfz-Haftpflicht Regionalklasse 2027", sub: "Class 1 is the cheapest, 12 the most expensive.", min: 1, max: 12, fmt: (v) => nf(v), na: "no single class published" },
    comprehensive_class_2027: { chip: "Vollkasko", head: "Vollkasko Regionalklasse 2027", sub: "Class 1 is the cheapest, 9 the most expensive.", min: 1, max: 9, fmt: (v) => nf(v), na: "no single class published" },
    partial_cover_class_2027: { chip: "Teilkasko", head: "Teilkasko Regionalklasse 2027", sub: "Class 1 is the cheapest, 16 the most expensive.", min: 1, max: 16, fmt: (v) => nf(v), na: "no single class published" },
    accidents_per_1000_cars: { chip: "Accidents per car", head: "Injury accidents per 1,000 cars", sub: "Yearly average 2020 to 2025 against the KBA 2025 car stock.", min: 2.5, max: 8, fmt: (v) => nf(v, 1) },
    share_killed_or_serious: { chip: "Severity", head: "Severity of injury accidents", sub: "Share of injury accidents with someone killed or seriously injured, 2020 to 2025.", min: 0.1, max: 0.3, fmt: (v) => pct(v) },
    population_per_km2: { chip: "Density", head: "Population density", sub: "People per km², 2024. Logarithmic colour scale.", min: 1.6, max: 3.5, fmt: (v) => nf(v), log: true, text: ["dense", "sparse"] },
    share_bev: { chip: "Electric share", head: "Battery-electric share of passenger cars", sub: "KBA vehicle stock, 1 January 2025.", min: 0.015, max: 0.06, fmt: (v) => pct(v) },
    resid_liability_class_2027: { chip: "Model gap", head: "Where GDV and the model disagree", sub: "GDV Haftpflicht class minus the model's prediction. Warm colours: GDV is higher than public data suggests.", min: -4, max: 4, fmt: (v) => signed(v, 1), diverging: true, text: ["GDV higher", "GDV lower"], na: "not modelled" },
  };

  function metricSpec(key, select = false) {
    const m = MAP_METRICS[key];
    return {
      select, min: m.min, max: m.max, colors: m.diverging ? DIV : RAMP, text: (m.text || ["high", "low"]).map((x) => t(x)),
      legendFmt: (v) => (m.log ? nf(10 ** v) : m.fmt(v)),
      data: districtRows.map((r) => { const raw = r[key]; return { name: r.geo_code, value: raw == null ? null : m.log ? Math.log10(raw) : raw, raw }; }),
      tip: (code, d) => {
        const r = districtIndex[code];
        if (!r) return "";
        const kind = r.area_type === "urban" || r.area_type === "rural" ? t(r.area_type) : r.area_type;
        return `<b>${esc(r.geo_name)}</b><br/>${dim(`${esc(r.bundesland)} · ${esc(kind)}`)}<br/>${esc(t(m.chip))}: <b>${d?.raw == null ? esc(t(m.na || "no data")) : m.fmt(d.raw)}</b>`;
      },
    };
  }

  function drawMap(c, spec, keepView = true) {
    const prev = keepView ? c.getOption()?.series?.[0] : null;
    const zoom = prev?.zoom || 1;
    c.__spec = spec;
    const fillOf = (v) => (v == null || Number.isNaN(v) ? C.nodata : rampColor((v - spec.min) / (spec.max - spec.min), spec.colors).bg);
    c.setOption(base({
      tooltip: { trigger: "item", formatter: (p) => spec.tip(p.name, p.data) },
      visualMap: {
        type: "continuous", min: spec.min, max: spec.max, calculable: true, orient: "horizontal", left: 0, bottom: 0, itemWidth: 9, itemHeight: 150,
        text: spec.text, textStyle: { color: C.text3, fontSize: 11 }, inRange: { color: spec.colors }, outOfRange: { color: C.nodata },
        formatter: spec.legendFmt, handleStyle: { color: C.surface, borderColor: C.lineStrong }, indicatorStyle: { borderColor: C.text },
      },
      series: [{
        type: "map", map: "DE", roam: zoom > 1 ? "move" : false, zoom, center: prev?.center, aspectScale: 0.64, layoutCenter: ["50%", "47%"], layoutSize: "95%",
        selectedMode: spec.select ? "single" : false,
        itemStyle: { borderColor: C.surface, borderWidth: 0.5, areaColor: C.nodata },
        emphasis: { label: { show: false }, itemStyle: { borderColor: C.text, borderWidth: 1.2 } },
        select: { label: { show: false }, itemStyle: { borderColor: C.text, borderWidth: 2 } },
        data: spec.data.map((d) => { const fill = fillOf(d.value); return { ...d, emphasis: { itemStyle: { areaColor: fill } }, select: { itemStyle: { areaColor: fill } } }; }),
      }],
    }), true);
    if (c.__selected) c.dispatchAction({ type: "select", seriesIndex: 0, name: c.__selected });
  }

  function seg(container, items, current, onPick) {
    container.innerHTML = items.map(([k, l]) => `<button type="button" class="seg-b" data-k="${esc(k)}" aria-pressed="${k === current}">${esc(l)}</button>`).join("");
    container.onclick = (e) => {
      const b = e.target.closest(".seg-b");
      if (!b) return;
      $$(".seg-b", container).forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      onPick(b.dataset.k);
    };
  }

  // ------------------------------------------------------------------ router
  const inits = {};
  const painters = {};
  const arrive = {};
  const ready = {};
  const done = new Set();
  let current = null;
  let pendingQuestion = null;

  function go(view, arg) {
    const h = `#${arg ? `${view}/${arg}` : view}`;
    if (location.hash === h) route(); else location.hash = h;
  }
  function route() {
    const [view, arg] = decodeURIComponent(location.hash.slice(1)).split("/");
    show(view || "overview", arg);
  }
  function show(view, arg) {
    if (!document.getElementById(`view-${view}`)) view = "overview";
    const el = document.getElementById(`view-${view}`);
    $$(".view").forEach((v) => v.classList.toggle("active", v === el));
    $$(".nav a").forEach((a) => {
      const on = a.dataset.nav === view;
      a.classList.toggle("active", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    $("#crumb").textContent = t(el.dataset.title);
    document.title = `${t(el.dataset.title)} · ClaimGuard`;
    $("#app").classList.remove("nav-open");
    if (current !== view) window.scrollTo(0, 0);
    current = view;
    ready[view] ??= Promise.resolve().then(() => inits[view]?.()).then(() => { done.add(view); }).catch((err) => {
      console.error(view, err);
      el.insertAdjacentHTML("afterbegin", `<div class="error-box">${t("This view could not be loaded: {msg}. Check that the API is running, then reload.", { msg: esc(err.message) })}</div>`);
    });
    ready[view].then(() => { if (current === view && done.has(view)) arrive[view]?.(arg); });
  }
  function repaint() {
    readTheme();
    done.forEach((v) => painters[v]?.());
  }
  function askAgent(q) {
    if (!q) return;
    if (current === "agent") { ask(q); return; }
    pendingQuestion = q;
    go("agent");
  }

  // ------------------------------------------------------------------ overview
  const TAB_LABEL = { germany: "Germany", europe: "Europe", fraud: "Fraud", ml: "Models", triage: "Triage" };
  const texts = {};

  inits.overview = async () => {
    const [ov, insights, trends, police] = await Promise.all([api("/api/overview"), api("/api/insights"), api("/api/germany/trends"), api("/api/fraud/police")]);
    const t0 = trends.find((t) => t.year === 2020);
    const t1 = trends.find((t) => t.year === ov.accidents_year);
    const accChange = t0 && t1 ? t1.accidents_with_injury / t0.accidents_with_injury - 1 : null;
    const peak = police.rows.reduce((a, r) => (r.recorded_offences > a.recorded_offences ? r : a), police.rows[0]);
    const fraudChange = ov.police_insurance_fraud_cases / peak.recorded_offences - 1;
    const arrow = (x) => (x > 0 ? "↑" : "↓");
    const paintKpis = () => {
      const rows = [
        [t("Population"), compact(ov.population_2024), t("{n} districts · Destatis 2024", { n: nf(ov.districts) })],
        [t("Passenger cars"), compact(ov.passenger_cars_2026), t("KBA, 1 January 2026")],
        [t("Injury accidents, {year}", { year: ov.accidents_year }), nf(ov.accidents_with_injury_latest), accChange == null ? t("Unfallatlas") : t("{arrow} since 2020 · Unfallatlas", { arrow: `<b>${arrow(accChange)} ${pct(Math.abs(accChange))}</b>` })],
        [t("Road deaths per 100,000"), nf(ov.germany_road_deaths_per_100k_2024, 2), t("Germany, 2024 · Eurostat")],
        [t("Suspicious claims"), `~${nf(ov.gdv_suspicious_share_pct)}%`, t("more than €{n} bn lost a year · GDV estimate", { n: nf(ov.gdv_fraud_loss_bn_eur) })],
        [t("Police fraud cases, {year}", { year: ov.police_year }), nf(ov.police_insurance_fraud_cases), t("{arrow} from the {year} peak · BKA", { arrow: `<b>${arrow(fraudChange)} ${pct(Math.abs(fraudChange), 0)}</b>`, year: peak.year })],
      ];
      $("#kpis").innerHTML = rows.map(([l, v, n]) => `<div class="kpi"><div class="kpi-l">${esc(l)}</div><div class="kpi-v">${esc(v)}</div><div class="kpi-n">${n}</div></div>`).join("");
    };
    const tabs = [...new Set(insights.map((i) => i.tab))];
    const renderFindings = (tab) => {
      $("#insights").innerHTML = insights.map((i, n) => ({ i, n })).filter(({ i }) => tab === "all" || i.tab === tab).map(({ i, n }) => `
        <a class="finding" href="#${esc(i.tab)}">
          <div class="f-top"><span>${esc(t(TAB_LABEL[i.tab] || i.tab))}</span><span>${String(n + 1).padStart(2, "0")}</span></div>
          <div class="f-v">${esc(i18n.insight(i, "value"))}</div><h4>${esc(i18n.insight(i, "title"))}</h4><p>${esc(i18n.insight(i, "text"))}</p>
          <div class="f-more">${esc(t("Open {tab}", { tab: t(TAB_LABEL[i.tab] || i.tab) }))}</div>
        </a>`).join("");
    };
    seg($("#ins-filter"), [["all", "All {n}"], ...tabs.map((tab) => [tab, TAB_LABEL[tab] || tab])], "all", renderFindings);
    const examples = ["Top 10 most expensive rural districts in Bayern", "How does Germany compare in Europe on road deaths?", "Which districts are priced higher than the model predicts?"];
    const paintExamples = () => {
      $("#ov-ask-examples").innerHTML = `<span>${esc(t("Try"))}</span>${examples.map((q) => `<button type="button" data-q="${esc(q)}">${esc(t(q))}</button>`).join("")}`;
    };
    $("#ov-ask-examples").onclick = (e) => { const b = e.target.closest("button"); if (b) askAgent(getLang() === "de" ? b.textContent : b.dataset.q); };
    $("#ov-ask").onsubmit = (e) => { e.preventDefault(); const input = $("input", e.target); askAgent(input.value.trim() || input.placeholder); };
    const paintOverviewText = () => {
      paintKpis();
      $$("#ins-filter .seg-b").forEach((b) => { b.textContent = b.dataset.k === "all" ? t("All {n}", { n: insights.length }) : t(TAB_LABEL[b.dataset.k] || b.dataset.k); });
      renderFindings($("#ins-filter .seg-b[aria-pressed='true']")?.dataset.k || "all");
      paintExamples();
      $$("#ov-metrics .seg-b").forEach((b) => { b.textContent = t(MAP_METRICS[b.dataset.k].chip); });
      $("#ov-hist-sub").textContent = t("{n} districts with one class. Median class: urban {u}, rural {r}.", { n: classed.length, u: nf(median("urban")), r: nf(median("rural")) });
      $("#ov-top12").innerHTML = `<span>${esc(t("Class 12"))}</span>${top.map((r) => `<a href="#germany/${r.geo_code}">${esc(shortName(r.geo_name))}</a>`).join("")}`;
    };

    await loadGeo();
    let metric = "liability_class_2027";
    const map = chart("ov-map");
    const paintMap = () => { const m = MAP_METRICS[metric]; $("#ov-map-sub").textContent = `${t(m.head)}. ${t(m.sub)}`; drawMap(map, metricSpec(metric)); };
    seg($("#ov-metrics"), ["liability_class_2027", "comprehensive_class_2027", "partial_cover_class_2027", "accidents_per_1000_cars", "population_per_km2", "share_bev"].map((k) => [k, MAP_METRICS[k].chip]), metric, (k) => { metric = k; paintMap(); });
    map.on("click", (p) => { if (districtIndex[p.name]) go("germany", p.name); });

    const classed = districtRows.filter((r) => r.liability_class_2027 != null);
    const classes = Array.from({ length: 12 }, (_, i) => i + 1);
    const count = (type, k) => classed.filter((r) => r.area_type === type && r.liability_class_2027 === k).length;
    const median = (type) => { const a = classed.filter((r) => r.area_type === type).map((r) => r.liability_class_2027).sort((x, y) => x - y); return a.length ? a[Math.floor((a.length - 1) / 2)] : null; };
    const top = classed.filter((r) => r.liability_class_2027 === 12).sort((a, b) => b.population_2024 - a.population_2024);
    const paintHist = () => chart("ov-hist").setOption(base({
      legend: legend(), grid: grid({ top: 34, bottom: 22 }), tooltip: shadowTip({ formatter: (p) => `<b>${esc(t("Class {n}", { n: p[0].name }))}</b><br/>${p.map((s) => `${s.marker}${esc(s.seriesName)}: <b>${s.value}</b> ${esc(t("districts"))}`).join("<br/>")}` }),
      xAxis: ax("category", { data: classes.map(String), name: t("Haftpflicht class 2027"), nameLocation: "middle", nameGap: 26 }),
      yAxis: ax("value", { minInterval: 1 }),
      series: [
        { name: t("Rural"), type: "bar", stack: "a", barWidth: "62%", color: C.teal, data: classes.map((k) => count("rural", k)) },
        { name: t("Urban"), type: "bar", stack: "a", color: C.magenta, itemStyle: { borderRadius: [2, 2, 0, 0] }, data: classes.map((k) => count("urban", k)) },
      ],
    }), true);

    texts.overview = paintOverviewText;
    painters.overview = () => { paintMap(); paintHist(); };
    paintOverviewText();
    painters.overview();
  };

  // ------------------------------------------------------------------ germany
  let deMap = null;
  let deMetric = "liability_class_2027";
  let currentDistrict = null;

  const TABLE_COLS = [
    { k: "geo_name", l: "District", text: true },
    { k: "area_type", l: "Type", text: true },
    { k: "population_2024", l: "Population", f: (v) => nf(v) },
    { k: "population_per_km2", l: "Per km²", f: (v) => nf(v) },
    { k: "liability_class_2027", l: "Haftpflicht", heat: 12 },
    { k: "comprehensive_class_2027", l: "Vollkasko", heat: 9 },
    { k: "partial_cover_class_2027", l: "Teilkasko", heat: 16 },
    { k: "pred_liability_class_2027", l: "Model", f: (v) => nf(v, 1) },
    { k: "resid_liability_class_2027", l: "Gap", gap: true },
    { k: "accidents_per_1000_cars", l: "Accidents / 1k cars", f: (v) => nf(v, 1) },
    { k: "share_killed_or_serious", l: "Severe", f: (v) => pct(v) },
    { k: "share_bev", l: "Electric", f: (v) => pct(v) },
  ];

  inits.germany = async () => {
    await loadGeo();
    deMap = chart("de-map");
    const paintMap = () => { const m = MAP_METRICS[deMetric]; $("#de-map-title").textContent = t(m.head); $("#de-map-sub").textContent = t(m.sub); drawMap(deMap, metricSpec(deMetric, true)); };
    seg($("#de-metrics"), Object.keys(MAP_METRICS).map((k) => [k, MAP_METRICS[k].chip]), deMetric, (k) => { deMetric = k; paintMap(); });
    deMap.on("click", (p) => { if (districtIndex[p.name]) openDistrict(p.name); });

    $("#districts").innerHTML = [...districtRows].sort((a, b) => a.geo_name.localeCompare(b.geo_name, "de")).map((r) => `<option value="${esc(r.geo_name)}"></option>`).join("");
    const search = $("#de-search");
    const findDistrict = () => {
      const q = fold(search.value.trim());
      if (!q) return;
      const hit = districtRows.find((r) => fold(r.geo_name) === q) || districtIndex[q.padStart(5, "0")] ||
        districtRows.filter((r) => fold(r.geo_name).includes(q)).sort((a, b) => (fold(b.geo_name).startsWith(q) - fold(a.geo_name).startsWith(q)) || b.population_2024 - a.population_2024)[0];
      if (hit) { openDistrict(hit.geo_code); search.value = ""; } else toast(t("No district found"), t("Nothing matches “{q}”.", { q: search.value.trim() }), "info");
    };
    search.onchange = findDistrict;
    search.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); findDistrict(); } };

    const [scatter, states, profiles, trends] = await Promise.all([api("/api/germany/scatter"), api("/api/states"), api("/api/germany/profiles"), api("/api/germany/trends")]);
    const st = [...states].sort((a, b) => a.liability_class_car_weighted - b.liability_class_car_weighted);
    const hours = Array.from({ length: 24 }, (_, h) => `hour_${String(h).padStart(2, "0")}`);
    const hp = profiles.accidents_by_hour;
    const paintCharts = () => {
      const groups = { urban: C.magenta, rural: C.teal };
      chart("de-scatter").setOption(base({
        legend: legend({ left: "auto", right: 0 }), grid: grid({ top: 34, bottom: 24 }),
        tooltip: { formatter: (p) => `<b>${esc(p.data.n)}</b><br/>${nf(p.data.value[0])} ${esc(t("people per km²"))}<br/>${esc(t("Haftpflicht class 2027"))} <b>${p.data.c}</b>` },
        xAxis: ax("log", { name: t("People per km² (log scale)"), nameLocation: "middle", nameGap: 28, min: 30, max: 6000 }),
        yAxis: ax("value", { ...yName(t("Haftpflicht class 2027")), min: 0, max: 13, interval: 2 }),
        series: Object.entries(groups).map(([g, color]) => ({
          name: t(cap(g)), type: "scatter", color,
          data: scatter.filter((r) => r.area_type === g).map((r) => ({ value: [r.population_per_km2, r.liability_class_2027 + jitter(r.geo_code) * 0.5], n: r.geo_name, c: r.liability_class_2027, code: r.geo_code, s: Math.sqrt(r.population_2024) / 55 })),
          symbolSize: (v, p) => Math.max(5, p.data.s), itemStyle: { opacity: 0.6, borderColor: C.surface, borderWidth: 0.6 },
          emphasis: { itemStyle: { opacity: 1, borderColor: C.text, borderWidth: 1 } },
        })),
      }), true);
      chart("de-states").setOption(base({
        legend: legend(), grid: grid({ top: 34 }), tooltip: shadowTip({ valueFormatter: (v) => nf(v, 1) }),
        xAxis: ax("value"), yAxis: yCat(st.map((s) => s.bundesland)),
        series: [["Haftpflicht", "liability_class_car_weighted", C.blue], ["Vollkasko", "comprehensive_class_car_weighted", C.violet], ["Teilkasko", "partial_cover_class_car_weighted", C.orange]]
          .map(([name, key, color]) => ({ name, type: "bar", barWidth: 5, barGap: "25%", color, itemStyle: { borderRadius: [0, 2, 2, 0] }, data: st.map((s) => s[key]) })),
      }), true);
      chart("de-hours").setOption(base({
        legend: legend(), grid: grid({ top: 34 }), tooltip: lineTip({ valueFormatter: (v) => pct(v) }),
        xAxis: ax("category", { data: hours.map((h) => `${h.slice(5)}:00`), boundaryGap: false, axisLabel: { interval: 2 } }),
        yAxis: ax("value", { axisLabel: { formatter: (v) => pct(v, 0) } }),
        series: ["urban", "rural"].map((g) => ({ name: t(cap(g)), type: "line", smooth: 0.3, symbol: "none", color: groups[g], lineStyle: { width: 2 }, areaStyle: { opacity: 0.07 }, data: hours.map((h) => hp[g]?.[h]) })),
      }), true);
      chart("de-trend").setOption(base({
        legend: legend(), grid: grid({ top: 34, right: 8 }), tooltip: shadowTip(),
        xAxis: ax("category", { data: trends.map((t) => String(t.year)) }),
        yAxis: [ax("value", { axisLabel: { formatter: (v) => compact(v) } }), ax("value", { splitLine: { show: false }, scale: true, axisLabel: { formatter: (v) => nf(v, 0) } })],
        series: [
          { name: t("Injury accidents"), type: "bar", barWidth: "56%", color: C.blue, tooltip: { valueFormatter: (v) => nf(v) },
            data: trends.map((row) => ({ value: row.accidents_with_injury, itemStyle: { color: row.complete ? C.blue : C.muted, borderRadius: [2, 2, 0, 0] } })) },
          { name: t("Killed or seriously injured per 100 accidents"), type: "line", yAxisIndex: 1, symbolSize: 6, color: C.orange, lineStyle: { width: 2 }, tooltip: { valueFormatter: (v) => nf(v, 1) },
            data: trends.map((t) => ((t.persons_killed + t.seriously_injured) / t.accidents_with_injury) * 100) },
        ],
      }), true);
    };
    chart("de-scatter").on("click", (p) => { if (p.data?.code) openDistrict(p.data.code, true); });

    // district explorer table
    const sort = { k: "liability_class_2027", dir: -1 };
    const stateSel = $("#tb-state");
    stateSel.insertAdjacentHTML("beforeend", [...new Set(districtRows.map((r) => r.bundesland))].sort().map((s) => `<option>${esc(s)}</option>`).join(""));
    const filtered = () => {
      const q = fold($("#tb-q").value.trim()), state = stateSel.value, type = $("#tb-type").value;
      const rows = districtRows.filter((r) => (!state || r.bundesland === state) && (!type || r.area_type === type) && (!q || fold(r.geo_name).includes(q) || r.geo_code.startsWith(q)));
      const col = TABLE_COLS.find((c) => c.k === sort.k);
      return rows.sort((a, b) => {
        const x = a[sort.k], y = b[sort.k];
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        return (col.text ? String(x).localeCompare(String(y), "de") : x - y) * sort.dir;
      });
    };
    const cell = (c, r) => {
      const v = r[c.k];
      if (c.text) {
        const shown = c.k === "area_type" && (v === "urban" || v === "rural") ? t(v) : v;
        return c.k === "geo_name" ? `<td><b>${esc(v)}</b><span class="sub">${esc(r.bundesland)} · <span class="mono">${r.geo_code}</span></span></td>` : `<td>${esc(shown)}</td>`;
      }
      if (v == null) return `<td class="num">–</td>`;
      if (c.heat) { const h = rampColor((v - 1) / (c.heat - 1), RAMP); return `<td class="num"><span class="heat" style="background:${h.bg};color:${h.ink}">${nf(v)}</span></td>`; }
      if (c.gap) { const h = rampColor((v + 4) / 8, DIV); return `<td class="num"><span class="heat" style="background:${h.bg};color:${h.ink}">${signed(v, 1)}</span></td>`; }
      return `<td class="num">${c.f(v)}</td>`;
    };
    const renderTable = () => {
      const rows = filtered();
      $("#tb-count").textContent = t("{n} of {m} districts. Classes are GDV 2027.", { n: nf(rows.length), m: nf(districtRows.length) });
      $("#de-table").innerHTML = `<table><thead><tr>${TABLE_COLS.map((c) => `<th class="sortable ${c.text ? "" : "num"} ${sort.k === c.k ? "sorted" : ""}" data-k="${c.k}" aria-sort="${sort.k === c.k ? (sort.dir > 0 ? "ascending" : "descending") : "none"}">${esc(t(c.l))}<span class="arrow">${sort.k === c.k ? (sort.dir > 0 ? "↑" : "↓") : ""}</span></th>`).join("")}</tr></thead>
        <tbody>${rows.map((r) => `<tr class="clickable" data-code="${r.geo_code}">${TABLE_COLS.map((c) => cell(c, r)).join("")}</tr>`).join("") || `<tr><td colspan="${TABLE_COLS.length}"><div class="empty">${esc(t("No district matches these filters."))}</div></td></tr>`}</tbody></table>`;
    };
    $("#de-table").onclick = (e) => {
      const th = e.target.closest("th[data-k]");
      if (th) { const k = th.dataset.k; if (sort.k === k) sort.dir *= -1; else { sort.k = k; sort.dir = TABLE_COLS.find((c) => c.k === k).text ? 1 : -1; } renderTable(); return; }
      const tr = e.target.closest("tr[data-code]");
      if (tr) openDistrict(tr.dataset.code, true);
    };
    $("#tb-q").oninput = renderTable;
    stateSel.onchange = renderTable;
    $("#tb-type").onchange = renderTable;
    $("#tb-export").onclick = () => {
      const q = (v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v));
      const lines = [["geo_code", "bundesland", ...TABLE_COLS.map((c) => c.k)].join(","), ...filtered().map((r) => [r.geo_code, r.bundesland, ...TABLE_COLS.map((c) => r[c.k])].map(q).join(","))];
      download("claimguard-districts.csv", URL.createObjectURL(new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" })));
    };

    texts.germany = () => { $$("#de-metrics .seg-b").forEach((b) => { if (MAP_METRICS[b.dataset.k]) b.textContent = t(MAP_METRICS[b.dataset.k].chip); }); };
    painters.germany = () => { paintMap(); paintCharts(); renderTable(); renderDistrict(); };
    texts.germany();
    painters.germany();
  };
  arrive.germany = (arg) => {
    if (arg && districtIndex[arg]) openDistrict(arg);
    else if (!currentDistrict) openDistrict("09162", false, true);
  };

  async function openDistrict(code, scroll = false, quiet = false) {
    if (!code || !deMap) return;
    const drawer = $("#drawer");
    if (!currentDistrict) drawer.innerHTML = `<div class="empty"><span class="typing"><span></span><span></span><span></span></span></div>`;
    let r;
    try { r = await api(`/api/districts/${code}`); } catch { toast(t("District not found"), t("No data for {code}.", { code }), "info"); return; }
    currentDistrict = r;
    deMap.__selected = code;
    deMap.dispatchAction({ type: "select", seriesIndex: 0, name: code });
    if (!quiet && current === "germany") window.history.replaceState(null, "", `#germany/${code}`);
    renderDistrict();
    if (scroll) $("#de-map").closest(".card").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function renderDistrict() {
    const r = currentDistrict;
    if (!r) return;
    const d = r.district, m = r.model_explanation;
    const old = $("#drawer-chart");
    if (old) echarts.getInstanceByDom(old)?.dispose();
    const cls = (label, v, max) => `<div class="cls"><span>${label}</span><b>${v == null ? "–" : nf(v)}<small> / ${max}</small></b><div class="track"><i style="width:${v ? (v / max) * 100 : 0}%;background:${rampColor(v == null ? null : (v - 1) / (max - 1), RAMP).bg}"></i></div></div>`;
    const fact = (l, v) => `<div><dt>${l}</dt><dd>${v}</dd></div>`;
    $("#drawer").innerHTML = `
      <p class="d-meta">${esc(d.bundesland)} · ${esc(d.district_type && d.district_type !== "urban" && d.district_type !== "rural" ? d.district_type : t(d.area_type))} · AGS <span class="mono">${esc(d.geo_code)}</span></p>
      <h3 class="d-title">${esc(d.geo_name)}</h3>
      <div class="classes">${cls("Haftpflicht", d.liability_class_2027, 12)}${cls("Vollkasko", d.comprehensive_class_2027, 9)}${cls("Teilkasko", d.partial_cover_class_2027, 16)}</div>
      <dl class="facts">
        ${fact(t("Population"), nf(d.population_2024))}${fact(t("People per km²"), nf(d.population_per_km2))}
        ${fact(t("Cars per 1,000 people"), nf(d.cars_per_1000_people))}${fact(t("Injury accidents, 2025"), nf(d.accidents_2025))}
        ${fact(t("Accidents per 1,000 cars"), nf(d.accidents_per_1000_cars, 1))}${fact(t("Killed or seriously injured"), pct(d.share_killed_or_serious))}
        ${fact(t("Bicycle involved"), pct(d.share_with_bicycle))}${fact(t("Battery-electric cars"), pct(d.share_bev))}
      </dl>
      ${m ? `<div class="d-model">
        <h4>${esc(t("Why class {n}?", { n: nf(m.actual) }))} <span class="pill">${esc(t(words(m.model)))}</span></h4>
        <p>${t("The model predicts {pred} from public data, a gap of {gap}. Bars show how each feature moves the prediction compared with a district at the German median.", { pred: `<b>${nf(m.predicted, 1)}</b>`, gap: `<b>${signed(m.gap, 1)}</b>` })}</p>
        <div id="drawer-chart" class="chart" style="height:250px"></div>
      </div>` : `<div class="d-model"><p>${esc(t("GDV publishes more than one class for this district, so it is not modelled."))}</p></div>`}
      <div class="d-actions"><button class="btn" type="button" id="drawer-ask">${esc(t("Ask the agent about {name}", { name: shortName(d.geo_name) }))}</button></div>`;
    const askText = getLang() === "de" ? `Erzähl mir von ${shortName(d.geo_name)}` : `Tell me about ${shortName(d.geo_name)}`;
    $("#drawer-ask").onclick = () => askAgent(askText);
    if (!m) return;
    const drivers = [...m.drivers].slice(0, 8).reverse();
    chart("drawer-chart").setOption(base({
      grid: grid({ top: 4, right: 30 }),
      tooltip: shadowTip({ formatter: (p) => { const x = drivers[p[0].dataIndex]; return `<b>${esc(t(x.label))}</b><br/>${esc(t("District: {v}", { v: nf(x.value, 3) }))}<br/>${esc(t("German median: {v}", { v: nf(x.median, 3) }))}<br/>${esc(t("Effect on class: {v}", { v: signed(x.effect, 2) }))}`; } }),
      xAxis: ax("value"), yAxis: yCat(drivers.map((x) => t(x.label)), { axisLabel: { color: C.text, fontSize: 12, width: 150, overflow: "break", lineHeight: 14 } }),
      series: [{ type: "bar", barWidth: 10, data: drivers.map((x) => ({ value: x.effect, itemStyle: { color: x.effect > 0 ? DIV[DIV.length - 1] : DIV[0], borderRadius: 2 } })),
        label: { show: true, position: "right", color: C.text2, fontSize: 11, formatter: (p) => signed(p.value, 2) } }],
    }), true);
  }

  // ------------------------------------------------------------------ europe
  const EU_METRICS = {
    road_deaths_per_100000: { chip: "Road deaths", label: "Road deaths per 100,000 people", fmt: (v) => nf(v, 2), axis: (v) => nf(v, 0), src: "Eurostat sdg_11_40" },
    cars_per_1000: { chip: "Cars per person", label: "Passenger cars per 1,000 people", fmt: (v) => nf(v), axis: (v) => nf(v), src: "Eurostat road_eqs_carhab" },
    nonlife_claims_ratio: { chip: "Claims ratio", label: "Non-life claims ratio", fmt: (v) => pct(v), axis: (v) => pct(v, 0), src: "EIOPA solo annual statistics, all non-life business" },
    nonlife_premiums_written_eur_million: { chip: "Premiums", label: "Non-life premiums written, € million", fmt: (v) => nf(v), axis: (v) => compact(v), src: "EIOPA solo annual statistics" },
  };
  inits.europe = async () => {
    const rows = await api("/api/europe");
    let metric = "road_deaths_per_100000";
    let picked = ["DE", "FR", "IT", "SE", "NL", "PL"];
    const sel = $("#eu-year");
    const fillYears = () => {
      const ys = [...new Set(rows.filter((r) => r[metric] != null).map((r) => r.year))].sort();
      const prev = Number(sel.value);
      sel.innerHTML = ys.map((y) => `<option>${y}</option>`).join("");
      sel.value = ys.includes(prev) ? prev : ys[ys.length - 1];
    };
    const paintRank = () => {
      const m = EU_METRICS[metric];
      const year = Number(sel.value);
      const data = rows.filter((r) => r.year === year && r[metric] != null).sort((a, b) => a[metric] - b[metric]);
      const de = data.find((r) => r.geo_code === "DE");
      $("#eu-rank-title").textContent = t("{label}, {year}", { label: t(m.label), year });
      $("#eu-rank-sub").textContent = `${de ? t("Germany: {v}, rank {rank} of {n} (1 is the highest)", { v: m.fmt(de[metric]), rank: data.length - data.indexOf(de), n: data.length }) : t("No value for Germany in this year")}. ${t("Source: {src}.", { src: t(m.src) })}`;
      $("#eu-series-title").textContent = t("{label} over time", { label: t(m.label) });
      chart("eu-rank").setOption(base({
        grid: grid({ right: 56 }), tooltip: shadowTip({ valueFormatter: m.fmt }),
        xAxis: ax("value", { axisLabel: { formatter: m.axis } }),
        yAxis: yCat(data.map((r) => countryName(r.geo_code, r.country)), { axisLabel: { color: C.text2, fontSize: 12, formatter: (v) => (v === countryName("DE") ? `{de|${v}}` : v), rich: { de: { color: C.accent, fontWeight: 700 } } } }),
        series: [{ type: "bar", barWidth: "64%", label: barLabel(m.fmt), data: data.map((r) => ({ value: r[metric], itemStyle: { borderRadius: [0, 2, 2, 0], color: r.geo_code === "DE" ? C.accent : C.muted } })) }],
      }), true);
      const palette = [C.orange, C.teal, C.violet, C.magenta, C.slate, C.green, C.amber];
      chart("eu-series").setOption(base({
        legend: legend({ type: "scroll" }), grid: grid({ top: 34 }), tooltip: lineTip({ valueFormatter: m.fmt }),
        xAxis: ax("category", { boundaryGap: false }), yAxis: ax("value", { scale: true, axisLabel: { formatter: m.axis } }),
        series: picked.map((code, i) => ({
          name: countryName(code), type: "line", symbol: "circle", symbolSize: code === "DE" ? 6 : 4, showSymbol: code === "DE", z: code === "DE" ? 5 : 2,
          color: code === "DE" ? C.accent : palette[(i - 1 + palette.length) % palette.length], lineStyle: { width: code === "DE" ? 3 : 1.6 }, emphasis: { focus: "series" },
          data: rows.filter((r) => r.geo_code === code && r[metric] != null).sort((a, b) => a.year - b.year).map((r) => [String(r.year), r[metric]]),
        })),
      }), true);
    };
    const both = rows.filter((r) => r.cars_per_1000 != null && r.road_deaths_per_100000 != null);
    const bubbleYear = Math.max(...both.map((r) => r.year));
    const pts = both.filter((r) => r.year === bubbleYear);
    const rho = spearman(pts.map((r) => r.cars_per_1000), pts.map((r) => r.road_deaths_per_100000));
    const paintBubbleSub = () => { $("#eu-bubble-sub").textContent = t("Rank correlation {rho} across {n} countries in {year}. Each bubble is a country, size shows population.", { rho: signed(rho, 2), n: pts.length, year: bubbleYear }); };
    paintBubbleSub();
    const paintBubble = () => chart("eu-bubble").setOption(base({
      grid: grid({ bottom: 24, top: 28 }),
      tooltip: { formatter: (p) => `<b>${esc(p.data.n)}</b><br/>${esc(t("{cars} cars per 1,000 people", { cars: nf(p.data.value[0]) }))}<br/>${esc(t("{deaths} road deaths per 100,000", { deaths: nf(p.data.value[1], 2) }))}` },
      xAxis: ax("value", { name: t("Passenger cars per 1,000 people"), nameLocation: "middle", nameGap: 28, scale: true }),
      yAxis: ax("value", { ...yName(t("Road deaths per 100,000 people")), scale: true }),
      series: [{ type: "scatter", data: pts.map((r) => ({ value: [r.cars_per_1000, r.road_deaths_per_100000], n: countryName(r.geo_code, r.country), code: r.geo_code, pop: r.population, itemStyle: { color: r.geo_code === "DE" ? C.accent : C.muted, opacity: r.geo_code === "DE" ? 1 : 0.75 } })),
        symbolSize: (v, p) => Math.max(8, Math.sqrt((p.data.pop || 1e6) / 1e6) * 6.5),
        label: { show: true, position: "top", distance: 3, formatter: (p) => p.data.code, color: C.text2, fontSize: 10 },
        itemStyle: { borderColor: C.surface, borderWidth: 1 }, labelLayout: { hideOverlap: true } }],
    }), true);

    seg($("#eu-metrics"), Object.entries(EU_METRICS).map(([k, v]) => [k, v.chip]), metric, (k) => { metric = k; fillYears(); paintRank(); });
    texts.europe = () => { $$("#eu-metrics .seg-b").forEach((b) => { b.textContent = t(EU_METRICS[b.dataset.k].chip); }); paintBubbleSub(); };
    const countries = [...new Set(rows.filter((r) => r.road_deaths_per_100000 != null).map((r) => r.geo_code))].sort((a, b) => countryName(a).localeCompare(countryName(b)));
    const drawCountryChips = () => { $("#eu-countries").innerHTML = countries.map((c) => `<button type="button" class="chip ${c === "DE" ? "locked" : ""}" data-k="${c}" aria-pressed="${picked.includes(c)}" title="${esc(countryName(c))}">${c}</button>`).join(""); };
    $("#eu-countries").onclick = (e) => {
      const k = e.target.dataset.k;
      if (!k || k === "DE") return;
      picked = picked.includes(k) ? picked.filter((x) => x !== k) : [...picked, k];
      drawCountryChips(); paintRank();
    };
    sel.onchange = paintRank;
    fillYears(); drawCountryChips();
    painters.europe = () => { paintRank(); paintBubble(); paintBubbleSub(); };
    texts.europe();
    painters.europe();
  };

  // ------------------------------------------------------------------ fraud
  inits.fraud = async () => {
    const [land, police, rules] = await Promise.all([api("/api/fraud/landscape"), api("/api/fraud/police"), api("/api/fraud/rules")]);
    const get = (src, measure, breakdown, year) => land.find((r) => r.source_dataset === src && r.measure === measure && (!breakdown || r.breakdown === breakdown) && (!year || r.year === String(year)));
    const v = (row, f) => (row ? f(row.value) : "–");
    const latest = police.latest;
    const suspicious = () => v(get("gdv_claim_fraud", "suspicious_claims_share", "all_lines", 2024), (x) => `~${nf(x)}%`);
    const loss = () => v(get("gdv_claim_fraud", "estimated_fraud_loss", "property_and_casualty_more_than"), (x) => (getLang() === "de" ? `${nf(x)} Mrd. €` : `€${nf(x)} bn`));
    const euroM = (x) => (getLang() === "de" ? `${nf(x)} Mio. €` : `€${nf(x)} m`);
    const paintFraudText = () => {
      const cards = [
        ["DE", t("GDV estimate · 2024"), suspicious(), t("of property and casualty claims are suspicious. Loss of more than {loss} a year.", { loss: loss() })],
        ["DE", t("BKA police statistics · {year}", { year: latest.year }), nf(latest.recorded_offences), t("insurance fraud cases recorded by police, {n} cleared.", { n: nf(latest.cleared_offences) })],
        ["SE", t("Larmtjänst · 2024"), v(get("larmtjanst_fraud", "refused_claim_value", "all_lines", 2024), (x) => `${nf(x)} MSEK`), t("in claims refused after investigation. Motor: {n} MSEK.", { n: v(get("larmtjanst_fraud", "refused_claim_value", "motor", 2024), nf) })],
        ["NL", t("CBV, Verbond · 2025"), v(get("cbv_fraud", "proven_fraud_cases", null, 2025), nf), t("proven fraud cases. €{n} m in losses prevented.", { n: v(get("cbv_fraud", "fraud_loss_prevented", null, 2025), (x) => nf(x)) })],
        ["FR", t("ALFA · 2024"), v(get("alfa_fraud", "detected_fraud_value", "all_lines", 2024), (x) => (getLang() === "de" ? euroM(x) : `€${nf(x)} m`)), t("of fraud detected. €{n} m stopped before payment.", { n: v(get("alfa_fraud", "fraud_stopped_before_payment", null, 2024), nf) })],
        ["UK", t("ABI · 2024"), v(get("abi_fraud", "detected_fraud_value", "all_lines", 2024), (x) => `£${nf(x, 2)} bn`), t("of fraud detected in {n} claims. Motor share: {share}.", { n: v(get("abi_fraud", "detected_fraud_claims", "all_lines", 2024), nf), share: v(get("abi_fraud", "share_of_detected_fraud_claims", "motor", 2024), (x) => `${nf(x)}%`) })],
        ["EU", "Insurance Europe", v(get("insurance_europe_fraud", "estimated_fraud_share_of_claims_expenditure", null, 2024), (x) => `~${nf(x)}%`), t("of claims expenditure across Europe is estimated to be fraudulent.")],
      ];
      $("#fraud-cards").innerHTML = cards.map(([cc, who, big, what]) => `<div class="lens"><div class="lens-top"><span class="cc">${cc}</span>${esc(who)}</div><div class="lens-v">${esc(big)}</div><p>${esc(what)}</p></div>`).join("");
      $("#fr-steps").innerHTML = [
        [t("Claims that insurers consider suspicious"), suspicious()],
        [t("Estimated loss a year, property and casualty"), `> ${loss()}`],
        [t("Cases recorded by police, {year}", { year: latest.year }), nf(latest.recorded_offences)],
        [t("Cases cleared by police, {year}", { year: latest.year }), nf(latest.cleared_offences)],
      ].map(([label, b], i) => `<div class="step-row"><i>${i + 1}</i><span>${esc(label)}</span><b>${esc(b)}</b></div>`).join("");
      $("#fr-rules").innerHTML = `<table><thead><tr><th>${esc(t("Rule"))}</th><th>${esc(t("Indicator"))}</th><th class="num">${esc(t("Points"))}</th><th>${esc(t("Basis"))}</th></tr></thead><tbody>${rules.map((r) => `<tr><td class="mono">${esc(r.rule_id)}</td><td><b>${esc(t(r.indicator))}</b><span class="sub">${esc(t(r.applies_when))}</span></td><td class="num"><b>${esc(r.points)}</b></td><td>${esc(r.source)}</td></tr>`).join("")}</tbody></table>`;
      $("#fr-patterns").innerHTML = [...patterns].reverse().map((r) => `<div class="hbar"><span>${esc(t(PATTERN[r.breakdown] || words(r.breakdown)))}</span><div class="track"><i style="width:${Math.min(100, r.value)}%"></i></div><b>${nf(r.value)}%</b></div>`).join("");
    };

    const rows = police.rows;
    const peak = rows.reduce((a, r) => (r.recorded_offences > a.recorded_offences ? r : a), rows[0]);
    const patterns = land.filter((r) => r.measure === "pattern_share_of_problematic_claims").sort((a, b) => a.value - b.value);
    const PATTERN = { happened_but_not_as_described: "Happened, but not as described", amount_exaggerated: "Amount exaggerated", invented: "Invented" };
    const se = land.filter((r) => r.source_dataset === "larmtjanst_fraud" && r.measure === "refused_claim_value" && r.breakdown !== "all_lines");
    const years = [...new Set(se.map((r) => r.year))].sort();
    const lines = [...new Set(se.map((r) => r.breakdown))].sort((a, b) => (b === "motor") - (a === "motor"));

    texts.fraud = paintFraudText;
    paintFraudText();

    painters.fraud = () => {
      chart("fr-police").setOption(base({
        legend: legend(), grid: grid({ top: 34 }), tooltip: lineTip({ valueFormatter: (x) => nf(x) }),
        xAxis: ax("category", { data: rows.map((r) => String(r.year)), boundaryGap: false }),
        yAxis: ax("value", { axisLabel: { formatter: compact } }),
        series: [
          { name: t("Recorded cases"), type: "line", symbol: "none", z: 4, color: C.blue, lineStyle: { width: 2.5 }, areaStyle: { opacity: 0.08 }, data: rows.map((r) => r.recorded_offences),
            markPoint: { symbol: "circle", symbolSize: 8, itemStyle: { color: C.blue, borderColor: C.surface, borderWidth: 2 }, label: { position: "top", color: C.text, fontSize: 11, fontWeight: 600, formatter: () => t("Peak {year}: {n}", { year: peak.year, n: nf(peak.recorded_offences) }) }, data: [{ coord: [String(peak.year), peak.recorded_offences] }] } },
          { name: t("Cleared cases"), type: "line", symbol: "none", color: C.teal, lineStyle: { width: 1.8 }, data: rows.map((r) => r.cleared_offences) },
          { name: t("Suspects"), type: "line", symbol: "none", color: C.slate, lineStyle: { width: 1.6, type: "dashed" }, data: rows.map((r) => r.suspects) },
        ],
      }), true);
      const colors = { motor: C.blue, home_house_travel: C.teal, commercial: C.violet, personal_injury: C.orange, other: C.muted };
      chart("fr-sweden").setOption(base({
        legend: legend(), grid: grid({ top: 34 }), tooltip: shadowTip({ valueFormatter: (x) => `${nf(x)} MSEK` }),
        xAxis: ax("category", { data: years }), yAxis: ax("value"),
        series: lines.map((l) => ({ name: t(words(l)), type: "bar", stack: "s", barWidth: "52%", color: colors[l] || C.slate, data: years.map((y) => se.find((r) => r.year === y && r.breakdown === l)?.value ?? 0) })),
      }), true);
    };
    painters.fraud();
  };

  // ------------------------------------------------------------------ triage
  let stream = null;
  let trMap = null;
  const counts = { total: 0, green: 0, amber: 0, red: 0, second: 0 };
  const points = [];
  const BAND_LABEL = { green: "Green", amber: "Amber", red: "Red" };
  const secondLook = (route) => String(route || "").toLowerCase().startsWith("second look");
  const feedClaims = [];
  let lastTriage = null;

  function drawCounters() {
    $("#tr-counters").innerHTML = [
      ["total", t("Claims scored"), ""],
      ["green", t("Green, paid"), counts.second ? t("{n} sent for a second look", { n: nf(counts.second) }) : t("handled in the normal queue")],
      ["amber", t("Amber, claims handler"), t("checked before payment")],
      ["red", t("Red, investigators"), t("payment on hold")],
    ].map(([k, l, note]) => `<div class="stat"><span>${k === "total" ? "" : `<i class="dot ${k}"></i>`}${l}</span><b>${nf(counts[k])}</b><small>${note || t("since the stream started")}</small></div>`).join("");
  }
  function feedHtml(c) {
    const rules = c.fired.length ? c.fired.join(" ") : t("no rule fired");
    const look = secondLook(c.route) ? ` · ${t("second look")}` : "";
    return `<span class="stripe"></span><span><span class="t"><span class="mono">${esc(c.claim_id)}</span>${esc(c.geo_name)}</span><span class="m">€${nf(c.claimed_amount_eur)} · ${esc(rules)} · ${esc(t("anomaly {n}", { n: c.anomaly.toFixed(2) }))}${look}</span></span><span class="s">${c.score}</span>`;
  }
  function renderFeed() {
    const feed = $("#tr-feed");
    if (!feed) return;
    if (!feedClaims.length) {
      feed.innerHTML = `<div class="empty" data-i18n-html="Press &lt;b&gt;Start stream&lt;/b&gt; to replay the inbox in real time.">${t("Press <b>Start stream</b> to replay the inbox in real time.")}</div>`;
      return;
    }
    feed.innerHTML = feedClaims.slice(0, 80).map((c) => `<button type="button" class="feed-item ${c.band}" data-id="${esc(c.claim_id)}">${feedHtml(c)}</button>`).join("");
    feed.onclick = (e) => { const b = e.target.closest(".feed-item"); if (b) showClaim(b.dataset.id); };
  }
  function drawPoints() {
    const byBand = (b) => points.filter((p) => p.band === b).map((p) => ({ value: p.coord, name: p.id, n: p.name, s: p.score }));
    trMap.setOption({ series: [{ id: "green", data: byBand("green") }, { id: "amber", data: byBand("amber") }, { id: "red", data: byBand("red") }] });
  }
  inits.triage = async () => {
    const { centroids } = await loadGeo();
    drawCounters();
    trMap = chart("tr-map");
    painters.triage = () => {
      trMap.setOption(base({
        tooltip: { formatter: (p) => (p.data?.n ? `<b>${esc(p.data.name)}</b><br/>${esc(p.data.n)}<br/>${esc(t("Score"))} <b>${p.data.s}</b>` : "") },
        geo: { map: "DE", roam: false, aspectScale: 0.64, layoutCenter: ["50%", "50%"], layoutSize: "98%", silent: true, itemStyle: { areaColor: C.surface2, borderColor: C.lineStrong, borderWidth: 0.5 } },
        series: [
          { id: "green", type: "scatter", coordinateSystem: "geo", symbolSize: 5, itemStyle: { color: C.green, opacity: 0.55 }, data: [] },
          { id: "amber", type: "scatter", coordinateSystem: "geo", symbolSize: 8, itemStyle: { color: C.amber, borderColor: C.surface, borderWidth: 1 }, data: [] },
          { id: "red", type: "effectScatter", coordinateSystem: "geo", symbolSize: 10, rippleEffect: { scale: 3.2, brushType: "stroke", period: 3 }, itemStyle: { color: C.red }, data: [] },
        ],
      }), true);
      drawPoints();
    };
    painters.triage();

    const btn = $("#tr-toggle");
    const start = () => {
      stream = new EventSource(`/api/claims/stream/live?speed=${$("#tr-speed").value}`);
      btn.textContent = t("Pause stream"); btn.classList.remove("primary");
      stream.onmessage = (e) => {
        const c = JSON.parse(e.data);
        counts.total++; counts[c.band]++;
        if (c.band === "green" && secondLook(c.route)) counts.second++;
        drawCounters();
        points.push({ id: c.claim_id, band: c.band, coord: centroids[c.geo_code] || [10.4, 51.1], name: c.geo_name, score: c.score });
        if (points.length > 240) points.splice(points.findIndex((p) => p.band === "green") >= 0 ? points.findIndex((p) => p.band === "green") : 0, 1);
        drawPoints();
        feedClaims.unshift(c);
        if (feedClaims.length > 80) feedClaims.pop();
        renderFeed();
        if (c.band === "red") toast(t("{id} sent to investigators", { id: c.claim_id }), t("Score {score} · {place} · €{amount}", { score: c.score, place: c.geo_name, amount: nf(c.claimed_amount_eur) }));
        const badge = $("#nav-red");
        badge.hidden = !counts.red;
        badge.textContent = t("{n} red", { n: counts.red });
      };
      stream.onerror = () => { if (stream?.readyState === 2) stop(t("Start stream")); };
    };
    const stop = (label = t("Resume stream")) => { stream?.close(); stream = null; btn.textContent = label; btn.classList.add("primary"); };
    btn.onclick = () => (stream ? stop() : start());
    $("#tr-speed").onchange = () => { if (stream) { stop(); start(); } };
    texts.triage = () => {
      drawCounters();
      renderFeed();
      btn.textContent = stream ? t("Pause stream") : (feedClaims.length ? t("Resume stream") : t("Start stream"));
      if (!stream) btn.classList.add("primary");
      if (lastTriage) renderResult(lastTriage.res, lastTriage.claim, lastTriage.body);
      const badge = $("#nav-red");
      if (counts.red) badge.textContent = t("{n} red", { n: counts.red });
    };

    const OFF = { description_matches_damage: "yes", amount_inflated: "no", document_manipulated: "no", police_report: "yes", injury: "no", witness: "yes" };
    $$("#tr-form .toggle").forEach((t) => { t.onclick = () => t.setAttribute("aria-pressed", String(t.getAttribute("aria-pressed") !== "true")); });
    $("#tr-form").onsubmit = async (e) => {
      e.preventDefault();
      const body = {};
      new FormData(e.target).forEach((val, k) => { body[k] = Number(val); });
      $$("#tr-form .toggle").forEach((t) => { body[t.dataset.k] = t.getAttribute("aria-pressed") === "true" ? t.dataset.on : OFF[t.dataset.k]; });
      try {
        const r = await postJson("/api/claims/score", body);
        renderResult(r.result, null, body);
      } catch (err) { toast(t("The claim could not be scored"), err.message, "info"); }
    };
  };
  arrive.triage = (arg) => { if (arg) showClaim(arg, true); };

  async function showClaim(id, scroll = false) {
    try {
      const r = await api(`/api/claims/${encodeURIComponent(id)}`);
      renderResult(r.result, r.claim, null);
      if (scroll) $("#tr-result").scrollIntoView({ behavior: "smooth", block: "center" });
    } catch { toast(t("Claim not found"), t("No simulated claim has the id {id}.", { id }), "info"); }
  }

  function renderResult(res, claim, body) {
    lastTriage = { res, claim, body };
    const route = res.route || res.action || "";
    const an = res.anomaly;
    $("#tr-result").innerHTML = `
      <header class="card-h">
        <div><h3>${claim ? `<span class="mono">${esc(claim.claim_id)}</span> · ${esc(claim.geo_name)}` : esc(t("Your claim"))} <span class="pill ${res.band}">${esc(t(BAND_LABEL[res.band] || res.band))}</span></h3>
        <p>${esc(t(cap(route)))}${claim ? ` · ${esc(t("simulated claim · €{amount} claimed", { amount: nf(claim.claimed_amount_eur) }))}` : ""}</p></div>
        <div class="card-tools"><button class="btn" type="button" id="brief-btn">${esc(t("Investigator brief"))}</button></div>
      </header>
      <div class="score">
        <div class="score-n ${res.band}">${nf(res.score)}</div>
        <div><div class="score-bar"><i class="g"></i><i class="a"></i><i class="r"></i><span class="marker" style="left:${Math.min(100, (res.score / 80) * 100)}%"></span></div>
        <div class="score-scale"><span>${esc(t("0 green"))}</span><span>${esc(t("15 amber"))}</span><span>${esc(t("35 red"))}</span></div></div>
      </div>
      <div class="rules-fired">
        ${res.fired.length ? res.fired.map((f) => `<div class="rule"><div><span class="mono">${esc(f.rule_id)}</span> · ${esc(t(f.label))}<em>${esc(t(f.basis))}</em></div><b>+${nf(f.points)}</b></div>`).join("") : `<div class="rule"><div>${esc(t("No red-flag rule fired"))}<em>${esc(t("The claim follows the normal path unless the anomaly check flags it."))}</em></div><b>0</b></div>`}
        ${an ? `<div class="rule anomaly"><div>${esc(t("Anomaly score, Isolation Forest"))}<em>${esc(t("A second look is requested at {n} or above", { n: nf(an.threshold, 2) }))}</em></div><b>${nf(an.anomaly_score, 2)}${an.second_look ? ` <span class="pill amber">${esc(t("Second look"))}</span>` : ""}</b></div>` : ""}
      </div>
      <div id="brief"></div>`;
    $("#brief-btn").onclick = async (e) => {
      e.target.disabled = true;
      $("#brief").innerHTML = `<div class="brief"><span class="typing"><span></span><span></span><span></span></span></div>`;
      try {
        const b = claim ? await api(`/api/agent/brief/${encodeURIComponent(claim.claim_id)}?lang=${getLang()}`) : await postJson("/api/agent/brief", { claim: body, lang: getLang() });
        $("#brief").innerHTML = `<div class="brief">${esc(b.brief)}</div>`;
      } catch (err) { $("#brief").innerHTML = `<div class="brief">${t("The brief could not be generated: {msg}", { msg: esc(err.message) })}</div>`; }
      e.target.disabled = false;
    };
  }

  function toast(title, text = "", kind = "") {
    const box = $("#toasts");
    const node = document.createElement("div");
    node.className = `toast ${kind}`;
    node.innerHTML = `<div><b>${esc(title)}</b><span>${esc(text)}</span></div>`;
    box.appendChild(node);
    while (box.children.length > 3) box.firstChild.remove();
    setTimeout(() => node.remove(), 4500);
  }

  // ------------------------------------------------------------------ ML
  const MODEL_LABEL = { baseline_median: "Median baseline", ridge: "Ridge", gradient_boosting: "Gradient boosting" };
  inits.ml = async () => {
    const [ml, reg, drift] = await Promise.all([api("/api/ml/regionalklasse"), api("/api/ml/registry"), api("/api/ml/drift"), loadGeo()]);
    const labels = ml.feature_labels || {};
    let target = "liability_class_2027";
    seg($("#ml-targets"), Object.entries(ml.targets).map(([k, t]) => [k, t.label]), target, (k) => { target = k; paint(); });

    const liab = ml.targets.liability_class_2027?.scores?.gate;
    const rule = liab?.rule;
    const regRows = Object.entries(reg.models || {}).flatMap(([name, m]) => Object.entries(m.versions).map(([ver, x]) => ({ name, ver, ...x })));
    const paintMlText = () => {
      const stages = [
        [t("Data contracts"), t("Schema, range and coverage checks on every build"), ""],
        [t("Training"), t("Baseline, ridge and gradient boosting with spatial cross-validation"), ""],
        [t("Quality gate"), rule ? t("MAE at most {mae}, {within} within one class", { mae: nf(rule.max_mae, 1), within: pct(rule.min_within_one, 0) }) : t("Thresholds from the config file"), liab ? `<span class="pill ${liab.passed ? "pass" : "fail"}">${esc(t(liab.passed ? "Passed" : "Failed"))}</span>` : ""],
        [t("Registry"), `<span class="mono">${esc(reg.models?.regionalklasse?.production || ml.version || "")}</span>`, `<span class="pill production">${esc(t("Production"))}</span>`],
        [t("Drift monitor"), t("{current} against training data", { current: drift.current || "" }), `<span class="pill ${esc(drift.status)}">${esc(t(cap(drift.status)))}</span>`],
        [t("Retraining"), t("Weekly in CI, or started by the drift workflow in n8n"), ""],
      ];
      $("#ml-pipeline").innerHTML = stages.map(([name, note, pill], i) => `<div class="stage"><div class="stage-n">${esc(t("Step {n}", { n: i + 1 }))}</div><b>${name}</b><small>${note}</small>${pill}</div>`).join("");
      $("#ml-registry").innerHTML = `<table><thead><tr><th>${esc(t("Model and version"))}</th><th>${esc(t("Stage"))}</th><th>${esc(t("Gate"))}</th><th class="num">${esc(t("Headline"))}</th><th>${esc(t("Created, UTC"))}</th></tr></thead><tbody>${regRows.map((r) => `<tr><td><b>${esc(t(words(r.name)))}</b><span class="sub mono">${esc(r.ver)}</span></td><td><span class="pill ${esc(r.stage)}">${esc(t(cap(r.stage)))}</span></td><td><span class="pill ${r.gate_passed ? "pass" : "fail"}">${esc(t(r.gate_passed ? "Passed" : "Failed"))}</span></td><td class="num">${r.headline?.mae != null ? esc(t("MAE {n}", { n: nf(r.headline.mae, 2) })) : r.headline?.flagged != null ? esc(t("{n} flagged", { n: nf(r.headline.flagged) })) : "–"}</td><td class="num">${esc((r.created || "").slice(0, 16).replace("T", " "))}</td></tr>`).join("")}</tbody></table>`;
      $("#ml-drift-sub").textContent = t("Population Stability Index, {current} against {reference}. Above {watch} watch, above {retrain} retrain.", { current: drift.current || t("current fleet"), reference: drift.reference || t("training data"), watch: nf(drift.thresholds?.watch ?? 0.1, 2), retrain: nf(drift.thresholds?.retrain ?? 0.25, 2) });
    };
    texts.ml = paintMlText;
    paintMlText();

    const paint = () => {
      const tgt = ml.targets[target];
      const s = tgt.scores;
      const best = s.best_model;
      const sp = s.spatial[best];
      const gate = s.gate || {};
      const leak = s.random[best].mae ? sp.mae / s.random[best].mae - 1 : null;
      const modelName = t(MODEL_LABEL[best] || words(best));
      $("#ml-kpis").innerHTML = [
        [t("Error on unseen Bundesländer"), t("{n} classes", { n: nf(sp.mae, 2) }), t("{model} · median baseline {mae}", { model: modelName, mae: nf(s.spatial.baseline_median.mae, 2) })],
        [t("Within one class"), pct(sp.within_one_class, 0), t("exact class in {pct} of districts", { pct: pct(sp.exact_class, 0) })],
        [t("Leakage in a random split"), leak == null ? "–" : `+${pct(leak, 0)}`, t("random split reports {random}, the honest figure is {honest}", { random: nf(s.random[best].mae, 2), honest: nf(sp.mae, 2) })],
        [t("Benchmark: last year's class"), s.persistence_2026 ? t("{n} classes", { n: nf(s.persistence_2026.mae, 2) }) : "–", t("error when the 2026 class is carried forward")],
      ].map(([l, val, n]) => `<div class="kpi"><div class="kpi-l">${esc(l)}</div><div class="kpi-v">${esc(val)}</div><div class="kpi-n">${esc(n)}</div></div>`).join("");

      const models = Object.keys(s.spatial);
      const fmt2 = (x) => nf(x, 2);
      chart("ml-cv").setOption(base({
        legend: legend(), grid: grid({ top: 38 }), tooltip: shadowTip({ valueFormatter: fmt2 }),
        xAxis: ax("category", { data: [...models.map((m) => t(MODEL_LABEL[m] || words(m))), t("Last year's class")], axisLabel: { interval: 0 } }),
        yAxis: ax("value"),
        series: [
          { name: t("Unseen Bundesländer"), type: "bar", barWidth: 26, barGap: "12%", color: C.blue, itemStyle: { borderRadius: [2, 2, 0, 0] }, label: { show: true, position: "top", color: C.text2, fontSize: 11, formatter: (p) => fmt2(p.value) }, data: [...models.map((m) => s.spatial[m].mae), s.persistence_2026?.mae ?? null] },
          { name: t("Random split"), type: "bar", barWidth: 26, color: C.muted, itemStyle: { borderRadius: [2, 2, 0, 0] }, label: { show: true, position: "top", color: C.text3, fontSize: 11, formatter: (p) => fmt2(p.value) }, data: models.map((m) => s.random[m].mae) },
        ],
      }), true);

      const max = 2 * Math.ceil((Math.max(...tgt.points.map((p) => p.actual)) + 1) / 2);
      chart("ml-scatter").setOption(base({
        grid: grid({ bottom: 24, top: 28 }),
        tooltip: { formatter: (p) => (p.data?.n ? `<b>${esc(p.data.n)}</b><br/>${esc(t("GDV class {actual}", { actual: p.data.a }))}<br/>${esc(t("Predicted {n}", { n: nf(p.data.value[0], 1) }))}` : "") },
        visualMap: { show: false, dimension: 2, min: -4, max: 4, inRange: { color: DIV } },
        xAxis: ax("value", { name: t("Predicted class"), nameLocation: "middle", nameGap: 28, min: 0, max, interval: 2 }),
        yAxis: ax("value", { ...yName(t("GDV class")), min: 0, max, interval: 2 }),
        series: [
          { type: "scatter", symbolSize: 7, itemStyle: { opacity: 0.85, borderColor: C.surface, borderWidth: 0.5 }, data: tgt.points.map((p) => ({ value: [p.predicted, p.actual + jitter(p.geo_code) * 0.4, p.residual], n: p.geo_name, a: p.actual })) },
          { type: "line", data: [[0, 0], [max, max]], symbol: "none", lineStyle: { color: C.text3, type: "dashed", width: 1 }, silent: true, tooltip: { show: false } },
        ],
      }), true);

      const imp = tgt.importance.slice(0, 12).reverse();
      chart("ml-imp").setOption(base({
        grid: grid({ top: 4, right: 46 }), tooltip: shadowTip({ valueFormatter: (x) => nf(x, 3) }),
        xAxis: ax("value"), yAxis: yCat(imp.map((i) => t(labels[i.feature] || i.feature))),
        series: [{ type: "bar", barWidth: 11, color: C.blue, itemStyle: { borderRadius: [0, 2, 2, 0] }, label: barLabel((x) => nf(x, 2)), data: imp.map((i) => i.mae_increase) }],
      }), true);

      const resid = {};
      tgt.points.forEach((p) => { resid[p.geo_code] = p.residual; });
      drawMap(chart("ml-resid"), {
        min: -4, max: 4, colors: DIV, text: [t("GDV higher"), t("GDV lower")], legendFmt: (x) => signed(x, 0),
        data: districtRows.map((r) => ({ name: r.geo_code, value: resid[r.geo_code] ?? null })),
        tip: (code, d) => { const r = districtIndex[code]; return r ? `<b>${esc(r.geo_name)}</b><br/>${dim(esc(r.bundesland))}<br/>${esc(t("Gap: {v}", { v: d?.value == null ? t("not modelled") : signed(d.value, 1) }))}` : ""; },
      });

      const pdp = Object.entries(tgt.partial_dependence);
      const col = (i) => `${(i % 3) * 33.4 + 1}%`;
      chart("ml-pdp").setOption(base({
        tooltip: lineTip({ valueFormatter: (x) => nf(x, 2) }),
        title: pdp.map(([f], i) => ({ text: t(labels[f] || f), left: col(i), top: i < 3 ? "0%" : "52%", textStyle: { color: C.text2, fontSize: 12, fontWeight: 500, fontFamily: FONT } })),
        grid: pdp.map((_, i) => ({ left: col(i), width: "29%", top: i < 3 ? "10%" : "62%", height: "30%", containLabel: true })),
        xAxis: pdp.map((_, i) => ax("value", { gridIndex: i, scale: true, splitLine: { show: false }, axisLine: { show: true, lineStyle: { color: C.lineStrong } }, axisLabel: { fontSize: 10, hideOverlap: true } })),
        yAxis: pdp.map((_, i) => ax("value", { gridIndex: i, scale: true, splitNumber: 3, axisLabel: { fontSize: 10 } })),
        series: pdp.map(([, d], i) => ({ type: "line", xAxisIndex: i, yAxisIndex: i, smooth: 0.2, symbol: "none", color: C.blue, lineStyle: { width: 2 }, areaStyle: { opacity: 0.06 }, data: d.x.map((x, j) => [x, d.y[j]]) })),
      }), true);

      const GATE = {
        mae_below_max: () => t("Error is at most {n} classes", { n: nf(gate.rule.max_mae, 1) }),
        within_one_above_min: () => t("At least {pct} of districts within one class", { pct: pct(gate.rule.min_within_one, 0) }),
        beats_baseline: () => t("Beats the median baseline by at least {pct}", { pct: pct(gate.rule.must_beat_baseline_by, 0) }),
      };
      $("#ml-gate").innerHTML = gate.rule
        ? `<div class="gate-list">${Object.entries(gate.checks || {}).map(([k, ok]) => `<div><span>${esc(GATE[k]?.() || words(k))}</span><span class="pill ${ok ? "pass" : "fail"}">${esc(t(ok ? "Passed" : "Failed"))}</span></div>`).join("")}</div>`
        : `<p class="empty" style="min-height:60px">${esc(t("No gate is configured for this target. Its scores are tracked only."))}</p>`;

      const feats = [...(drift.features || [])].reverse();
      const statusColor = { retrain: C.red, watch: C.amber, stable: C.green };
      chart("ml-drift").setOption(base({
        grid: grid({ top: 18, right: 46 }),
        tooltip: shadowTip({ formatter: (p) => { const f = feats[p[0].dataIndex]; return `<b>${esc(t(labels[f.feature] || f.feature))}</b><br/>${esc(t("PSI {psi} · {status}", { psi: nf(f.psi, 2), status: t(f.status) }))}<br/>${esc(t("Mean {a} → {b}", { a: pct(f.reference_mean), b: pct(f.current_mean) }))}`; } }),
        xAxis: ax("value"), yAxis: yCat(feats.map((f) => t(labels[f.feature] || f.feature))),
        series: [{ type: "bar", barWidth: 11, label: barLabel((x) => nf(x, 2)), data: feats.map((f) => ({ value: f.psi, itemStyle: { color: statusColor[f.status] || C.muted, borderRadius: [0, 2, 2, 0] } })),
          markLine: { symbol: "none", silent: true, label: { color: C.text3, fontSize: 10, position: "end" }, lineStyle: { type: "dashed", width: 1 },
            data: [{ xAxis: drift.thresholds?.watch ?? 0.1, lineStyle: { color: C.amber }, label: { formatter: t("watch") } }, { xAxis: drift.thresholds?.retrain ?? 0.25, lineStyle: { color: C.red }, label: { formatter: t("retrain") } }] } }],
      }), true);
    };
    painters.ml = paint;
    paint();
  };

  // ------------------------------------------------------------------ agent
  const chatHistory = [];
  const SUGGEST = [
    "Why is Gelsenkirchen in Haftpflicht class 12?",
    "Top 10 most expensive rural districts in Bayern",
    "Which districts are priced higher than the model predicts?",
    "How does Germany compare in Europe on road deaths?",
    "Police fraud trend in Germany",
    "Explain SIM-0373",
    "How good is the model and is there drift?",
    "What does the Unfallatlas not include?",
  ];
  const AVATAR = `<div class="avatar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 5 5.7v5.8c0 4.7 3 8.4 7 9.6 4-1.2 7-4.9 7-9.6V5.7z"/><path d="m8.8 12 2.3 2.3 4.2-4.6"/></svg></div>`;

  function md(text) {
    const lines = esc(text).split("\n");
    let html = "";
    let list = null;
    const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|\s)_(.+?)_(?=\s|$|[.,;:])/g, "$1<em>$2</em>").replace(/\*(.+?)\*/g, "<em>$1</em>").replace(/`(.+?)`/g, "<code>$1</code>");
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    let quote = [];
    const flushQuote = () => { if (quote.length) { html += `<blockquote>${quote.map(inline).join("<br/>")}</blockquote>`; quote = []; } };
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (line.startsWith("&gt; ")) { close(); quote.push(line.slice(5)); continue; }
      flushQuote();
      let m;
      if ((m = line.match(/^\s*[-•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1])}</li>`; }
      else if ((m = line.match(/^\s*\d+\.\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1])}</li>`; }
      else if (line.trim() === "") { close(); }
      else { close(); html += `<p>${inline(line.replace(/^#+\s*/, ""))}</p>`; }
    }
    flushQuote(); close();
    return html;
  }
  function addMsg(role, html) {
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.innerHTML = role === "user" ? esc(html) : `${AVATAR}<div class="bubble">${html}</div>`;
    $("#messages").appendChild(el);
    $("#messages").scrollTop = $("#messages").scrollHeight;
    return el;
  }
  function addStep(color, title, detail) {
    const el = document.createElement("div");
    el.className = "tstep";
    el.style.setProperty("--k", color);
    el.innerHTML = `<b>${esc(title)}</b>${detail ? `<code>${esc(detail)}</code>` : ""}`;
    $("#trace").appendChild(el);
    $("#trace").scrollTop = $("#trace").scrollHeight;
  }

  let busy = false;
  async function ask(question) {
    if (busy || !question) return;
    busy = true;
    addMsg("user", question);
    const bot = addMsg("bot", `<div class="used"></div><span class="typing"><span></span><span></span><span></span></span>`);
    const used = $(".used", bot);
    $("#trace").innerHTML = "";
    addStep("var(--text-3)", t("Question"), question);
    try {
      const res = await fetch("/api/agent/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, history: chatHistory.slice(-6), lang: getLang() }) });
      if (!res.ok) throw new Error(`the agent returned ${res.status}`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done: end } = await reader.read();
        if (end) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          if (!chunk.startsWith("data: ")) continue;
          const ev = JSON.parse(chunk.slice(6));
          if (ev.type === "plan") addStep("var(--d4)", t("Plan"), ev.text);
          if (ev.type === "tool") { addStep("var(--d1)", t("Call {name}", { name: ev.name }), JSON.stringify(ev.args)); used.insertAdjacentHTML("beforeend", `<span>${esc(ev.name)}</span>`); }
          if (ev.type === "observation") addStep("var(--d3)", t("Result from {name}", { name: ev.name }), ev.summary);
          if (ev.type === "answer") {
            addStep("var(--green)", t("Answer, {mode}", { mode: ev.mode === "llm" ? t("language model") : t("offline planner") }), ev.sources.length === 1 ? t("1 source cited") : t("{n} sources cited", { n: ev.sources.length }));
            $(".bubble", bot).innerHTML = (used.children.length ? used.outerHTML : "") + md(ev.text) + (ev.sources.length ? `<div class="sources">${ev.sources.map((s) => `<span>${esc(s)}</span>`).join("")}</div>` : "");
            chatHistory.push({ role: "user", content: question }, { role: "assistant", content: ev.text });
          }
        }
      }
    } catch (err) {
      $(".bubble", bot).innerHTML = `<p>${t("The agent could not answer: {msg}.", { msg: esc(err.message) })}</p>`;
    }
    $("#messages").scrollTop = $("#messages").scrollHeight;
    busy = false;
  }

  inits.agent = async () => {
    const paintSuggest = () => { $("#suggest").innerHTML = SUGGEST.map((s) => `<button type="button" class="chip" data-q="${esc(s)}">${esc(t(s))}</button>`).join(""); };
    paintSuggest();
    $("#suggest").onclick = (e) => { const b = e.target.closest(".chip"); if (b) ask(getLang() === "de" ? b.textContent : b.dataset.q); };
    const ta = $("#composer textarea");
    $("#composer").onsubmit = (e) => { e.preventDefault(); const q = ta.value.trim(); ta.value = ""; ta.style.height = ""; ask(q); };
    ta.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer").requestSubmit(); } };
    ta.oninput = () => { ta.style.height = "auto"; ta.style.height = `${Math.min(140, ta.scrollHeight + 2)}px`; };
    const welcome = "I answer questions about German districts, Europe, fraud statistics, the simulated claims and the models. I use the project data and the source documents, show every tool I call, and cite my sources.\n\nClaims in the triage inbox are **simulated**.";
    addMsg("bot", md(t(welcome)));
    texts.agent = () => {
      paintSuggest();
      const bots = $$("#messages .msg.bot");
      const users = $$("#messages .msg.user");
      if (!users.length && bots.length === 1) bots[0].querySelector(".bubble").innerHTML = md(t(welcome));
      if (!$("#trace .tstep") && $("#trace .empty")) $("#trace .empty").textContent = t("Ask a question to see how the agent works.");
    };
  };
  arrive.agent = () => {
    if (!pendingQuestion) return;
    const q = pendingQuestion;
    pendingQuestion = null;
    ask(q);
  };

  // ------------------------------------------------------------------ command palette
  const PAGES = [["overview", "Overview"], ["germany", "Germany"], ["europe", "Europe"], ["fraud", "Fraud landscape"], ["triage", "Live triage"], ["ml", "ML lab and MLOps"], ["agent", "Analyst agent"], ["system", "How it connects"], ["methods", "Data and methods"]];
  let pItems = [];
  let pIdx = 0;
  let pReturn = null;
  function paletteGroups(q) {
    const f = fold(q.trim());
    const groups = [];
    const pages = PAGES.filter(([, l]) => !f || fold(l).includes(f) || fold(t(l)).includes(f)).map(([k, l]) => ({ label: t(l), hint: t("Page"), run: () => go(k) }));
    if (!f) {
      groups.push([t("Pages"), pages]);
      groups.push([t("Try"), [
        { label: "München", hint: t("District"), run: () => go("germany", "09162") },
        { label: "SIM-0373", hint: t("Simulated claim"), run: () => go("triage", "SIM-0373") },
        { label: t("Which districts are priced higher than the model predicts?"), hint: t("Ask the agent"), run: () => askAgent(getLang() === "de" ? t("Which districts are priced higher than the model predicts?") : "Which districts are priced higher than the model predicts?") },
      ]]);
      return groups;
    }
    const ds = districtRows.filter((r) => fold(r.geo_name).includes(f) || r.geo_code.startsWith(f))
      .sort((a, b) => (fold(b.geo_name).startsWith(f) - fold(a.geo_name).startsWith(f)) || b.population_2024 - a.population_2024).slice(0, 7)
      .map((r) => ({ label: r.geo_name, hint: `${r.bundesland} · ${r.liability_class_2027 == null ? t("no single class") : t("class {n}", { n: nf(r.liability_class_2027) })}`, run: () => go("germany", r.geo_code) }));
    if (ds.length) groups.push([t("Districts"), ds]);
    const claim = q.trim().match(/^sim[-\s]?(\d{1,4})$/i);
    if (claim) { const id = `SIM-${claim[1].padStart(4, "0")}`; groups.push([t("Claims"), [{ label: id, hint: t("Open simulated claim"), run: () => go("triage", id) }]]); }
    if (pages.length) groups.push([t("Pages"), pages]);
    groups.push([t("Agent"), [{ label: t("Ask: {q}", { q: q.trim() }), hint: t("Analyst agent"), run: () => askAgent(q.trim()) }]]);
    return groups;
  }
  function renderPalette() {
    const groups = paletteGroups($("#palette-input").value);
    pItems = groups.flatMap(([, items]) => items);
    pIdx = Math.min(pIdx, Math.max(0, pItems.length - 1));
    let n = 0;
    $("#palette-list").innerHTML = groups.map(([g, items]) => `<div class="p-group">${esc(g)}</div>${items.map((it) => { const i = n++; return `<button type="button" class="p-item ${i === pIdx ? "on" : ""}" data-i="${i}" role="option" aria-selected="${i === pIdx}"><span>${esc(it.label)}</span><small>${esc(it.hint)}</small></button>`; }).join("")}`).join("");
    $(".p-item.on", $("#palette-list"))?.scrollIntoView({ block: "nearest" });
  }
  function openPalette() {
    if (!$("#palette").hidden) return;
    pReturn = document.activeElement;
    $("#palette").hidden = false;
    $("#palette-input").value = "";
    pIdx = 0;
    renderPalette();
    $("#palette-input").focus();
    loadDistricts().then(renderPalette).catch(() => {});
  }
  function closePalette() {
    $("#palette").hidden = true;
    pReturn?.focus?.();
  }
  function runPalette(i) {
    const it = pItems[i];
    if (!it) return;
    closePalette();
    it.run();
  }

  // ------------------------------------------------------------------ chrome
  function bindChrome() {
    $$("#lang .lang-b").forEach((b) => {
      b.onclick = () => {
        if (b.dataset.lang === getLang()) return;
        i18n.setLang(b.dataset.lang);
        applyLanguage();
      };
    });
    $("#theme-btn").onclick = () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("cg-theme", next); } catch { /* storage unavailable */ }
      repaint();
    };
    $("#menu-btn").onclick = () => $("#app").classList.toggle("nav-open");
    $("#scrim").onclick = () => $("#app").classList.remove("nav-open");

    $("#palette-kbd").textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘K" : "Ctrl K";
    $("#palette-btn").onclick = openPalette;
    $("#palette").onclick = (e) => { if (e.target.id === "palette") closePalette(); };
    $("#palette-input").oninput = () => { pIdx = 0; renderPalette(); };
    $("#palette-input").onkeydown = (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); pIdx = (pIdx + 1) % Math.max(1, pItems.length); renderPalette(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); pIdx = (pIdx - 1 + pItems.length) % Math.max(1, pItems.length); renderPalette(); }
      else if (e.key === "Enter") { e.preventDefault(); runPalette(pIdx); }
      else if (e.key === "Escape") { e.preventDefault(); closePalette(); }
    };
    $("#palette-list").onclick = (e) => { const b = e.target.closest(".p-item"); if (b) runPalette(Number(b.dataset.i)); };
    $("#palette-list").onmousemove = (e) => { const b = e.target.closest(".p-item"); if (b && Number(b.dataset.i) !== pIdx) { pIdx = Number(b.dataset.i); $$(".p-item", $("#palette-list")).forEach((x) => x.classList.toggle("on", x === b)); } };
    document.addEventListener("keydown", (e) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if ($("#palette").hidden) openPalette(); else closePalette(); }
      else if (e.key === "/" && !typing) { e.preventDefault(); openPalette(); }
      else if (e.key === "Escape" && !$("#palette").hidden) closePalette();
    });

    // download button on every chart card
    const icon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7.5 11 12 15.5 16.5 11M5 19.5h14"/></svg>`;
    $$(".card").forEach((card) => {
      const ch = $(".chart[id]", card);
      const head = $(".card-h", card);
      if (!ch || !head) return;
      let tools = $(".card-tools", head);
      if (!tools) { tools = document.createElement("div"); tools.className = "card-tools"; head.appendChild(tools); }
      tools.insertAdjacentHTML("beforeend", `<button type="button" class="icon-btn sm" data-export="${ch.id}" data-i18n-label="Download this chart as PNG" data-i18n-title="Download this chart as PNG" title="Download this chart as PNG" aria-label="Download this chart as PNG">${icon}</button>`);
    });
    // zoom controls on every map
    $$(".map-wrap").forEach((w) => w.insertAdjacentHTML("beforeend", `<div class="map-ctl"><button type="button" data-zoom="in" data-i18n-label="Zoom in" data-i18n-title="Zoom in" aria-label="Zoom in" title="Zoom in">+</button><button type="button" data-zoom="out" data-i18n-label="Zoom out" data-i18n-title="Zoom out" aria-label="Zoom out" title="Zoom out">−</button><button type="button" data-zoom="reset" data-i18n-label="Reset the map" data-i18n-title="Reset the map" aria-label="Reset the map" title="Reset the map"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 1 0 2.6-5.9M4 4.5v4h4"/></svg></button></div>`));
    document.addEventListener("click", (e) => {
      const ex = e.target.closest("[data-export]");
      if (ex) {
        const c = echarts.getInstanceByDom(document.getElementById(ex.dataset.export));
        if (c) download(`claimguard-${ex.dataset.export}.png`, c.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: C.surface }));
        return;
      }
      const z = e.target.closest("[data-zoom]");
      if (!z) return;
      const c = echarts.getInstanceByDom(document.getElementById(z.closest(".map-wrap").dataset.map));
      if (!c?.__spec) return;
      const now = c.getOption().series[0].zoom || 1;
      const next = z.dataset.zoom === "reset" ? 1 : Math.min(10, Math.max(1, now * (z.dataset.zoom === "in" ? 1.6 : 1 / 1.6)));
      if (next <= 1.01) drawMap(c, c.__spec, false);
      else c.setOption({ series: [{ zoom: next, roam: "move" }] });
    });
  }

  function applyDom() {
    $$("[data-i18n]").forEach((el) => { el.textContent = t(el.getAttribute("data-i18n")); });
    $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.getAttribute("data-i18n-html")); });
    $$("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.getAttribute("data-i18n-placeholder")); });
    $$("[data-i18n-label]").forEach((el) => { el.setAttribute("aria-label", t(el.getAttribute("data-i18n-label"))); });
    $$("[data-i18n-title]").forEach((el) => { el.title = t(el.getAttribute("data-i18n-title")); });
  }
  function applyLanguage() {
    regionNames = null;
    $$("#lang .lang-b").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === getLang())));
    applyDom();
    const el = $(".view.active");
    if (el) {
      $("#crumb").textContent = t(el.dataset.title);
      document.title = `${t(el.dataset.title)} · ClaimGuard`;
    }
    done.forEach((view) => { texts[view]?.(); painters[view]?.(); });
    if (!$("#palette").hidden) renderPalette();
    status();
  }

  async function status() {
    try {
      const h = await api("/api/health");
      const llm = h.agent.mode === "llm";
      $("#sb-model").textContent = h.models.regionalklasse || t("none");
      $("#sb-agent").textContent = llm ? h.agent.model : t("Offline planner");
      $("#agent-mode").textContent = llm ? t("Language model: {model}", { model: h.agent.model }) : t("Offline planner");
      $("#agent-mode").classList.toggle("accent", llm);
    } catch {
      $("#sb-model").textContent = t("API unreachable");
      $("#sb-agent").textContent = "–";
    }
    try {
      const s = (await api("/api/overview")).drift_status;
      if (!s) return;
      $("#sb-drift").innerHTML = `<span class="pill ${esc(s)}">${esc(t(cap(s)))}</span>`;
      $("#top-drift").innerHTML = `<i class="dot ${esc(s)}"></i>${esc(t("Fleet drift: {status}", { status: t(s) }))}`;
      $("#top-drift").hidden = false;
    } catch { $("#sb-drift").textContent = "–"; }
  }

  inits.system = async () => { window.CG_SYSTEM?.start(); };
  painters.system = () => window.CG_SYSTEM?.resize();
  texts.system = () => window.CG_SYSTEM?.relabel();

  // ------------------------------------------------------------------ boot
  async function boot() {
    readTheme();
    bindChrome();
    applyLanguage();
    const inter = (document.fonts?.load?.("500 12px Inter") ?? Promise.resolve([])).then((faces) => faces.length > 0).catch(() => false);
    const useInter = () => { FONT = `Inter, ${FALLBACK_FONT}`; };
    if (await Promise.race([inter, new Promise((r) => setTimeout(() => r(false), 700))])) useInter();
    else inter.then((ok) => { if (ok) { useInter(); repaint(); } });
    window.addEventListener("hashchange", route);
    route();
    status();
  }
  boot();
})();
