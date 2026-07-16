# ArthOS UX Hardening Sprint — Report (2026-07-15/16)

Branch: `feature/arthos-product-ux-hardening` (from `phase-1/ledger` @ `26532b6`).
**Not merged, not pushed, not deployed.** Production untouched and frozen at
`7e0af44` / DB `109`. Orchestrated boss-worker: Fable 5 orchestrator; Haiku
scouts; Codex `gpt-5.6-terra` implements in this worktree; Codex `gpt-5.6-sol`
+ Claude `security-reviewer` review; separation of duties enforced.

## Scope chosen

Categories A/B/C/D (first-touch comprehension, recommendation understanding
already strong, paper journey truth, returning-user continuity) + E (production
WebUI hardening). Selected from the audit's top-10 — the coherent
"paper-journey truth + first-touch clarity + shippable static web" cluster, not
a scatter of micro-changes.

## Implemented (7 commits)

| Commit | What | Model | Review |
|--------|------|-------|--------|
| `c19c453` | Regenerate web lockfile with builder npm — `npm ci` was broken at HEAD | orchestrator | Sol APPROVE |
| `2e8de0d`→`5291107`→`176320a` | Paper-journey truth: book narrative from API `book_scope`, honest priced-position estimate (not "book value"), corrected fill-anchoring copy, full neutral-state gating, session-gated queries, nav active-state | terra `019f6aa9`/`019f6bc1` + orchestrator | Sol BLOCK→repaired |
| `51d9fa2` | First-touch: honest Day-1 duration, `/account?mode=signup` + signup CTAs, pre-signup continuity note, `/me` renders saved profile answers, `/arth` buy-bar copy | terra `019f6abc` | Sol APPROVE-WITH-NOTES (LOWs fixed) |
| `164415f` | Gate `/api/paper/executed/*` by book ownership; canonical `book_scope` | terra `019f6bb7` | Claude sec APPROVE-WITH-NOTES; Sol flagged broader surface (escalated) |
| `586b059`→`6b8fa3c`→`176320a` | Compose-native static web: `/opt/dist` one-shot atomic sync, Caddy `/healthz` + cache policy, `!reset` ports, rollout/rollback runbook | terra `019f6ab9` + orchestrator | Sol BLOCK→repaired |

## Findings closed (verified in rendered UI)

- **F1** web build broken / dev-server-in-prod → deterministic `npm ci` + static
  image + atomic publish + Caddy healthz/cache; local serving proof green.
- **F3** demo-vs-own book narrative → keyed on API `book_scope` (screenshots
  `after/A01`, `A03`).
- **F4** "being prepared" + no value → honest priced-position estimate.
- **F5** unexplained opened-date → corrected fill-anchoring note (open of most
  recent trading day).
- **F6** onboarding answers not on `/me` → profile rows rendered (`after/A02`).
- **F7** nav active-state prefix bug → segment-aware (verified: `/portfolios/:slug`
  no longer lights My Portfolio).
- **F8** 5-min vs 27-min → reconciled (`after/A04`).
- **F9** signup CTA → sign-in → `?mode=signup` + CTA links.
- **F2** pre-signup continuity → honest note at signup.
- **F10** `/arth` trust-copy drift → buy-bar wording.
- Plus **security**: 4 previously-public paper read endpoints now
  ownership-gated (net exposure reduction).

## Deferred / escalated (NOT shipped)

- **F11** (frontend calls flag-off endpoints → 404 noise) — needs a small
  capability-discovery design; documented in the audit.
- **Pre-existing paper-surface exposure** (`paper.py` public create/trade/list;
  `performance_paper.py`/`paper_live.py` leak `user:<uid>` book names) — raised
  by both reviewers, **pre-existing in frozen prod**, gating it wrongly breaks
  the anonymous add-to-paper funnel. Escalated with a design decision in
  `docs/ux/PAPER_SURFACE_SECURITY_FOLLOWUP.md`; belongs in `SECURITY_BACKLOG.md`.
- F12–F15 (marquee reduced-motion, RR v7 warnings, chart alt-text, focus-ring
  thinness) — backlog.

## Tests & gates (exact)

- Frontend (`apps/web`): `tsc --noEmit` clean; `eslint --max-warnings 0` clean;
  `lint:copy` pass; `lint:portfolio` pass; `vitest run` **302 passed / 26 files**.
- Backend targeted: `pytest apps/api/tests/unit/test_paper_executed_api.py
  test_paper_canonical_api.py` → **25 passed**.
- Auth gate (docker, PG): `test_accounts_m1_pg.py` + `test_login_rate_limit_pg.py`
  → **18 passed** (after recreating the stale `investment_platform_test` DB).
- Web image: `docker build -f infra/docker/web.Dockerfile` green; one-shot sync
  idempotent, zero temp files; Caddy serving proof — `/healthz` 200, `/` 200
  `no-cache`, `/today/pick/GE` deep-link 200, hashed asset `immutable`+gzip+
  nosniff; Caddy 13.6 MiB vs ~106 MB dev-server.
- Broad backend unit suite: **147 failed / 73 collection errors are PRE-EXISTING**
  — identical on clean base `26532b6` (branch adds only +8 passing tests). Paired
  evidence captured.

## Performance (measured)

- Bundle: 1 JS chunk 888 KB raw / **261 KB gzip**; CSS 291 KB / **48 KB gzip**;
  dist ≈ 1.1 MB. (Single-chunk — a code-splitting pass is a future win, out of
  this sprint's scope.)
- Static Caddy **13.6 MiB** vs production Vite dev-server container **~106 MB
  observed** + the 384 MiB-capped `web` dev service removed entirely in prod.

## Production confirmation

- Production **not touched**; no deploy, no push, no VM action.
- Prod DB remains **109**; no migration generated or applied (sprint is
  zero-migration).
- No production flag enabled.
- 48-hour observation window continues independently.

## Verdict

**PARTIAL — HIGH-VALUE FIXES COMPLETE.** Ten audit findings closed and verified
in the rendered product; production WebUI now has a reviewed, tested, static
path (not deployed); a net security improvement landed on the paper read
surface. One pre-existing paper-authorization exposure and F11 are escalated
with evidence and a recommended next step, per the two-repair-loop rule.

## Next recommended step

Owner decision on the anonymous-paper model, then a dedicated
**backend paper-authorization** branch (security-reviewer + Sol dual review) to
close items 1–3 of `PAPER_SURFACE_SECURITY_FOLLOWUP.md`. Independent of the
frozen-prod observation and Stage-B. The WebUI static path is review-ready for a
separate owner-approved deploy once its VM Caddy-routing precondition is
confirmed.
