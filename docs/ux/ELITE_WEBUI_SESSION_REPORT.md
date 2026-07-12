# Elite WebUI Session Report — 2026-07-11

Branch: `feature/elite-arthos-provable-ideas`. Production untouched — no
deploy, no prod flags, no migrations, no recommendation-logic change.

## What ran

- Full local stack: elite-branch API (uvicorn, auth enabled, dev DB at
  migration 118) + vite dev web. Audited signed-out, signed-in non-owner,
  and owner sessions at 1440×900 and 390×844, spot 200 % zoom.
- Audit: `docs/ux/ELITE_WEBUI_AUDIT.md` — 2 CRITICAL, 9 HIGH, 8 MEDIUM,
  5 POLISH. **All CRITICAL and HIGH items fixed and verified live.**

## Fixes shipped (commits, oldest first)

| Commit | Scope |
|--------|-------|
| `fe915d4` | Audit doc + primitives: `freshness.ts`, `EvidenceBadge`, `StatusPanel` |
| `39a4443` | C1/C2/H5 — truthful freshness labels; "Meets the buy bar" default copy; plain-English why-line on every idea card |
| `2b90781` | H1/H2 — share precision (2 dp); age-aware amber snapshot status |
| `e38f825` | H4/H9 — Trust Center humanized (grouped, explained rows, badges, raw JSON behind disclosure, owner-only state panel) |
| `4c49901` | H6/H7 — onboarding why-we-ask + radiogroup semantics + progress; account trust panel + show-password + recovery-oriented errors |
| `00c515b` | H3/H8 — ticker aria-hidden + SR summary; logo → /discover |

## Reusable components created

`v2/components/ui/EvidenceBadge.tsx` (six honesty states, glyph + text +
meaning, never color-only), `v2/components/ui/StatusPanel.tsx`
(info/success/warn/error; what happened / anything lost / what next),
`v2/lib/freshness.ts` (single truthful freshness mapping),
`plainText.ideaOneLiner()` (beginner why-line fallback).

## Verification evidence

- `npx tsc --noEmit` — clean. `npm run lint` (eslint, max-warnings 0) — clean.
- `npm run build` (copy-lint + tsc + vite production build) — green.
- `npm run lint:portfolio` — RED, **pre-existing**: fails identically on
  clean HEAD (6 violations, e.g. PickPage PaperExplainer localStorage);
  not introduced by this pass, tracked as backlog.
- No frontend unit-test runner exists (`npm test` is a placeholder) — noted.
- Live route smokes (dev app, real API): discover / pick / portfolio /
  account / profile / learn / admin / admin-trust-center — no new console
  errors (one pre-existing 404 resource on pick page).
- Live behavioral proof: GE idea shows "MEETS THE BUY BAR · UPDATED
  YESTERDAY" consistent with its Jul 10 as-of; add-to-paper success flow
  produced "2.80 SHARES" position; 3-day-old engine book shows the amber
  "Snapshot from Jul 8 — 3 days old" panel.
- Screenshots: `docs/ux/screenshots/elite-webui/` (10 files: discover
  desktop+mobile, idea detail desktop+mobile, portfolio empty + stale
  states, Trust Center, onboarding mobile, account, learn mobile). The
  signed-in shots use the synthetic audit account
  `elite-audit@example.com` (sanitized; no real PII, IDs, tokens, or raw
  JSON visible). Research Inbox has no UI surface yet (audit M5) — no
  screenshot possible.

## Dev-DB artifacts created during audit (removable)

- `app_user` rows: `elite-audit@example.com` (access_role=owner) and
  `local-dev` promoted to owner — **dev DB only**, revert with
  `UPDATE app_user SET access_role='user' WHERE id='local-dev';`
  `DELETE FROM app_user WHERE email='elite-audit@example.com';` (cascade
  of its practice book as preferred).
- One GE paper position ($1,000) in the audit user's practice book.

## Remaining backlog (MEDIUM/POLISH — see audit doc)

M1 placeholder-scale ticker values · M2 signed-out canonical-book
labeling · M3 "what changed" narrative (needs backend delta contract) ·
M4 Briefing/TrackRecord layout parity · M5 Research Inbox UI · M6 options
vocabulary pass · M7 route error boundary · M8 Ctrl+K hint · P1–P5.

## Staged promotion recommendation

WebUI changes are flag-safe and additive; the only behavior default that
changed is presentation copy ("Meets the buy bar") — owner-approved
wording, reversible via `VITE_MEETS_BUY_BAR=0`. Recommend riding the
existing PRODUCTION_PROMOTION_PLAN stages: web-only image rebuild after
Stage B unblocks; re-verify `/admin/trust-center` against the prod API
(needs elite API code in the prod image before the route exists).
