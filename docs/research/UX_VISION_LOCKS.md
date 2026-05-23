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

This document is the authoritative reference for visual-parity work.
Subsequent phases (D-H) may extend it but may not contradict it
without a new vision-lock entry.
