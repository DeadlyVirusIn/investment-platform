#!/usr/bin/env bash
# Smoke test for /api/market/events.
#
# Calls the multi-symbol endpoint for AAPL/MSFT/NVDA and prints the
# count of filings / news / earnings / options_expirations per symbol,
# plus the live provider availability map.
#
# Usage:
#   ./scripts/smoke_market_events.sh                          # default base
#   API_BASE=http://localhost:8000 ./scripts/smoke_market_events.sh
#   ./scripts/smoke_market_events.sh AAPL,TSLA,NVDA           # custom syms
#
# Exits 0 on HTTP 200 + parseable JSON. Exits 1 otherwise.

set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
SYMBOLS="${1:-AAPL,MSFT,NVDA}"
URL="${API_BASE}/api/market/events?symbols=${SYMBOLS}"

echo "GET ${URL}"
echo

# Fetch + count + format in a single Python process — works on
# any OS where python is on PATH (no /tmp dependency).
python - "${URL}" <<'PYEOF'
import json, sys, urllib.request

url = sys.argv[1]
try:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if r.status != 200:
            print(f"HTTP {r.status} — endpoint failed")
            sys.exit(1)
        d = json.loads(r.read().decode("utf-8"))
except Exception as exc:
    print(f"Request failed: {exc}")
    sys.exit(1)

provs = d.get("providers", {})
print("providers:")
for k, v in provs.items():
    flag = "ON " if v else "off"
    print(f"  {flag}  {k}")
print(f"generated_at: {d.get('generated_at', '?')}")
print()
print(f"{'symbol':<8} {'filings':>8} {'news':>6} {'earnings':>9} {'expir':>6}")
print("-" * 42)
for sym, ev in d.get("symbols", {}).items():
    print(
        f"{sym:<8} "
        f"{len(ev['filings']):>8} "
        f"{len(ev['news']):>6} "
        f"{len(ev['earnings']):>9} "
        f"{len(ev['options_expirations']):>6}"
    )
PYEOF
