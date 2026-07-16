# Paper-surface authorization matrix

Branch `security/paper-surface-ownership` @ `a90a676`. Read-only inventory
(Haiku scouts + orchestrator verification). Production reality established
first-hand: `config` ships `DEMO_DEVICE_MODE=False` and `AUTH_DISABLED_LOCAL=
False`, so `resolve_identity` (`apps/api/src/auth/identity.py:295`) returns
`None` for any caller **without a session cookie** — the `X-Auth-User-Id` device
header the frontend sends is honored **only in dev/demo mode**.

## Consequence (the load-bearing fact)

- Paper **mutation** via `model_portfolios` (`/idea/{symbol}/add-to-paper`,
  `/{slug}/follow`) uses `require_user_id` → **401 for anonymous in production**.
  The anonymous device-book seen in the UX audit was a **dev-mode artifact**;
  production already requires login to touch paper.
- The real breach is `apps/api/src/api/paper.py` (`/api/paper/portfolios*`):
  **zero auth, zero identity derivation** — anyone can list every book (names
  include `user:<uid>`), create arbitrarily-named books, and submit trades /
  snapshots to any `portfolio_id`. The current live V2 app does **not** call it
  (only dead, unrouted legacy `apps/web/src/lib/hooks.ts` + `PaperPortfolio.tsx`
  do; `App.tsx:31` routes `/*` → V2App).
- Read leaks: `performance_paper.py` risk-dashboard and `paper_live.py` live-nav
  scan `paper_portfolio WHERE is_active` with **no user-book exclusion**, so an
  anonymous request receives `user:<uid>` book names + holdings.

## Portfolio scopes (server-derived; client never selects a raw book)

| Scope | Definition | Source of truth |
|-------|-----------|-----------------|
| `user` | a signed-in user's own book | name `user:<uid>:stock`, created only by `resolve_user_stock_portfolio` keyed to the session uid |
| `demo` / `canonical` | the shared read-only demo book | `settings.CANONICAL_STOCK_PORTFOLIO_ID` |
| `model` | published model portfolios | `model_portfolio.is_published` |
| `engine` | engine-tradable books | active, `name NOT LIKE 'user:%'` (`engine_tradable_portfolios_stmt`) |
| `admin` | owner | `admin_guard` role/allowlist |
| `guest` | **does not exist server-side today** | proposed in the design decision (needs migration) |

## Endpoint matrix (condensed; leak/mutation risk in **bold**)

### `apps/api/src/api/paper.py` — `/api/paper/portfolios*` (CRITICAL, unused by live V2)
| Route | Method | Auth today | Identity | Risk |
|-------|--------|-----------|----------|------|
| `/paper/portfolios` | GET | **none** | none | **enumerates ALL books incl. `user:<uid>` names + equity** |
| `/paper/portfolios` | POST | **none** | none | **arbitrary book creation (name preclaim of `user:<victim>:stock`)** |
| `/paper/portfolios/{id}` | GET | **none** | client `id` | **IDOR read of any book** |
| `/paper/portfolios/{id}/trade` | POST | **none** | client `id` | **IDOR write — trade into any book** |
| `/paper/portfolios/{id}/trades` | GET | **none** | client `id` | **IDOR read; returns portfolio name** |
| `/paper/portfolios/{id}/equity` | GET | **none** | client `id` | **IDOR read** |
| `/paper/portfolios/{id}/snapshot` | POST | **none** | client `id` | **IDOR write** |

### `apps/api/src/api/paper_executed.py` — gated in prior sprint (`164415f`)
| Route | Auth | Note |
|-------|------|------|
| `/paper/executed/{summary,trades,positions}`, `/paper/closed-recommendations` | `_require_readable_portfolio` (owner unrestricted; else portfolio_id required, own/non-user only) | **still returns raw `portfolio_name`** → redaction gap |

### `apps/api/src/api/paper_canonical.py`
| Route | Auth | Note |
|-------|------|------|
| `/paper/canonical/stock` | optional; `resolve_identity`→own book, else shared demo | returns `book_scope`; **returns raw `name`** → redaction gap |

### Read-only public surface with **user-book leaks**
| Route | File:line | Leak |
|-------|-----------|------|
| `/performance/paper/risk-dashboard` | `performance_paper.py:3192` | **`concentration_by_portfolio` emits `user:<uid>` names**, no exclusion |
| `/paper/live-nav` | `paper_live.py:113` | **per-portfolio `id`+`name` incl. user books** |
| `/performance/paper/*` (summary/trades/equity/attribution/…) | `performance_paper.py` | aggregate reads; acceptable if no per-user name emitted — audit each for `portfolio_name` |
| `/paper/funnel/*`, `/paper/runs/*` | — | no identity input, no name emission — low |

### Write paths that are already correct
| Route | Auth | Note |
|-------|------|------|
| `/model-portfolios/{slug}/follow`, `/idea/{symbol}/add-to-paper` | `require_user_id` (session only; 401 anon) | writes only to caller's own `user:<uid>:stock`; **preserve** |
| worker `run_paper_trading` etc. | `engine_tradable_portfolio_ids` (excludes user books) | P1 2026-07-08 fix — **preserve** |

## Identifier policy (violations to fix)

No public response may emit `user:<uid>`, internal owner ids, engine-private
book names, or raw DB portfolio keys. Current emitters of raw `portfolio_name`:
`paper.py` (all), `paper_executed.py` (trades/positions/closed-recs),
`paper_canonical.py`, `performance_paper.py` risk-dashboard + pending-fills,
`paper_live.py`. Fix = a single server-side redaction helper mapping internal
names → safe display labels (`"Your practice book"`, `"Demo book"`, model
slug/title, or an opaque token), applied at every emission point; user-book
aggregates excluded from anonymous cross-portfolio views.
