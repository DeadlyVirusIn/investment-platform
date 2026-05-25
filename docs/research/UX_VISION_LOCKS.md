# ArthOS V2 — UX Vision Locks

Established alongside the Phase 0/A/B/C visual-parity work. These are
the non-negotiable design positions that downstream phases must honor.

## 1. Category positioning
**ArthOS is an AI Investing Copilot for novice investors.**

- Subtitle "AI Investing Copilot" must appear in the chrome on every
  page (desktop SideNav + mobile TopBar wordmark).
- The word "copilot" must appear in `<title>`, in onboarding copy, and
  in the SideNav subtitle.
- The product is NOT positioned as: trading dashboard, portfolio
  tracker, Bloomberg-lite, robo-advisor, or paper-trading sandbox.

## 2. Visual register
**Light-first, sage-green editorial.**

- Default theme: light. Dark stays available as toggle.
- Brand color: sage green (`oklch(0.38 0.05 150)` light /
  `oklch(0.78 0.07 150)` dark) applied to: primary CTAs, active nav
  states, eyebrow pills, focus rings, brand-mark tile, progress fills.
- Type system: Instrument Serif (display), Fraunces (editorial drop-cap
  + accent only), Inter (body), JetBrains Mono (numerics).
- Card surfaces use a single `SurfaceCard` primitive — three variants
  (default / muted / highlight). No ad-hoc `surface-drawer` utility
  styling on new code.

## 3. Information architecture
**Five primary destinations. Period.**

  Today · Journal · Practice · Learn · Me

Operator surfaces (Trade Ideas, Coming Up, Notes, Watchlist) and
reference surfaces (Reflections, Methodology) live in the drawer
secondary list. Track Record folds into Me.

Decision Journal is a deferred surface; if `/v2/journal` does not
exist, the primary-nav slot is omitted, NOT renamed to something
else.

## 4. Navigation pattern
**Fixed 248px SideNav on desktop. 5-tab BottomNav on mobile.**

- No drawer-hamburger pattern on desktop. The SideNav is always
  visible.
- BottomNav uses icon + label + active top-indicator.
- TopBar carries optional progress slot (lesson reading %) and the
  mobile-only brand tile + subtitle.

## 5. Editorial typography
**Drop-cap on lesson body. Brand-pill eyebrow on page headers.**

- `prose-editorial` class wraps lesson body — applies
  `::first-letter` Fraunces 3.75em colored brand.
- `<PageHeader>` primitive renders an eyebrow as a
  `bg-brand/8 text-brand text-[10px] uppercase tracking-widest`
  pill — no other eyebrow pattern allowed on top of pages.

## 6. Coaching voice (Phase 0)
**Onboarding speaks as a coach, not as a publication.**

Before: "Every weekday we publish a briefing — the actual decisions
of a model portfolio."

After: "ArthOS is your AI investing copilot. We walk you through one
investing idea per day. Nothing real is at stake."

The shift is from third-person editorial ("we publish") to
second-person coaching ("we walk you through").

## 7. Trust shelf
**Methodology link in every page footer.**

- Methodology stays as a 5-section page (already exists).
- Every page renders a footer with: "How ArthOS works →" link +
  "Stored on this device only. Never sent anywhere." reassurance.
- "AI-generated" disclaimer was rewritten to "Automated" in PR #5;
  do not regress.

## 8. Out of scope (do not regress)
- No new AI features
- No new analytics / telemetry
- No new dependencies beyond what visual parity strictly requires
- No new routes beyond what UX Phase 2 + 3A already shipped
- No Decision Journal route
- No backend / API changes

## 9. Lovable shell must coexist with the ArthOS market ticker / status rail
**The Lovable-style SideNav + TopBar + content layout MUST continue
to render the ArthOS market-aware top rail above the main page area.
Do NOT remove the ticker tape, the NOW/NEXT/RISK strip, the Engine
status cell, the Health pill, or the Regime cell during visual-parity
work.**

Reason: ArthOS is positioned as an AI Investing Copilot, and the
copilot framing depends on the user being able to see — at any
moment, on any page — what the engine sees: live regime, engine
arming state, anomaly health, and market context. Hiding this rail
turns the product back into a reading magazine; keeping it is what
makes the editorial surfaces feel coupled to a live system.

### Components that must remain visible
| Component | Source | Slot |
|---|---|---|
| `TopStrip` | `apps/web/src/components/shell/TopStrip.tsx` | NAV · Today P&L · Total return · Regime · Engine · Health · Last-run |
| `MarketTicker` | `apps/web/src/components/shell/MarketTicker.tsx` | Scrolling market context tape |
| `StatusRail` | `apps/web/src/components/shell/StatusRail.tsx` | NOW · NEXT · RISK strip |

### Rendering order (top → bottom)
```
TopStrip          (~44 px on desktop, sticky)
MarketTicker      (~28 px scroll tape)
StatusRail        (~30 px context strip)
─── Lovable SideNav + TopBar + main below ───
```

### Visual restyle rules (applied during V2 visual-parity work)
- Borders: replace `border-ink/40` and equivalent heavy borders with
  `--border` token (sage-tinted ink/8%).
- Surface: replace `bg-ink/95` opaque dark on the rail backdrop with
  `color-mix(in oklch, var(--card) 92%, transparent)` + backdrop-blur.
- Typography: replace operator monospace tickers (where applicable)
  with `font-mono` (JetBrains Mono) at 12-13 px with tabular-nums.
- Cell padding: tighten from `px-4 py-3` to `px-4 py-2.5` for
  vertical compaction; spec keeps the rail unobtrusive.
- Pill tones: `success` → brand-tinted (`color-mix var(--brand) 18%`),
  `warning` → accent-tinted, `danger` → destructive-tinted. Pills
  must still flash colour when state warrants.
- Mobile (< lg): rail collapses to a single line carrying NAV +
  Health + ⌄ disclosure for the remaining cells. NEVER hidden
  entirely on mobile.

### Warning visibility — non-negotiable
- Health pill MUST remain visible at all times.
- Warning + critical states MUST use coloured tone (not muted).
- "No evaluation path currently active" copy on the Engine cell
  stays. Wording may not be softened to "Engine idle" or similar
  unless the underlying `state.fire` semantics change.
- StatusRail RISK segment MUST surface anomaly counts when > 0.

### Acceptance criteria for visual-parity PRs
A visual-parity PR is REJECTED if it:
- removes `TopStrip` / `MarketTicker` / `StatusRail` from `Shell`,
- hides the Health pill on any viewport,
- replaces the Engine `state.fire`-driven copy with static text,
- removes anomaly-derived RISK count from the rail,
- omits the rail above the Lovable-style chrome on the V2 surface.

The `ArthosPage` shell (in `apps/web/src/v2/chrome/ArthosChrome.tsx`)
must be extended to render the rail above its SideNav-offset main
column. Today the V2 surface renders the Lovable chrome WITHOUT the
rail — that is a known gap and will be closed before further visual
phases ship.

## 10. Out of scope (do not regress) — continued
- No new AI features
- No new analytics / telemetry
- No new dependencies beyond what visual parity strictly requires
- No new routes beyond what UX Phase 2 + 3A already shipped
- No Decision Journal route
- No backend / API changes

This document is the authoritative reference for visual-parity work.
Subsequent phases (D-H) may extend it but may not contradict it
without a new vision-lock entry.
