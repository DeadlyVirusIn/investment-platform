# ArthOS — Security Hardening Backlog (P3)

Tracking-only. Open P3 follow-ups from [SECURITY_AUDIT.md](SECURITY_AUDIT.md)
(audit passed, release gate PASS at commit `15d7db6`). None block the small
external beta. **Do not implement without a scoped, approved sprint** — each has
stop conditions below.

---

## SEC-P3-1 — paper/executed session-ownership filter

- **Severity:** P3 (low — not exploitable today)
- **Surface:** `GET /api/paper/executed/trades?portfolio_id=…` (`api/paper_executed.py`)
- **Rationale:** the endpoint filters by `portfolio_id` (parameterized, no SQLi)
  but does **not** verify the caller owns that portfolio — a classic IDOR shape.
- **Risk (why P3, not higher):** `portfolio_id` is a v4 UUID — unguessable, not
  enumerable, and not exposed except the caller's own book (from
  `/paper/canonical/stock`) and the intentionally public canonical/demo book.
  No real-money or PII data in paper trades. Practical exploitation requires
  knowing another user's exact UUID, which isn't disclosed anywhere.
- **Proposed fix:** when a session resolves to a user, restrict results to
  portfolios that user owns **OR** the public canonical portfolio
  (`settings.CANONICAL_STOCK_PORTFOLIO_ID`). Anonymous callers keep canonical-only.
  Add an integration test: user A cannot read user B's `portfolio_id`; canonical
  + own book still readable; logged-out canonical still works.
- **Dependencies:** confirm the ownership column/join on `paper_portfolio`
  (user_id linkage); confirm which surfaces pass which `portfolio_id`.
- **Stop conditions / must-not-break:** the **public reviewer proof** + the
  **logged-out canonical book** must still return data (ReviewerProof / ProofPulse
  depend on the canonical portfolio being readable while anonymous). Do not gate
  the canonical/demo book behind auth. Design + review before implementing.

## SEC-P3-2 — move hardcoded owner/operator email to env/config

- **Severity:** P3 (low — PII, not a credential)
- **Surface:** `api/v2_promotion.py:47` hardcodes `kunalkhurana1@gmail.com`
  (operator allowlist); migration `108_app_user_role.py` references it as the
  one-time bootstrap backfill.
- **Rationale:** an owner email in source is PII coupling + drift risk, though
  not a secret leak (privacy grep is clean of credentials/keys/tokens).
- **Proposed fix:** read the `v2_promotion` operator allowlist from
  `settings`/env (reuse the `ARTHOS_OWNER_EMAILS` pattern or a dedicated
  `ARTHOS_OPERATOR_EMAILS`). Leave migration 108 as-is (a historical one-time
  backfill literal is acceptable and already applied; rewriting an applied
  migration is worse than leaving it). The **durable DB `access_role='owner'`**
  remains the source of truth either way.
- **Dependencies:** none beyond the existing config loader.
- **Stop conditions / must-not-break:** the DB owner role + env owner allowlist
  must keep working (owner stays owner; non-owner stays 404). Never log or
  serialize the env value. Do not weaken the `require_owner` dual-source guard.

## SEC-P3-3 — optional later hardening (watch-items)

- **Health version disclosure** (P3-info): `/api/health` returns
  `version: 1.0.0-beta`. Standard, low-value to an attacker. *Action:* optionally
  drop the version field if a stricter posture is wanted; no fix needed for beta.
- **CSRF tokens** (P3, conditional): state-changing endpoints are protected by
  `SameSite=Lax` cookies + session design. *Trigger to implement:* only if a
  cross-site form-POST flow or a non-Lax cookie is ever introduced.
- **App-level request body-size cap** (P3, conditional): body size is currently
  bounded by Cloudflare/reverse-proxy limits. *Trigger to implement:* if the edge
  protection is removed or a direct-origin path is added, add an app/uvicorn
  body-size limit.

---

## Status

| ID | Item | Severity | Blocks beta? | State |
|----|------|----------|--------------|-------|
| SEC-P3-1 | paper/executed ownership filter | P3 | No | open — design-first |
| SEC-P3-2 | owner email -> env | P3 | No | open |
| SEC-P3-3 | health version / CSRF / body-cap | P3 | No | watch-items (conditional) |

No P0/P1/P2 open. Beta cleared. Pick up SEC-P3-1 / SEC-P3-2 in a dedicated,
approved hardening sprint with the stop conditions above.
