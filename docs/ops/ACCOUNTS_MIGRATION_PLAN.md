# Accounts + Personalization — Phase 1 Audit & Phase 2–6 Plan

**Date:** 2026-06-20 · P0 before Oracle/public beta. Phase 1 audits the current identity/portfolio model; Phases 2–6 are designed to decision level (not yet implemented). Security-critical: the invariant is **no user ever sees another user's portfolio.**

## Phase 1 — Current state (audited)

### Current identity → portfolio flow (stateless, device-based)
1. Browser generates `arthos_device_id` (UUID) on first load → `localStorage` (`apps/web/src/lib/api.ts:19-31`).
2. Every request sends `X-Auth-User-Id: <device-id>` (`api.ts:33-35`); fallback `'anon'`.
3. Backend reads the header (no middleware); `GET /api/paper/canonical/stock` (`paper_canonical.py:45-170`).
4. `resolve_user_stock_portfolio(db, uid[:64])` (`paper_service.py:98-130`) get-or-creates a book named `user:<device-id>:stock`. No header → anonymous → `CANONICAL_STOCK_PORTFOLIO_ID` (`166b12ed`, Replay Recovery).
5. `get_current_user()` (`auth/resolver.py:225-239`) resolves *tier* from `app_user`+`subscription`; identity is just the header value.

**Verdict:** isolation per device works, but identity is **client-controlled and spoofable** — not real auth. No session, no login, no stable user identity.

### What EXISTS vs DORMANT vs MISSING
- **Live:** device-id header; per-device portfolio isolation; `subscription` tier resolver; `/api/auth/me`, `/api/auth/orgs`.
- **Dormant (schema exists, zero code):** `app_user` (id/email/display_name/`auth_provider`/`external_auth_id`/`disabled_at` — **no password column**), `user_account` (`persona` default 'novice', `starting_paper_balance`, `paper_only`), `user_paper_position`/`user_paper_trade`/`user_visit_log`. Migrations `060_auth_subscription_org.py`, `078_phase_l_user_accounts.py`.
- **Missing:** password storage, login/signup/logout endpoints, session/cookie/JWT, bcrypt/passlib, OAuth adapters, any per-user recommendation personalization, any `user_profile` table, server-synced prefs (`v2-prefs` is localStorage-only).
- **Demo assets:** device `305fcf0b…` → book `bc207e65…` (seeded clone); shared `166b12ed…` for anonymous; legacy `Follow:*` books (some `user_id NULL`, hidden from My Portfolio).

The intended swap point is explicit: `auth/resolver.py` comment — "Real JWT/session auth is intentionally deferred — the abstraction lives here so a future swap is one-file."

---

## Phase 2 — MVP Accounts (design)

**Reuse `app_user`; add the missing pieces via one additive migration.**

- **Migration (additive, non-destructive):** add `app_user.password_hash text NULL`; new table `user_session (token text PK, user_id FK app_user, created_at, expires_at, revoked_at NULL)`. No drops, no overwrites.
- **Password hashing:** `passlib[bcrypt]` (add dep) — `bcrypt` hash on signup, verify on login. (Stdlib `hashlib.scrypt` is the dep-free fallback if adding passlib is undesirable.)
- **Sessions:** opaque random token in `user_session`, set as **HttpOnly, Secure, SameSite=Lax cookie** (`arthos_session`). DB-backed so logout/expiry is real (revocable) — simpler + safer than JWT for MVP. Expiry ~30d sliding.
- **Endpoints (new):** `POST /api/auth/signup` (email+password+display_name → create `app_user` + `user_account` + session cookie), `POST /api/auth/login` (verify → session cookie), `POST /api/auth/logout` (revoke session, clear cookie), extend `GET /api/auth/me` to report logged-in identity. Rate-limit + generic errors (no user-enumeration).
- **Identity resolution change (load-bearing):** `get_current_user()` resolves identity in priority order: (1) **valid session cookie → `app_user.id`**; (2) in **dev/demo mode only** (`AUTH_DISABLED_LOCAL=true` or `DEMO_DEVICE_MODE=true`) → `X-Auth-User-Id` device header; (3) else anonymous. Then **all per-user endpoints** call `resolve_user_stock_portfolio(db, <resolved stable id>)` — so a logged-in user always maps to `user:<app_user_id>:stock`, a stable identity. Device id is **never** the long-term identity once logged in.
- **Requirements satisfied:** logged-in user always resolves to own book (stable id); browser/device id demoted to dev/demo-only; demo device still resolves to `bc207e65` while `DEMO_DEVICE_MODE` is on (dev); cross-user isolation preserved by the same name-scoping that already works (now keyed on the unforgeable session-derived id).

## Phase 3 — User investing profile (design)

- **Migration:** `user_profile (user_id PK FK app_user, experience text, risk_comfort text CHECK in (low,medium,high), time_horizon text, goals text[], avoid_sectors text[], interest_sectors text[], style text CHECK in (steady,balanced,growth), options_interest text CHECK in (none,learning,advanced), created_at, updated_at)`.
- **Capture:** beginner-safe onboarding form on signup (frontend), 8 questions exactly as specified. **Endpoints:** `GET /api/user/profile`, `PUT /api/user/profile` (scoped to current user). Server-side stored (replaces the local-only `v2-prefs` for identity-bearing prefs; `v2-prefs` can stay for pure-UI a11y).

## Phase 4 — Personalization layer (design, NO engine rebuild)

- Use the **existing global recommendations as the base pool**; a thin backend function personalizes over them using `user_profile`:
  - **reorder** by fit (risk match via the volatility-family evidence already on each rec; interest_sectors boost; horizon match);
  - **suppress** unsuitable (avoid_sectors; high-volatility names when risk_comfort=low);
  - **gate options** by `options_interest` (none → hide options lane; learning → show read-only; advanced → full);
  - **annotate** each idea: "Why this fits you" / "Why this may not fit you" derived from real profile↔evidence overlap (no fabricated reasons);
  - **honest label** on every still-global idea: *"ArthOS market idea, adjusted for your profile."*
- **Endpoint:** `GET /api/recommendations/personalized` (current user + global pool → reordered/annotated). Frontend Discover consumes it when logged in; falls back to the global list otherwise. No fake personalization — if profile is empty, label says "not yet personalized."

## Phase 5 — Migration / demo safety (design)

- **Do not destroy or overwrite** any demo data. All changes additive (new columns/tables).
- **Demo device `305fcf0b…` / book `bc207e65…`:** stays usable via the dev/demo device-header path (`DEMO_DEVICE_MODE=true` in dev). In prod, device header is ignored for identity → demo device only works in dev/demo.
- **Shared Replay Recovery `166b12ed…`:** remains the anonymous fallback in dev; in prod, anonymous users hit a login wall instead of seeing a shared book (closes the "anonymous sees shared data" path for real users).
- **Legacy `Follow:*` books:** untouched, remain hidden from My Portfolio.

## Phase 6 — Validation (test plan)

Integration tests (pg fixture), mirroring the existing `test_paper_user_portfolio_pg.py` guardrail:
1. **user A ≠ user B:** two sessions resolve to different books; A's reads never return B's rows.
2. **login persists portfolio:** same credentials → same `app_user.id` → same book across sessions/devices.
3. **logout no leak:** revoked session → no user data; anonymous fallback only in dev mode.
4. **new user starts empty:** fresh signup → empty book, 0 positions.
5. **profile saves:** PUT then GET roundtrip equality.
6. **personalization:** given a profile, the personalized endpoint reorders/labels deterministically vs the global list; avoid_sectors suppressed; options gated.
7. **demo device dev-only:** device header resolves a book **only** when `DEMO_DEVICE_MODE`/`AUTH_DISABLED_LOCAL` is set; with it off, header is ignored.
Plus runtime verify: signup → onboarding profile → add-to-paper → logout/login → portfolio persists → personalized Discover copy appears.

## Sequencing & risks

**Milestones (commit after each):** (M1) migration + password/session + signup/login/logout + `get_current_user` swap; (M2) profile table + endpoints + onboarding form; (M3) personalization endpoint + Discover wiring; (M4) tests; (M5) runtime verification + demo-mode flag.

**Risks:** (a) the `get_current_user` identity swap touches every per-user endpoint — must be exhaustive or some endpoint stays device-keyed (leak risk); audit all `X-Auth-User-Id` readers before flipping. (b) Cookie/CORS config for the SPA (SameSite, credentials) must be correct or sessions silently fail. (c) Demo-mode flag must be **off in prod** or device-spoof identity returns. (d) Password/auth security review needed before public beta (rate-limiting, no enumeration, secure cookie flags). (e) `v2-prefs`→server profile migration for existing local onboarding state.

**Recommendation:** implement M1 first in a focused session (it's the security core), behind a `DEMO_DEVICE_MODE` flag so the demo keeps working throughout, with the cross-user isolation test (Phase 6 #1) written **before** flipping identity. Do not ship to Oracle/public until M1+M4 (auth + isolation tests) are green.
