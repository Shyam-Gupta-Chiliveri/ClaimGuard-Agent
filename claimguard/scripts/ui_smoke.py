"""Browser smoke test for the frontend.

Drives headless Chrome over the DevTools protocol: opens every view in both themes, uses the command
palette, the district explorer, the live triage stream, the claim form and the agent, checks for
JavaScript errors and horizontal overflow, and saves the README screenshots.

    python scripts/ui_smoke.py http://127.0.0.1:8000 docs/screenshots
"""

from __future__ import annotations

import base64
import itertools
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PORT = 9333
VIEWS = ["overview", "germany", "europe", "fraud", "triage", "ml", "agent", "methods"]


class Page:
    def __init__(self, ws):
        self.ws = ws
        self.ids = itertools.count(1)
        self.errors: list[str] = []

    def cmd(self, method: str, **params):
        i = next(self.ids)
        self.ws.send(json.dumps({"id": i, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == i:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})
            self._event(m)

    def _event(self, m: dict) -> None:
        if m.get("method") == "Runtime.exceptionThrown":
            d = m["params"]["exceptionDetails"]
            self.errors.append(d.get("exception", {}).get("description") or d.get("text", "exception"))
        if m.get("method") == "Runtime.consoleAPICalled" and m["params"]["type"] == "error":
            self.errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in m["params"]["args"]))
        if m.get("method") == "Network.requestWillBeSent":
            url = m["params"]["request"]["url"]
            if url.startswith("http") and not url.startswith(BASE):
                self.errors.append(f"third-party request: {url}")

    def js(self, expr: str):
        r = self.cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"{expr}: {r['exceptionDetails'].get('exception', {}).get('description')}")
        return r["result"].get("value")

    def wait(self, expr: str, timeout: float = 20) -> None:
        end = time.time() + timeout
        while time.time() < end:
            if self.js(expr):
                return
            time.sleep(0.2)
        raise TimeoutError(expr)

    def size(self, w: int, h: int, mobile: bool = False) -> None:
        self.cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if mobile else 1, mobile=mobile)

    def open(self, view: str, theme: str = "light") -> None:
        self.cmd("Page.navigate", url="about:blank")  # a hash-only change would not reload the page
        self.cmd("Page.navigate", url=f"{BASE}/?theme={theme}&lang=en#{view}")
        self.wait("document.readyState === 'complete' && !!document.querySelector('.view.active')")

    def settle(self, seconds: float = 0.9) -> None:
        time.sleep(seconds)
        self.js("1")

    def shot(self, name: str) -> None:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_bytes(base64.b64decode(self.cmd("Page.captureScreenshot", format="png")["data"]))
        print(f"  saved {OUT / name}")

    def click(self, selector: str) -> None:
        if not self.js(f"(() => {{ const el = document.querySelector({json.dumps(selector)}); if (!el) return false; el.click(); return true; }})()"):
            raise RuntimeError(f"no element for {selector}")

    def no_overflow(self, label: str) -> None:
        w = self.js("[document.documentElement.scrollWidth, window.innerWidth]")
        check(w[0] <= w[1] + 1, f"{label}: no horizontal overflow ({w[0]} <= {w[1]})")


FAILED: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        FAILED.append(label)


CHARTS_READY = {
    "overview": "document.querySelectorAll('#view-overview canvas').length >= 2 && document.querySelectorAll('#insights .finding').length > 5",
    "germany": "document.querySelectorAll('#view-germany canvas').length >= 6 && !!document.querySelector('#drawer .d-title') && document.querySelectorAll('#de-table tbody tr').length > 100",
    "europe": "document.querySelectorAll('#view-europe canvas').length >= 3",
    "fraud": "document.querySelectorAll('#view-fraud canvas').length >= 2 && document.querySelectorAll('#fraud-cards .lens').length === 7",
    "triage": "document.querySelectorAll('#view-triage canvas').length >= 1",
    "ml": "document.querySelectorAll('#view-ml canvas').length >= 6 && document.querySelectorAll('#ml-registry tbody tr').length >= 2",
    "agent": "document.querySelectorAll('#messages .msg').length >= 1",
    "methods": "document.querySelectorAll('#view-methods table tr').length > 5",
}


def run(p: Page) -> None:
    p.cmd("Page.enable")
    p.cmd("Runtime.enable")
    p.cmd("Network.enable")
    p.size(1440, 1000)

    print("views, light theme")
    for v in VIEWS:
        p.open(v)
        p.wait(CHARTS_READY[v])
        p.settle()
        p.no_overflow(v)
        if v not in ("triage", "agent"):
            p.shot(f"{v}.png")

    print("theme switch repaints every open chart")
    p.open("germany")
    p.wait(CHARTS_READY["germany"])
    p.click("#theme-btn")
    p.settle()
    check(p.js("document.documentElement.dataset.theme") == "dark", "theme is dark after the toggle")
    check(p.js("localStorage.getItem('cg-theme')") == "dark", "theme choice is stored")
    p.shot("germany-dark.png")
    p.js("localStorage.removeItem('cg-theme')")

    print("command palette")
    p.open("overview")
    p.wait(CHARTS_READY["overview"])
    p.js("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))")
    check(p.js("!document.querySelector('#palette').hidden"), "Ctrl K opens the palette")
    p.js("(() => { const i = document.querySelector('#palette-input'); i.value = 'koln'; i.dispatchEvent(new Event('input', { bubbles: true })); })()")
    p.wait("[...document.querySelectorAll('#palette-list .p-item')].some((b) => b.textContent.includes('Köln'))")
    check(True, "typing 'koln' finds Köln")
    p.settle(0.4)
    p.shot("palette.png")
    p.js("document.querySelector('#palette-input').dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))")
    p.wait("location.hash === '#germany/05315' && (document.querySelector('#drawer .d-title')?.textContent || '').includes('Köln')")
    check(True, "Enter opens the district and the link is shareable (#germany/05315)")

    print("district explorer")
    p.js("(() => { const i = document.querySelector('#tb-q'); i.value = 'münchen'; i.dispatchEvent(new Event('input', { bubbles: true })); })()")
    n = p.js("document.querySelectorAll('#de-table tbody tr[data-code]').length")
    check(0 < n < 10, f"filter 'münchen' leaves {n} rows")
    p.js("(() => { const i = document.querySelector('#tb-q'); i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); })()")
    p.click("#de-table th[data-k='share_bev']")
    first = p.js("document.querySelector('#de-table tbody tr td b').textContent")
    check("Wolfsburg" in first, f"sorting by electric share puts {first} first")
    p.click(".map-wrap[data-map='de-map'] [data-zoom='in']")
    check(p.js("echarts.getInstanceByDom(document.getElementById('de-map')).getOption().series[0].zoom") > 1.5, "map zoom button zooms in")
    p.click(".map-wrap[data-map='de-map'] [data-zoom='reset']")
    check(p.js("echarts.getInstanceByDom(document.getElementById('de-map')).getOption().series[0].zoom") == 1, "map reset restores the view")
    p.click("#de-metrics .seg-b[data-k='resid_liability_class_2027']")
    check("disagree" in p.js("document.querySelector('#de-map-title').textContent"), "metric switch updates the map title")

    print("live triage")
    p.open("triage")
    p.wait(CHARTS_READY["triage"])
    p.js("document.querySelector('#tr-speed').value = '8'")
    p.click("#tr-toggle")
    p.wait("document.querySelectorAll('#tr-feed .feed-item').length >= 45", timeout=60)
    p.click("#tr-toggle")
    total = p.js("document.querySelector('#tr-counters .stat b').textContent")
    check(int(total.replace(",", "")) >= 45, f"stream scored {total} claims")
    p.js("(document.querySelector('#tr-feed .feed-item.red') || document.querySelector('#tr-feed .feed-item')).click()")
    p.wait("!!document.querySelector('#tr-result .score-n')")
    p.click("#brief-btn")
    p.wait("(document.querySelector('#brief .brief')?.textContent || '').length > 80")
    check(True, "claim detail shows the score and an investigator brief")
    p.js("document.querySelectorAll('.toast').forEach((t) => t.remove()); window.scrollTo(0, 0)")
    p.settle(0.4)
    p.shot("triage.png")
    p.js("document.querySelectorAll('#tr-form .toggle')[2].click(); document.querySelectorAll('#tr-form .toggle')[0].click(); document.querySelector('[name=days_after_policy_start]').value = 5; document.querySelector('#tr-form').requestSubmit()")
    p.wait("(document.querySelector('#tr-result h3')?.textContent || '').includes('Your claim')")
    check(p.js("document.querySelector('#tr-result .score-n').textContent") == "55", "form claim scores 55 (R1 + R5 + R7)")
    p.click("#brief-btn")
    p.wait("(document.querySelector('#brief .brief')?.textContent || '').length > 80")
    check(True, "brief works for a claim typed into the form")
    p.open("triage/SIM-0373")
    p.wait("(document.querySelector('#tr-result h3')?.textContent || '').includes('SIM-0373')")
    check(True, "claim deep link #triage/SIM-0373 opens the claim")

    print("agent")
    p.open("agent")
    p.wait(CHARTS_READY["agent"])
    p.click("#suggest .chip")
    p.wait("!!document.querySelector('#messages .sources')", timeout=40)
    check(p.js("document.querySelectorAll('#trace .tstep').length") >= 4, "trace lists the plan, tool calls and answer")
    check("Gelsenkirchen" in p.js("document.querySelector('#messages .msg.bot:last-child .bubble').textContent"), "answer mentions Gelsenkirchen and cites sources")
    p.settle(0.4)
    p.shot("agent.png")

    print("dark theme")
    for v in ("overview", "ml", "fraud"):
        p.open(v, "dark")
        p.wait(CHARTS_READY[v])
        p.settle()
        p.shot(f"{v}-dark.png")

    print("phone layout (390 x 844)")
    p.size(390, 844, mobile=True)
    for v in VIEWS:
        p.open(v)
        p.wait(CHARTS_READY[v])
        p.settle(0.6)
        p.no_overflow(f"{v} on a phone")
    p.open("overview")
    p.wait(CHARTS_READY["overview"])
    p.settle()
    p.shot("overview-phone.png")
    p.click("#menu-btn")
    p.settle(0.4)
    check(p.js("document.querySelector('#app').classList.contains('nav-open')"), "menu button opens the navigation")

    print("language toggle")
    p.size(1440, 1000)
    p.open("overview")
    p.wait(CHARTS_READY["overview"])
    p.click("#lang .lang-b[data-lang=de]")
    p.wait("document.documentElement.lang === 'de' && (document.querySelector('#view-overview h1')?.textContent || '').includes('Deutschland')")
    check(True, "DE translates the overview heading")
    for v in VIEWS:
        p.js(f"location.hash = {json.dumps('#' + v)}")
        p.wait(CHARTS_READY[v])
        p.settle(0.3)
    missing = p.js("window.CG_I18N.missing") or []
    check(len(missing) == 0, f"every visible string has a German translation ({len(missing)} missing)")
    for key in missing[:20]:
        print("     missing:", key[:180])
    p.size(390, 844, mobile=True)
    p.settle(0.4)
    p.no_overflow("German pages on a phone")
    p.size(1440, 1000)
    p.click("#lang .lang-b[data-lang=en]")
    p.wait("document.documentElement.lang === 'en'")

    check(not p.errors, f"no JavaScript errors or third-party requests ({len(p.errors)})")
    for e in p.errors[:10]:
        print("     ", e[:300])


def main() -> int:
    profile = tempfile.mkdtemp(prefix="cg-chrome-")
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--remote-debugging-port={PORT}",
         f"--user-data-dir={profile}", "--window-size=1440,1000", "--no-first-run", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        target = None
        for _ in range(50):
            try:
                target = next(t for t in httpx.get(f"http://127.0.0.1:{PORT}/json").json() if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        if target is None:
            print("Chrome did not start")
            return 2
        with connect(target["webSocketDebuggerUrl"], max_size=None) as ws:
            run(Page(ws))
    finally:
        chrome.terminate()
    print(f"\n{'ALL CHECKS PASSED' if not FAILED else f'{len(FAILED)} CHECK(S) FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
