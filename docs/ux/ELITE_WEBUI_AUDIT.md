# Elite WebUI Audit — 2026-07-11

Scope: full local app (`apps/web` V2 surface) against dev API (elite branch,
auth enabled, owner + non-owner + signed-out). Viewports: 1440×900 desktop,
390×844 mobile, spot-checks at tablet width and 200 % zoom. Routes audited:
`/discover`, `/today/pick/:symbol`, `/portfolio`, `/opportunities`, `/options`,
`/account`, `/profile`, `/learn`, `/me`, `/admin`, `/admin/trust-center`,
`/dev/trust-center`, `/journal`, `/reflections`, `/track-record`, plus
loading / empty / stale / unauthorized / error states.

Verdicts use: CRITICAL (trust or comprehension breaks), HIGH (blocks the
"beginner understands in 5 seconds" bar or a11y), MEDIUM, POLISH.

## CRITICAL

| # | Finding | Where | Status |
|---|---------|-------|--------|
| C1 | Freshness label lies: "updated today" shown for any idea ≤ 30 h old — an idea generated *yesterday* 23:42 renders "UPDATED TODAY" beside an as-of stamp that says otherwise. Two independent copies of the logic (PickPage `isFresh`, LiveTodayHero `freshness`) disagree with the visible as-of line. Trust-first product must never mislabel staleness. | `PickPage.tsx`, `LiveTodayHero.tsx` | FIXED — shared truthful `freshnessInfo()` (`lib/freshness.ts`): "Updated today / yesterday / N days ago", warn tone past 30 h |
| C2 | Approved confidence copy not applied: cards and detail show raw "high confidence" although the owner decision (2026-07-09, calibration study) collapsed High/Medium to **"Meets the buy bar"**. Beginners read "high confidence" as a probability claim the data does not support. | `confidenceDisplay.ts` (flag default off) | FIXED — presentation default flipped on (opt-out `VITE_MEETS_BUY_BAR=0`); numeric conviction / API untouched |

## HIGH

| # | Finding | Where | Status |
|---|---------|-------|--------|
| H1 | Positions show absurd share precision ("1628.664495114 shares") — reads as a bug, erodes trust in every number next to it. | `PaperBook.tsx` PositionRow | FIXED — `fmtShares` (integers plain, fractional max 4 dp trimmed) |
| H2 | Stale snapshot understated: book "As of Jul 8" (3 days old) renders footnote "Snapshot slightly delayed." No age, no visual state. | `PaperBook.tsx` freshnessNote | FIXED — age-aware amber status panel with explicit date + "what this means" |
| H3 | Market tape is a screen-reader trap: quotes ×3 marquee copies ≈ 200 text nodes announced on every page; per-character split in the a11y tree. | `GlobalTicker.tsx` | FIXED — track `aria-hidden`, single visually-hidden summary sentence |
| H4 | Trust Center renders raw JSON blobs per section — violates its own "no developer clutter" purpose; labels are color-styled text only. | `AdminTrustCenter.tsx` | FIXED — humanized metric rows, EvidenceBadge (icon + text, six states), grouped sections, raw payload behind a `<details>` disclosure |
| H5 | Idea cards on Discover show no plain-English "why" — engine thesis strings are quant-residue so `plainThesis()` correctly bails, but nothing replaces it; beginner sees only numbers (entry/target/exit). 5-second test fails item 3 ("why interesting"). | `Opportunities.tsx` RecCard | FIXED — falls back to plain-language signal summary (`ideaSignals`) when no clean thesis |
| H6 | Onboarding questions carry no "why we ask" explanations (mission: beginner must understand why every question is asked); chips lack radiogroup semantics. | `ProfilePage.tsx` | FIXED — per-question why-line, `role="radiogroup"` + `aria-pressed`, answered-count progress |
| H7 | Sign-in page has no privacy/trust messaging, no caps-lock/password guidance beyond signup hint; generic error offers no recovery path. | `AccountPage.tsx` | FIXED — trust panel (private, practice-only, no real money), show-password toggle, actionable error copy |
| H8 | Sidebar wordmark links to `/learn`, not the home surface `/discover` — disorients (logo = home convention). | `ArthosChrome.tsx` | FIXED — logo routes to `/discover` |
| H9 | Owner-only / unauthorized state is a bare sentence ("Not available (owner-only).") — no what-happened / is-anything-lost / what-next. | `AdminTrustCenter.tsx` | FIXED — proper owner-only state panel |

## MEDIUM (status after the 2026-07-12 session)

| # | Finding | Where | Status |
|---|---------|-------|--------|
| M1 | Ticker values are placeholder-scale (S&P 754.95) with +0.00 % across the board when market closed — consider hiding price level when data source is the delayed dev feed. | `GlobalTicker`/tape API | OPEN |
| M2 | Signed-out `/portfolio` shows the engine canonical book under "YOUR practice portfolio". | `PaperBook.tsx`, `Briefing.tsx` sidebar | FIXED — "Demo practice portfolio" framing + sign-in CTA; "Your" reserved for authenticated sessions; 4 tests |
| M3 | "What changed" narrative needs a backend delta contract; PickPage shows freshness but not deltas vs. yesterday's read. | `delta.py` (Wave 1C) | CLOSED (2026-07-13) — per-idea delta service + PickPage section, Discover featured note, Briefing one-liner behind `REC_DELTA_ENABLED` (see RECOMMENDATION_DELTA_CONTRACT.md). Residual: plan-zone proximity unavailable until plan values are persisted |
| M4 | `/today` Briefing and `/track-record` older layout patterns. | `Briefing.tsx`, `TrackRecord.tsx` | FIXED — what-changed strip + next step; open-vs-resolved with EvidenceBadge, paper-only disclosure, methodology details |
| M5 | Research Inbox has no UI surface. | — | FIXED — `/admin/research-inbox` (VITE_RESEARCH_INBOX=1, owner-gated server routes, approve/reject state machine, versioned corrections; 6 tests) |
| M6 | Options pages expose more telemetry vocabulary than the stock surfaces. | `OptionsVisibility.tsx` | OPEN (deliberate: it is the operator diagnostics surface; beginner options surfaces were reworked in the earlier trader-first pass) |
| M7 | No route-level error boundary — an exception white-screens the SPA. | `App.tsx` | FIXED — `RouteErrorBoundary` (retry, Discover exit, focus + alert, bounded logs; 5 tests) |
| M8 | Command palette has no visible hint for Windows users. | `ArthosChrome.tsx` | FIXED — platform-aware Ctrl+K / ⌘K |

Also cleared this session: frontend test runner (Vitest + Testing Library,
241 tests), `lint:portfolio` gate green (frozen localStorage surface
consolidated into `storage.ts` raw-key wrappers; test files exempted from
production-only freeze rules), mobile `.pb-safe` safe-area utility defined,
feedback pills echo the recorded answer, dark-mode + 200 % zoom verified
(no horizontal overflow at 720 px).

## POLISH

| # | Finding |
|---|---------|
| P1 | Full-page mobile capture shows bottom tab bar overlapping last card padding by a few px — add safe-area bottom padding. |
| P2 | "Practice portfolio." headline period inconsistent with other H1s. |
| P3 | Admin Beta overview cards could reuse SurfaceCard paddings (slightly different radii). |
| P4 | PickPage feedback form buttons (Yes / Not really) lack pressed state feedback. |
| P5 | Dark-mode toggle icon has no accessible label ("Switch to dark" present — verify contrast in dark theme). |

## What already passes (evidence)

- Discover: calm editorial identity (serif display + sane palette), honest
  record card ("tracks every idea it makes to the end on paper", −0.49 %
  shown, 0 closed / 10 open), journey ribbon, no fake win-rate. 5-second test
  passes items 1/2/4/5 pre-fix, all five post-fix.
- Idea detail: narrative order already matches the required beginner story
  (What to do next → why the window looks open → why this idea exists → Bulls
  vs Bears with equal prominence → Before you act → See the working with
  audit trail behind disclosure). No guaranteed-return language anywhere.
- Paper explainer, "no investment advice" footnotes, and practice-money
  labeling are consistent.
- Empty portfolio state: clear, actionable ("Browse ideas →").
- Admin console: read-only posture stated, QA-vs-real user split honest.
- Trust Center backend: six honesty labels, preliminary research explicitly
  "NOT a production statistic", incidents listed truthfully (Jul 8 drain).
- Reduced motion respected in the tape marquee.

## Test / verification summary

See final session report: `docs/ux/ELITE_WEBUI_SESSION_REPORT.md`.
