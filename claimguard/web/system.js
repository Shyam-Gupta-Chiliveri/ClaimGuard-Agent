/* Spatial map of the real system. Canvas only: no library, no network. */
(() => {
  "use strict";

  const GROUPS = [
    ["sources", "Published statistics", "GDV, Destatis, KBA, Eurostat, EIOPA and BKA", "#8eb6ff"],
    ["tables", "Tables", "Districts, Europe and Fraud", "#5ee0d0"],
    ["models", "Models", "Regionalklasse and Anomaly", "#f0b46a"],
    ["surface", "Site", "API, Dashboards and the Agent. These are the ClaimGuard pages.", "#d7c4ff"],
    ["jobs", "Jobs", "The four workflows on this page: Claim intake, App events, Weekly drift and Red queue", "#8ee0a8"],
  ];

  const NODES = [
    ["gdv", "GDV", "Regionalklassen, the price classes the model explains.", "sources", -250, 80, -260],
    ["destatis", "Destatis", "Population and injury accidents.", "sources", -150, 150, -250],
    ["kba", "KBA", "Vehicle stock, and the fleet used for the drift check.", "sources", -50, 180, -240],
    ["eurostat", "Eurostat", "Road deaths and passenger cars per person.", "sources", 50, 180, -240],
    ["eiopa", "EIOPA", "Non-life premiums and the claims ratio.", "sources", 150, 150, -250],
    ["bka", "BKA", "Police-recorded insurance fraud.", "sources", 250, 80, -260],
    ["districts", "Districts", "400 districts joined to classes, accidents and cars.", "tables", -150, -20, -70],
    ["europe", "Europe", "Country comparison for roads and insurance.", "tables", 0, 40, -40],
    ["fraud", "Fraud", "Published fraud figures and the ten red-flag rules.", "tables", 150, -20, -70],
    ["regional", "Regionalklasse", "Predicts a district class from public data, checked on unseen Bundesländer.", "models", -100, 90, 70],
    ["anomaly", "Anomaly", "Isolation Forest. A second look, not a fraud verdict.", "models", 100, 90, 70],
    ["api", "API", "Serves the maps, the scores, the models and the agent.", "surface", 0, -10, 190],
    ["site", "Dashboards", "The pages a visitor reads.", "surface", -180, -90, 230],
    ["agent", "Agent", "Twelve tools over the data, the models and the documents, with citations.", "surface", 180, -90, 230],
    ["intake", "Claim intake", "A claim arrives, is scored, and an investigator note is written.", "jobs", -160, 50, 340],
    ["events", "App events", "Claims the site itself pushes into the same path.", "jobs", -55, 130, 360],
    ["drift", "Weekly drift", "Once a week, asks whether the model should be retrained.", "jobs", 55, 130, 360],
    ["digest", "Red queue", "Once a day, lists claims waiting for an investigator.", "jobs", 160, 50, 340],
  ].map(([id, label, blurb, group, x, y, z]) => ({ id, label, blurb, group, x, y, z }));

  const EDGES = [
    ["gdv", "districts"], ["destatis", "districts"], ["kba", "districts"],
    ["eurostat", "europe"], ["eiopa", "europe"], ["bka", "fraud"],
    ["districts", "regional"], ["fraud", "anomaly"],
    ["districts", "api"], ["europe", "api"], ["fraud", "api"],
    ["regional", "api"], ["anomaly", "api"],
    ["api", "site"], ["api", "agent"],
    ["api", "intake"], ["api", "events"], ["api", "drift"], ["api", "digest"],
  ];

  const byId = Object.fromEntries(NODES.map((n) => [n.id, n]));
  const ICON = {
    gdv: "#8eb6ff", destatis: "#7ddeb0", kba: "#f0c14b", eurostat: "#67d4ff", eiopa: "#f0d78c", bka: "#ff9b8a",
    districts: "#8aa2ff", europe: "#5ee0d0", fraud: "#ff8a6a",
    regional: "#f0b46a", anomaly: "#d2a8ff",
    api: "#7ee0c8", site: "#9ec1ff", agent: "#d7c4ff",
    intake: "#8ee0a8", events: "#ffe08a", drift: "#7ad7ff", digest: "#ff9aa8",
  };
  const rgba = (hex, a) => {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  };
  let rotY = -0.42;
  let rotX = 0.22;
  let zoom = 1;
  let selected = "api";
  const stars = Array.from({ length: 90 }, (_, i) => {
    const a = (i * 2.399) % (Math.PI * 2);
    const b = ((i * 17) % 50) / 50 - 0.5;
    const r = 420 + (i % 7) * 18;
    return { x: Math.cos(a) * r, y: b * 280, z: Math.sin(a) * r };
  });
  const t = (s) => window.CG_I18N?.t(s) ?? s;

  function pane(g, x, y, w, h) {
    g.moveTo(x, y);
    g.lineTo(x + w, y);
    g.lineTo(x + w, y + h);
    g.lineTo(x, y + h);
    g.closePath();
  }

  const GLYPH = {
    gdv(g) {
      g.moveTo(0, -11); g.lineTo(9, -7); g.lineTo(9, 2);
      g.quadraticCurveTo(9, 10, 0, 12); g.quadraticCurveTo(-9, 10, -9, 2);
      g.lineTo(-9, -7); g.closePath();
      g.moveTo(-4, -1); g.lineTo(4, -1);
      g.moveTo(-4, 3); g.lineTo(2, 3);
    },
    destatis(g) {
      pane(g, -10, 1, 5, 8); pane(g, -2.5, -5, 5, 14); pane(g, 5, -10, 5, 19);
    },
    kba(g) {
      g.moveTo(-11, 2); g.lineTo(-7, 2); g.lineTo(-4, -4); g.lineTo(4, -4); g.lineTo(7, 2); g.lineTo(11, 2);
      g.lineTo(11, 6); g.lineTo(-11, 6); g.closePath();
      g.moveTo(-3.7, 6); g.arc(-6, 6, 2.3, 0, Math.PI * 2);
      g.moveTo(8.3, 6); g.arc(6, 6, 2.3, 0, Math.PI * 2);
    },
    eurostat(g) {
      g.arc(0, 0, 9, 0, Math.PI * 2);
      g.moveTo(-9, 0); g.lineTo(9, 0);
      g.moveTo(0, -9); g.bezierCurveTo(5, -5, 5, 5, 0, 9);
      g.moveTo(0, -9); g.bezierCurveTo(-5, -5, -5, 5, 0, 9);
    },
    eiopa(g) {
      g.moveTo(7, -7); g.bezierCurveTo(-1, -12, -10, -6, -8, 0);
      g.bezierCurveTo(-10, 6, -1, 12, 7, 7);
      g.moveTo(-9, -2); g.lineTo(5, -2);
      g.moveTo(-9, 3); g.lineTo(4, 3);
    },
    bka(g) {
      for (let i = 0; i < 10; i++) {
        const a = -Math.PI / 2 + i * Math.PI / 5;
        const r = i % 2 ? 4.2 : 10;
        const x = Math.cos(a) * r;
        const y = Math.sin(a) * r;
        if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
      }
      g.closePath();
    },
    districts(g) {
      for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 3; c++) pane(g, -10 + c * 7, -10 + r * 7, 5.2, 5.2);
      }
    },
    europe(g) {
      g.moveTo(-10, -8); g.lineTo(3, -8); g.lineTo(10, -1); g.lineTo(10, 8); g.lineTo(-10, 8); g.closePath();
      g.moveTo(3, -8); g.lineTo(3, -1); g.lineTo(10, -1);
    },
    fraud(g) {
      g.moveTo(0, -11); g.lineTo(10, 9); g.lineTo(-10, 9); g.closePath();
      g.moveTo(0, -4); g.lineTo(0, 3);
      g.moveTo(0, 6.2); g.arc(0, 6.2, 0.7, 0, Math.PI * 2);
    },
    regional(g) {
      g.moveTo(-10, 8); g.lineTo(10, 8);
      g.moveTo(-10, 8); g.lineTo(-10, -8);
      g.moveTo(-8, 5); g.lineTo(-2, 1); g.lineTo(2, 3); g.lineTo(8, -6);
    },
    anomaly(g) {
      g.arc(-2, -2, 6.2, 0, Math.PI * 2);
      g.moveTo(2.6, 2.6); g.lineTo(10, 10);
    },
    api(g) {
      g.moveTo(-4, -11); g.quadraticCurveTo(-9, -11, -9, -6); g.lineTo(-9, -2);
      g.quadraticCurveTo(-9, 0, -12, 0); g.quadraticCurveTo(-9, 0, -9, 2);
      g.lineTo(-9, 6); g.quadraticCurveTo(-9, 11, -4, 11);
      g.moveTo(4, -11); g.quadraticCurveTo(9, -11, 9, -6); g.lineTo(9, -2);
      g.quadraticCurveTo(9, 0, 12, 0); g.quadraticCurveTo(9, 0, 9, 2);
      g.lineTo(9, 6); g.quadraticCurveTo(9, 11, 4, 11);
    },
    site(g) {
      pane(g, -10, -10, 8, 8); pane(g, 2, -10, 8, 8); pane(g, -10, 2, 8, 8); pane(g, 2, 2, 8, 8);
    },
    agent(g) {
      g.arc(0, -5, 3.5, 0, Math.PI * 2);
      g.moveTo(-8, 11); g.quadraticCurveTo(-8, 1, 0, 1); g.quadraticCurveTo(8, 1, 8, 11);
    },
    intake(g) {
      g.moveTo(-10, 0); g.lineTo(-10, 10); g.lineTo(10, 10); g.lineTo(10, 0);
      g.moveTo(-10, 0); g.lineTo(-4, 4); g.lineTo(4, 4); g.lineTo(10, 0);
      g.moveTo(0, -11); g.lineTo(0, -2);
      g.moveTo(-3.2, -5); g.lineTo(0, -2); g.lineTo(3.2, -5);
    },
    events(g) {
      g.moveTo(2, -11); g.lineTo(-6, 1); g.lineTo(-1, 1); g.lineTo(-3, 11); g.lineTo(7, -2); g.lineTo(1, -2); g.closePath();
    },
    drift(g) {
      g.arc(0, 0, 7, 0.7, Math.PI * 1.85);
      g.moveTo(5.2, -6.2); g.lineTo(8.5, -1.2); g.lineTo(2.4, -2.2);
    },
    digest(g) {
      [-10, -2, 6].forEach((y) => {
        pane(g, -10, y, 4, 4);
        g.moveTo(-3, y + 2); g.lineTo(10, y + 2);
      });
    },
  };

  function drawIcon(g, id, x, y, px, on) {
    const color = ICON[id] || "#dce6f2";
    const glow = g.createRadialGradient(x, y, px * 0.05, x, y, px * 1.05);
    glow.addColorStop(0, rgba(color, on ? 0.5 : 0.32));
    glow.addColorStop(1, rgba(color, 0));
    g.fillStyle = glow;
    g.beginPath();
    g.arc(x, y, px * 1.05, 0, Math.PI * 2);
    g.fill();
    g.save();
    g.translate(x, y);
    g.scale(px / 24, px / 24);
    g.lineWidth = on ? 1.9 : 1.55;
    g.lineCap = "round";
    g.lineJoin = "round";
    g.strokeStyle = on ? "#ffffff" : color;
    if (id === "destatis") {
      [[-10, 1, 5, 8, "#7ddeb0"], [-2.5, -5, 5, 14, "#67d4ff"], [5, -10, 5, 19, "#8eb6ff"]].forEach(([bx, by, bw, bh, c]) => {
        g.beginPath(); pane(g, bx, by, bw, bh); g.strokeStyle = on ? "#ffffff" : c; g.stroke();
      });
    } else if (id === "districts") {
      const ramp = ["#6f8cff", "#8eb6ff", "#5ee0d0", "#7ddeb0", "#f0c14b", "#f0b46a", "#ff8a6a", "#ff9aa8", "#d2a8ff"];
      let i = 0;
      for (let r = 0; r < 3; r++) {
        for (let c = 0; c < 3; c++) {
          g.beginPath(); pane(g, -10 + c * 7, -10 + r * 7, 5.2, 5.2);
          g.strokeStyle = on ? "#ffffff" : ramp[i++]; g.stroke();
        }
      }
    } else if (id === "site") {
      ["#8eb6ff", "#7ddeb0", "#f0c14b", "#d2a8ff"].forEach((c, i) => {
        const col = i % 2;
        const row = i < 2 ? 0 : 1;
        g.beginPath(); pane(g, -10 + col * 12, -10 + row * 12, 8, 8);
        g.strokeStyle = on ? "#ffffff" : c; g.stroke();
      });
    } else {
      g.beginPath();
      (GLYPH[id] || GLYPH.api)(g);
      g.stroke();
    }
    g.restore();
  }
  const stage = () => document.getElementById("system-stage");
  const canvas = () => document.getElementById("system-canvas");

  function project(p, w, h) {
    const cy = Math.cos(rotY);
    const sy = Math.sin(rotY);
    const cx = Math.cos(rotX);
    const sx = Math.sin(rotX);
    const px = p.x * 0.62;
    const py = p.y * 0.62;
    const pz = p.z * 0.78;
    const x1 = px * cy - pz * sy;
    const z1 = px * sy + pz * cy;
    const y2 = py * cx - z1 * sx;
    const z2 = py * sx + z1 * cx;
    const s = (720 / (720 + z2)) * zoom;
    return { x: w / 2 + x1 * s, y: h / 2 + y2 * s * 0.92, s, z: z2 };
  }

  function paintDetail() {
    const node = byId[selected];
    const box = document.getElementById("system-detail");
    if (!box || !node) return;
    box.innerHTML = `<span class="system-k">${t(GROUPS.find((g) => g[0] === node.group)[1])}</span><b>${t(node.label)}</b><p>${t(node.blurb)}</p>`;
  }

  function paintLegend() {
    const box = document.getElementById("system-legend");
    if (!box) return;
    box.innerHTML = GROUPS.map(([, name, hint, color]) => `<span><i style="background:${color}"></i><b>${t(name)}</b><em>${t(hint)}</em></span>`).join("");
  }

  function frame() {
    const c = canvas();
    const host = stage();
    if (!c || !host) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = host.clientWidth;
    const h = host.clientHeight;
    if (c.width !== Math.floor(w * dpr) || c.height !== Math.floor(h * dpr)) {
      c.width = Math.floor(w * dpr);
      c.height = Math.floor(h * dpr);
    }
    const g = c.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const bg = g.createRadialGradient(w * 0.5, h * 0.45, 40, w * 0.5, h * 0.5, Math.max(w, h) * 0.72);
    bg.addColorStop(0, "#172033");
    bg.addColorStop(1, "#0c111a");
    g.fillStyle = bg;
    g.fillRect(0, 0, w, h);

    const pts = stars.map((p) => project(p, w, h)).sort((a, b) => a.z - b.z);
    pts.forEach((p) => {
      g.globalAlpha = 0.18 + p.s * 0.25;
      g.fillStyle = "#d5deee";
      g.beginPath();
      g.arc(p.x, p.y, Math.max(0.4, p.s * 1.1), 0, Math.PI * 2);
      g.fill();
    });
    g.globalAlpha = 1;

    const placed = NODES.map((n) => ({ n, p: project(n, w, h) }));
    const at = Object.fromEntries(placed.map(({ n, p }) => [n.id, p]));
    GROUPS.forEach(([id, name, , color]) => {
      const members = placed.filter(({ n }) => n.group === id);
      if (!members.length) return;
      let minX = Infinity;
      let maxX = -Infinity;
      let minY = Infinity;
      let maxY = -Infinity;
      members.forEach(({ p }) => {
        minX = Math.min(minX, p.x);
        maxX = Math.max(maxX, p.x);
        minY = Math.min(minY, p.y);
        maxY = Math.max(maxY, p.y);
      });
      const pad = 28;
      g.save();
      g.strokeStyle = color;
      g.globalAlpha = 0.45;
      g.lineWidth = 1;
      g.beginPath();
      g.roundRect(minX - pad, minY - pad - 6, maxX - minX + pad * 2, maxY - minY + pad * 2 + 10, 12);
      g.stroke();
      g.globalAlpha = 1;
      g.font = "600 10px Inter, sans-serif";
      g.fillStyle = color;
      g.textAlign = "left";
      g.fillText(t(name).toUpperCase(), minX - pad + 8, minY - pad + 6);
      g.restore();
    });
    g.lineCap = "round";
    EDGES.forEach(([a, b]) => {
      const p = at[a];
      const q = at[b];
      const dx = q.x - p.x;
      const dy = q.y - p.y;
      const len = Math.hypot(dx, dy) || 1;
      const sign = ((a.charCodeAt(0) + b.charCodeAt(0)) % 2 ? 1 : -1);
      const bend = Math.min(22, len * 0.09) * sign;
      const cx = (p.x + q.x) / 2 + (-dy / len) * bend;
      const cy = (p.y + q.y) / 2 + (dx / len) * bend;
      const lit = a === selected || b === selected;
      const grad = g.createLinearGradient(p.x, p.y, q.x, q.y);
      grad.addColorStop(0, rgba(ICON[a], lit ? 0.35 : 0.16));
      grad.addColorStop(0.5, rgba(ICON[b], lit ? 0.7 : 0.38));
      grad.addColorStop(1, rgba(ICON[b], lit ? 0.95 : 0.62));
      g.strokeStyle = grad;
      g.lineWidth = lit ? 1.8 : 1.15;
      g.beginPath();
      g.moveTo(p.x, p.y);
      g.quadraticCurveTo(cx, cy, q.x, q.y);
      g.stroke();
    });

    const taken = [];
    placed.sort((a, b) => a.p.z - b.p.z).forEach(({ n, p }) => {
      const on = n.id === selected;
      const px = 22 * Math.max(0.82, Math.min(1.45, p.s));
      drawIcon(g, n.id, p.x, p.y, px, on);
      const label = t(n.label);
      g.font = `${on ? 600 : 500} ${Math.max(11, 12 * Math.min(1.2, p.s))}px Inter, sans-serif`;
      const tw = g.measureText(label).width;
      const top = p.y - px / 2 - 16;
      const box = { x: p.x - tw / 2 - 3, y: top, w: tw + 6, h: 15 };
      const clear = on || !taken.some((b) => box.x < b.x + b.w && b.x < box.x + box.w && box.y < b.y + b.h && b.y < box.y + box.h);
      if (clear) {
        taken.push(box);
        g.fillStyle = on ? "#ffffff" : (ICON[n.id] || "#eef2f8");
        g.textAlign = "center";
        g.fillText(label, p.x, p.y - px / 2 - 5);
      }
    });
  }

  function hit(ev) {
    const c = canvas();
    const rect = c.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const y = ev.clientY - rect.top;
    const w = rect.width;
    const h = rect.height;
    let best = null;
    let bestD = 20 * zoom;
    NODES.forEach((n) => {
      const p = project(n, w, h);
      const d = Math.hypot(p.x - x, p.y - y);
      if (d < bestD) { best = n.id; bestD = d; }
    });
    return best;
  }

  function bind() {
    const c = canvas();
    if (!c || c.dataset.bound) return;
    c.dataset.bound = "1";
    let drag = null;
    const pointers = new Map();
    let pinch = null;
    const clampZoom = (z) => Math.max(0.55, Math.min(2.8, z));
    c.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      zoom = clampZoom(zoom * Math.exp(-ev.deltaY * 0.0014));
      frame();
    }, { passive: false });
    c.addEventListener("pointerdown", (ev) => {
      pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
      c.setPointerCapture(ev.pointerId);
      if (pointers.size === 1) drag = { x: ev.clientX, y: ev.clientY, rotY, rotX, moved: false };
    });
    c.addEventListener("pointermove", (ev) => {
      if (!pointers.has(ev.pointerId)) return;
      pointers.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
      if (pointers.size >= 2) {
        const [a, b] = [...pointers.values()];
        const dist = Math.hypot(a.x - b.x, a.y - b.y);
        if (!pinch) pinch = { dist, zoom };
        zoom = clampZoom(pinch.zoom * (dist / pinch.dist));
        drag = null;
        frame();
        return;
      }
      if (!drag) return;
      const dx = ev.clientX - drag.x;
      const dy = ev.clientY - drag.y;
      if (Math.hypot(dx, dy) > 3) drag.moved = true;
      rotY = drag.rotY + dx * 0.005;
      rotX = Math.max(-0.6, Math.min(0.7, drag.rotX + dy * 0.004));
      frame();
    });
    c.addEventListener("pointerup", (ev) => {
      pointers.delete(ev.pointerId);
      pinch = null;
      if (drag && !drag.moved) {
        const id = hit(ev);
        if (id) { selected = id; paintDetail(); frame(); }
      }
      drag = null;
    });
    c.addEventListener("pointercancel", (ev) => {
      pointers.delete(ev.pointerId);
      pinch = null;
      drag = null;
    });
  }

  window.CG_SYSTEM = {
    start() {
      bind();
      paintLegend();
      paintDetail();
      frame();
    },
    resize() { frame(); },
    relabel() { paintLegend(); paintDetail(); frame(); },
  };
})();
