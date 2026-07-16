# Paper ownership — design decision

## The reframe (established first-hand, not assumed)

In **production** (`DEMO_DEVICE_MODE=False`, `AUTH_DISABLED_LOCAL=False`), paper
mutation already requires a session cookie (`require_user_id` → 401 anonymous).
There is **no working anonymous paper-mutation funnel in production today** — the
device-header book is a dev-only mechanism. So "don't weaken the anonymous
funnel" cannot mean "preserve anonymous mutation," because that isn't live. It
means: keep the anon → *browse ideas / see the demo book / be nudged to sign
up* experience intact, and don't add friction to signup.

## Options

### Option A — login required for all paper mutation
- Security: strong; no anonymous write surface.
- Simplicity: highest; **zero migration**; matches current prod behavior exactly.
- Acquisition impact: none beyond today (anon already hits 401 → "create a free
  account"). No pre-signup paper continuity (there is none today).

### Option B — one shared demo book, read-only anonymously
- Security: strong. But users can't *try* a paper action before signup at all
  (worse than today, where the UI at least offers the action then converts).

### Option C — guest-scoped paper portfolio (preferred *enhancement*, needs migration)
- Adds a real, secure anonymous try-paper funnel that prod doesn't have.
- Requires: opaque guest identity (HttpOnly `arthos_guest` cookie, random
  token, never the raw value in any response); a **server-derived** guest book
  (client never sends a book id/name); bounded guests; explicit **claim on
  signup** (atomic + idempotent); expiry/retention for abandoned guests; guest
  books excluded from engine selection and from cross-portfolio public reads.
- Needs new persisted facts → **migration required** (schema below).

## Decision

**Two-part delivery.**

**Part 1 — SHIP NOW (zero migration, no approval needed): enforce ownership +
redaction on the existing surface.** Closes every CRITICAL/HIGH (threats 1–7)
and weakens nothing that production does today. This is Option A's enforcement.
Covers minimum-implementation items 1, 3–8 and item 2 in its "no anonymous
mutation" reading.

**Part 2 — DESIGN READY, APPROVAL REQUIRED: Option C guest funnel.** Delivers a
*new* secure anonymous try-paper capability. Requires the migration below; per
mission rules the migration is **not generated** — proposal only, awaiting
explicit owner approval.

Why not force Option C now: robust guest ownership cannot be enforced with
existing persisted facts (there is no server-side guest identity or
guest→owner relation). Faking it with a client-supplied guest id would re-create
the exact IDOR class we are closing. So the honest path is A now, C on approval.

## Proposed schema for Option C (NOT generated — approval gate)

Minimal, additive, reversible:

```
-- guest_session: opaque server-side guest identity
guest_session(
  id            uuid primary key default gen_random_uuid(),  -- internal, never emitted
  cookie_hash   text not null unique,       -- hash of the HttpOnly cookie value (never store raw)
  created_at    timestamptz not null default now(),
  last_seen_at  timestamptz not null default now(),
  claimed_by    uuid null references app_user(id),  -- set once, at claim; then cookie is inert
  claimed_at    timestamptz null
)

-- ownership link for the guest's single paper book (server-derived, bounded to 1)
guest_paper_book(
  guest_session_id uuid primary key references guest_session(id) on delete cascade,
  portfolio_id     text not null unique references paper_portfolio(id),
  created_at       timestamptz not null default now()
)
```

Claim = single transaction: `UPDATE guest_session SET claimed_by=:uid,
claimed_at=now() WHERE id=:gid AND claimed_by IS NULL` (idempotent — 0 rows on
replay), then reassign/merge `guest_paper_book.portfolio_id` into the user's
`user:<uid>:stock` per the conflict policy; audit row records `{event:'claim',
guest_session_id, app_user_id, at}` with **no** raw cookie/uid emitted anywhere.
Retention: reaper deletes `guest_session` rows unclaimed for N days (cascade
drops the book). Bound: one guest book per `guest_session`; rate-limit guest
creation per IP.

Conflict policy (guest book + existing user book at claim): **keep-both by
default** (guest book imported as a dated, labeled secondary practice book) —
never silently overwrite; merge or choose offered later. To be confirmed with
owner at approval.

## Verdict for this document

Part 1 is implementable and reviewable now. Part 2 is **DESIGN READY —
MIGRATION APPROVAL REQUIRED**.
