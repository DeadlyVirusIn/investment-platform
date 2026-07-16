# ArthOS Product & UX Audit — 2026-07 (Sprint: feature/arthos-product-ux-hardening)

Audit date: 2026-07-15/16 · Base: `phase-1/ledger` @ `26532b6` · Method: rendered-UI
walkthrough on local stack (API :8002 on dev DB @ migration 121, **all feature flags at
defaults = production-like OFF**; Vite :5199), desktop 1440×900 and mobile 390×844,
fresh isolated browser profile. Evidence: `docs/ux/ux-sprint-202607/screenshots/before/`.

Personas exercised: (1) complete beginner, (4) mobile-only, (5) returning paper user,
(6) landing-with-no-context. Journey: Landing → Signup → Onboarding → Discover →
Pick → Add to paper → Portfolio → Return.

## What is genuinely good (do not regress)

- Welcome overlay and Discover lead with honest positioning: "Nothing real is at
  stake. We don't promise returns." Paper-only framing is consistent and prominent.
- Pick page (`/today/pick/:symbol`) is strong: bulls-vs-bears, "Before you act",
  expected holding period, entry/target/exit-if-wrong with "paper planning estimate —
  not investment advice", audit trail toggle, feedback widget.
- "The honest record" on Discover refuses to show win-rate below 10 closed outcomes.
- `/arth` report card explicitly refuses to manufacture accuracy numbers.
- Model portfolio page discloses survivorship bias on the historical chart.
- Signup is minimal (email+password), rate-limited server-side, HttpOnly cookie.
- Mobile bottom-tab navigation works at 390px; no horizontal scroll observed on the
  audited pages.

## Findings (ranked)

### CRITICAL

**F1 — The committed production web build is broken; prod serves the SPA from a Vite
dev server.**
Evidence: `docker build -f infra/docker/web.Dockerfile .` at `26532b6` fails in
`RUN npm ci` — lockfile out of sync with the builder's npm (node:20-alpine / npm
10.8.2): `Missing: @emnapi/core@… esbuild@0.28.1 from lock file`. Local npm (newer)
fails the same gate with different missing entries: the lockfile satisfies **no** npm
line. Meanwhile `PRODUCTION_REBUILD_REPORT_20260715.md` (line 102) confirms "Web
remains a Vite dev-server pattern in prod". Impact: no deterministic, rollback-
compatible web artifact; prod web = unpinned `node:20-alpine` + `npm install` at
container start (supply-chain and reproducibility risk); dev-mode server semantics in
production. Affected: all users; ops. Fix: regenerate lockfile with the build
environment's npm, pin builder base, wire `web_dist` population into the prod compose
overlay, add health endpoint + cache headers to Caddy. Cost: small. Validation: clean
`docker build`, local static-serve smoke (SPA deep-link, headers, gzip, healthz).
→ Sprint scope **E** (implemented).

### HIGH

**F2 — Pre-signup practice positions silently vanish at signup.**
Evidence: anonymous "Add to paper ($1,000)" on GE succeeds (`POST
/api/model-portfolios/idea/GE/add-to-paper` → 200, device book); the sign-in nudge
promises "Sign in and every idea you add is tracked privately under your own book";
after signup the portfolio is empty ("No practice positions yet") with no explanation
(screenshots 03/04 vs 07). The conversion moment breaks the product's core trust
promise ("A real, auditable track record that grows"). Personas 1, 5, 6. Fix
(zero-migration, honest): tell the user at signup/first-portfolio-view that the
device book stays on the device and the account starts a fresh private book; carry-in
of device positions is a follow-up backend decision. Cost: small. → Sprint scope.

**F3 — Anonymous /portfolio mixes two books in one narrative.**
Evidence: header says "Demo practice portfolio … doesn't belong to you" while the same
page renders the visitor's own device-book position (GE added a minute earlier) under
"You've already added ideas to your practice account" (screenshot 04).
`PaperBook.tsx:90` keys `isDemo` on `!authenticated` but the data hooks return the
visitor's book when one exists. A beginner cannot tell what they own. Fix: derive the
header/narrative from which book is actually displayed. Cost: small. → Sprint scope.

**F4 — Portfolio with positions shows "being prepared" and no book value/cash.**
Evidence: after following Steady Compounders (6 positions), BOOK VALUE section says
"Your practice portfolio is being prepared … values update with the next market
snapshot" while the cards below show live prices and day P&L (screenshot 11). The two
claims contradict; equity/cash totals are absent though position market values are
known. Fix: when positions carry prices, show the derivable summary (sum of market
values; cash if the API supplies it) with an honest "pre-snapshot" label; reserve
"being prepared" for truly price-less states. Cost: small-medium. → Sprint scope.

**F5 — "OPENED Jul 14" on ideas added Jul 15, at a different price than quoted.**
Evidence: GE added Jul 15 at last close $360.35 shows AVG COST $355.60, OPENED Jul 14
(screenshots 04/11) — paper fills anchor to the last completed market bar. Correct
engine behavior, unexplained in UI → reads as a bug and undermines the "auditable"
claim. Fix: label fills as priced at the last market close ("Opened Jul 14 · priced at
last close") once, where OPENED renders. Cost: small. → Sprint scope.

**F6 — Completed onboarding is not reflected back to the user.**
Evidence: immediately after saving the 5 required profile answers, `/me` → "What
you've told me" still says "Once you finish onboarding, the things you told me … will
live here"; "What I've seen you do" ignores the model-portfolio follow performed
minutes earlier (screenshot 12). The relationship page opens by contradicting the
relationship. Fix (smallest): render saved profile answers (GET /api/profile) in
"What you've told me"; leave behavioral sections gated on observations. Cost: medium.
→ Sprint scope (profile reflection only).

### MEDIUM

**F7 — Wrong navigation highlight (prefix matching).**
`/portfolios/:slug` (model portfolio) highlights **My Portfolio**; `/today` highlights
**Discover** while the banner says TODAY. Beginners lose wayfinding. Fix: exact/
segment-aware active matching. Cost: tiny. → Sprint scope.

**F8 — Time expectation mismatch on the very first click.**
Welcome overlay: "Begin Day 1 is a ~5-minute guided lesson"; Start page: "About 27
minutes total" (screenshots 01/02). First-session trust cut. Fix: reconcile copy
(lead with the honest total; per-step minutes already shown). Cost: tiny. → Sprint
scope.

**F9 — "Create a free practice account" CTAs land on Sign-in mode.**
All account CTAs link `/account` which defaults to Sign in; new users must find the
"Sign up" toggle. Fix: support `/account?mode=signup` and point create-account CTAs
at it. Cost: tiny. → Sprint scope.

**F10 — Trust-surface copy drift.**
`/arth` says "Every idea shows a plain confidence level" — Pick page deliberately
shows buy-bar wording instead (owner decision). Discover strip says "accuracy
publishes at 10 closed outcomes"; `/arth` says no number until outcome lineage is
wired. Fix: align `/arth` copy with the buy-bar language and one accuracy-gating
story. Cost: tiny. → Sprint scope.

**F11 — Frontend unconditionally calls flag-off endpoints.**
Every Pick view fires `/api/system/posture`, `/recommendations/:sym/delta`,
`/…/timeline` (404 when flags off) and `/api/admin/overview` fires for every visitor
(owner-nav probe). Console error noise + wasted requests. Fix: feature-detect once per
session (cache 404), or gate on a config endpoint. Cost: medium. → Deferred
(documented; needs a small capability-discovery design, not a page patch).

### LOW

**F12 — Marquee ticker**: duplicated content is aria-hidden-equivalent? A text
fallback exists ("Delayed index quotes: …") which screen readers get — acceptable;
verify `prefers-reduced-motion` stops the marquee. → Backlog.
**F13 — React Router v7 future-flag warnings** in console. → Backlog (opt-in flags).
**F14 — Model-portfolio chart has no text alternative** beyond the caption; add an
aria-label summarizing the series. → Backlog.
**F15 — Possible H1 clipping under the sticky header** on /portfolio (observed in a
full-page capture; not reproduced in viewport captures). → Verify during sprint QA.

## Top-10 priority table

| # | Finding | Sev | Persona hit | Route | Fix cost | In sprint? |
|---|---------|-----|-------------|-------|----------|-----------|
| 1 | F1 prod web build broken / dev server in prod | CRIT | all/ops | infra | S | ✅ E |
| 2 | F2 pre-signup positions vanish silently | HIGH | 1,5,6 | /account, /portfolio | S | ✅ |
| 3 | F3 demo-vs-mine mixed narrative | HIGH | 1,6 | /portfolio (anon) | S | ✅ |
| 4 | F4 "being prepared" + no book value | HIGH | 1,5 | /portfolio | S-M | ✅ |
| 5 | F5 OPENED-date/price anchoring unexplained | HIGH | 1,2,3 | /portfolio | S | ✅ |
| 6 | F6 onboarding answers not reflected on /me | HIGH | 1,5 | /me | M | ✅ |
| 7 | F7 nav active-state prefix bug | MED | 1,4 | chrome | XS | ✅ |
| 8 | F8 5-min vs 27-min | MED | 1,6 | overlay, /start | XS | ✅ |
| 9 | F9 signup CTA lands on sign-in | MED | 1,6 | /account | XS | ✅ |
| 10 | F10 trust-copy drift (/arth) | MED | 3 | /arth | XS | ✅ |

## Comprehension check (persona 1, before sprint)

Can answer: what ArthOS is; that it's paper-only; why the stock is shown; the risks;
what invalidates the idea; holding period. Cannot reliably answer: "where did my
pre-signup idea go" (F2), "what is my portfolio worth / how much cash is left" (F4),
"why does it say opened yesterday" (F5), "did it hear my onboarding answers" (F6),
"where am I in the app" on model-portfolio pages (F7).

## Accessibility notes (spot checks)

Semantic landmarks present (complementary/nav/banner/main); headings hierarchical on
audited pages; onboarding progress uses `aria-live=polite`; form inputs labelled;
buttons named. Not yet audited exhaustively: contrast ratios, 200% zoom reflow,
focus-visible styling across all interactive elements, chart alternatives (F14).
Keyboard: interactive elements are buttons/links (focusable); full tab-order walk
deferred to sprint QA.

## Production WebUI architecture (Phase 2 summary)

Current repo state: dev compose `web` = `node:20-alpine` + bind-mount + `npm install
&& npm run dev` (HMR, polling); prod overlay keeps that service (384m cap) AND runs
Caddy serving `/srv/web` from a `web_dist` volume that must be populated **manually**
(`docker build … && docker cp …` — comment in `docker-compose.prod.yml:64-65`);
`infra/docker/web.Dockerfile` (builder → dist holder) exists but does not build at
HEAD (F1). Public traffic: Caddy :80/:443 + tunnel :8081, gzip/zstd, nosniff/DENY/
referrer headers, no cache policy, no Caddy healthcheck, no web healthz route.
Per the 2026-07-15 rebuild report, live prod "rebuild WebUI" = clean source +
recreate the Vite dev-server container — i.e. the running prod web is the dev server,
NOT the static path (the VM's effective Caddy routing must be confirmed at deploy
time; out of scope for this sprint — no prod access).

Target (smallest production-grade, implemented this sprint on the feature branch,
NOT deployed): deterministic `npm ci` (container-regenerated lockfile) → `vite build`
→ immutable dist image → compose-native one-shot `web-dist` populator into `web_dist`
→ existing Caddy serves static SPA with explicit cache policy (hashed assets
immutable; index.html no-store) + `/healthz` + compose healthcheck. Rollback: retag
previous dist image; Caddy/API untouched. Full plan:
`docs/ops/WEBUI_PRODUCTION_HARDENING_PLAN.md`.
