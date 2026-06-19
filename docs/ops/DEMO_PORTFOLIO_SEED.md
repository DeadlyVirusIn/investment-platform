# Demo portfolio seed + why the old shared book no longer appears

## Why "My Portfolio" can look empty now (and that's correct)

Before commit `af4b158`, a device with **no book of its own** silently fell back
to a **shared demo portfolio** ("Replay Recovery Account",
`166b12ed-…`, ~29 positions). So a brand-new user saw *someone else's* 29
positions in My Portfolio — confusing and not theirs.

`af4b158` fixed this: `GET /paper/canonical/stock` now **get-or-creates the
caller's own `user:<device-id>:stock` book** (and the read + write endpoints use
the same resolver). A cold device therefore gets an **empty personal portfolio**
— never the shared book. "No practice positions yet" on a fresh device is the
**correct** state, not a regression.

- The shared Replay Recovery book is reserved for **anonymous/legacy callers**
  (requests with no `X-Auth-User-Id` header). The web app always sends a device
  id, so it never shows the shared book.
- Legacy `Follow:*` books (some with a null `user_id`) created before per-user
  isolation are **not migrated automatically** and are **not** shown in My
  Portfolio. Migrating them is a separate, explicit opt-in.

## Seed a demo device (dev/demo only)

To make My Portfolio look populated for a demo, seed a specific device id:

```
python -m scripts.seed_demo_portfolio --device-id <your-device-id>
```
Options:
```
--api http://localhost:5173            # API base
--symbols AAPL,MSFT,NVDA,AMZN          # 3–5 single-stock adds
--portfolio steady-compounders         # one model portfolio to follow
--usd 1000                             # USD per single-stock add
```

It drives the real API endpoints with that device id, so it goes through the
exact per-user resolution:
1. adds the single-stock positions into `user:<id>:stock`, and
2. follows one model portfolio, which **merges into the same canonical book**
   (post `af4b158`).

**Find your device id** in the browser console:
```
localStorage.getItem('arthos_device_id')
```
then seed that id and refresh.

Safety: touches **only** the device id you pass; no other user portfolios; no
legacy migration; no direct DB writes; no shared-fallback reintroduced.
