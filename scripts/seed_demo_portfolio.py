#!/usr/bin/env python3
"""seed_demo_portfolio — populate ONE device's canonical practice book for demos.

DEV/DEMO ONLY. Drives the real, deployed API endpoints over HTTP with the given
device id as the `X-Auth-User-Id` header, so it goes through the exact same
per-user resolution as the app (resolve_user_stock_portfolio → user:<id>:stock).

It:
  - adds 3–5 single-stock practice positions (add-to-paper), and
  - follows one model portfolio, which (post af4b158) merges into the SAME
    canonical book.

Safety:
  - touches ONLY the device id you pass (no other user portfolios),
  - does NOT migrate or read legacy `Follow:*` books,
  - does NOT reintroduce the shared Replay-Recovery fallback,
  - makes no direct DB writes — only the public API endpoints.

Usage:
  python -m scripts.seed_demo_portfolio --device-id <id>
  python -m scripts.seed_demo_portfolio --device-id demo-1 \
      --api http://localhost:5173 --symbols AAPL,MSFT,NVDA,AMZN \
      --portfolio steady-compounders
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def _req(method: str, url: str, device_id: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Auth-User-Id", device_id)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return {"_http_error": e.code, "_detail": e.read().decode()[:200]}
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}


def _book(api: str, device_id: str) -> dict:
    return _req("GET", f"{api}/api/paper/canonical/stock", device_id)


def main() -> int:
    p = argparse.ArgumentParser(description="Seed a demo device's canonical practice book.")
    p.add_argument("--device-id", required=True, help="the device id (X-Auth-User-Id) to seed")
    p.add_argument("--api", default="http://localhost:5173", help="API base URL")
    p.add_argument("--symbols", default="AAPL,MSFT,NVDA,AMZN",
                   help="comma-separated stock symbols to add (3–5)")
    p.add_argument("--portfolio", default="steady-compounders",
                   help="model-portfolio slug to follow (merged into canonical)")
    p.add_argument("--usd", type=float, default=1000.0, help="USD per single-stock add")
    args = p.parse_args()

    api = args.api.rstrip("/")
    did = args.device_id
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()][:5]

    before = _book(api, did)
    print(f"[before] device={did} portfolio_id={before.get('portfolio_id')} "
          f"open_positions={before.get('open_positions_count')} status={before.get('status')}")

    # 1) single-stock adds
    for sym in symbols:
        r = _req("POST", f"{api}/api/model-portfolios/idea/{sym}/add-to-paper",
                 did, {"usd_amount": args.usd})
        ok = "_error" not in r and "_http_error" not in r
        print(f"  add {sym:6} -> {'ok' if ok else r}")

    # 2) follow one model portfolio (merges into the canonical book)
    r = _req("POST", f"{api}/api/model-portfolios/{args.portfolio}/follow", did, {})
    if "_error" in r or "_http_error" in r:
        print(f"  follow {args.portfolio} -> {r}")
    else:
        print(f"  follow {args.portfolio} -> opened {len(r.get('opened', []))} "
              f"(pid {r.get('paper_portfolio_id')})")

    after = _book(api, did)
    print(f"[after]  device={did} portfolio_id={after.get('portfolio_id')} "
          f"open_positions={after.get('open_positions_count')} status={after.get('status')}")

    if (after.get("open_positions_count") or 0) <= (before.get("open_positions_count") or 0):
        print("WARNING: position count did not increase — check API/symbols/price data.")
        return 1
    print("OK: demo book seeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
