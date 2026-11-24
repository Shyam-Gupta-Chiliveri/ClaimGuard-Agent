#!/usr/bin/env bash
# Capture every view with headless Chrome and print any JavaScript console errors.
# Usage: scripts/screenshots.sh [base-url] [out-dir] [theme] [views...]
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"
OUT="${2:-docs/screenshots}"
THEME="${3:-light}"
shift $(( $# > 3 ? 3 : $# ))
VIEWS=("$@")
[ ${#VIEWS[@]} -eq 0 ] && VIEWS=(overview germany europe fraud triage ml agent methods)
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
mkdir -p "$OUT"
for v in "${VIEWS[@]}"; do
  h=2300
  case "$v" in agent) h=1000 ;; europe) h=1100 ;; fraud) h=1500 ;; triage) h=1500 ;; methods) h=1700 ;; germany) h=2700 ;; ml) h=2350 ;; esac
  suffix=""; [ "$THEME" = "dark" ] && suffix="-dark"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --window-size=1440,$h --virtual-time-budget=9000 --enable-logging=stderr --v=0 \
    --screenshot="$OUT/$v$suffix.png" "$BASE/?theme=$THEME#$v" 2>&1 \
    | grep -E "CONSOLE|Uncaught" | grep -viE "DevTools|preload" | sed "s/^/[$v] /" || true
  echo "saved $OUT/$v$suffix.png"
done
