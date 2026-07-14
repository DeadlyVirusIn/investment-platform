# ArthOS — Beta Readiness Report (2026-06-19)

Evaluation only. Branch `mvp/ideas-you-can-follow`. Measured on a cold device
(`fund-audit-1`, 390×844 mobile).

## 1. First-time user audit (measured)

### Time-to-first-value
- Landing communicates the promise immediately (value prop + "Begin Day 1"
  above the fold after the earlier fix).
- **First real, understandable idea** (a complete plan) is reachable in
  **1–2 taps**: Landing → "Begin Day 1" → Day-1 path, then Discover; or straight
  to Discover where **Today's Top Idea sits above the fold with its full plan**.
- A beginner sees a *complete* idea (name, sector, plain confidence,
  Entry/Target/Exit/Timeframe) within ~10 seconds of reaching Discover.

### Clicks to each milestone (verified)
| Action | Clicks | Notes |
|---|---|---|
| Leave landing into product | **1** | "Begin Day 1" → `/v2/start` |
| Understand one idea fully | **0–1** | Plan is on the Discover hero; "See why" → full detail (1) |
| Add to paper | **1** | card "Add to paper" (→ pick `?add=1`, auto-adds) or pick-page button; shows ✓ confirmation. Verified: book count 0 → 1. |
| View performance | **1** | bottom-nav "Portfolio" → `/v2/portfolio` |
| Follow a portfolio | **2–3** | Discover → Model Portfolios (open) → portfolio → "Follow Portfolio" (✓ confirmation); now lands in the same My Portfolio book |

*(Note: an automated selector pass mis-flagged Add-to-paper / Portfolio-nav as
"broken" — false negatives: Discover's "Add to paper" is a link, not a button,
and the run never opened a pick page. Both flows verified functional via the
API + prior screenshots.)*

### Friction points
1. **Landing CTA goes to the lesson path, not an idea.** "Begin Day 1" lands on
   `/v2/start` (lessons). A curious user may want to *see an idea* first.
   Mitigated by the Discover nav, but a "See today's idea" secondary CTA on the
   landing would shorten time-to-value. *(P1 — not a bug.)*
2. **Fundamentals/news often empty.** Honest placeholders, but a demo/first
   session should land on a symbol with real news. *(Data, not UX.)*
3. **Options single-stock cards empty until Monday** (ETFs only today).
4. **Follow takes 2–3 taps** through the (collapsed) Model Portfolios section.
   Acceptable; the comparison row is a faster path.

## 2. Landing page audit

### Does it communicate value in 10 seconds?
**Mostly yes.** Above the fold: "Your AI Investing Copilot," the promise ("we
read the market, write the thesis, explain it in plain English"), the honest
hook ("Nothing real is at stake. We promise literacy, not returns"), and a
working "Begin Day 1" CTA.

### Missing on the landing (for conversion + a fund)
- **Proof / social proof** — no "N calls live," no track-record teaser, no
  user/beta numbers on the landing itself (the record exists *inside* the app
  via TrustBanner, but not on the first screen).
- **Differentiation line** — doesn't explicitly contrast with Robinhood/AI
  pickers ("not trading, not a black box").
- **A glimpse of the product** — text-only; no preview of a real idea card. One
  example idea card on the landing would sell the "plain-English completeness"
  instantly.
- **Trust marks** — "practice money, no real money," "we never fabricate
  numbers" could be surfaced as a one-line trust strip.

These are landing-copy/layout opportunities, not blockers.

## 3. Beta readiness scorecard (1–10)

| Dimension | Score | Rationale |
|---|---:|---|
| **Product** | 7 | Core loop complete (Discover→Practice→Build); Options + Automate/Invest pending |
| **UX** | 8 | Beginner-first, mobile, compressed (≤3.5 screens all states), consistent disclosure pattern |
| **Onboarding** | 7 | Strong Day-1 + progress spine + Continue-path; above-fold CTA; could add "see an idea first" |
| **Trust** | 8 | Honest-data discipline, real per-user track record, practice-first, confidence explained, honest empty states |
| **Data quality** | 6 | Real recs engine + Polygon names/sectors + ATR plans; fundamentals/news sparse; options stock universe blocked (Monday) |
| **Beginner friendliness** | 9 | Jargon removed (verified 0 leaks), plain plans, company names, education/trust blocks, "practice money" framing |
| **Differentiation** | 8 | "Follow + prove + learn" + honesty is genuinely distinct |
| **Demo readiness** | 7 | Strong happy path; needs a seeded demo device (positions + a portfolio followed) + prod deploy |
| **Overall** | **7.5** | **Green for a private/invite beta on the stock loop**; data depth + options are the visible gaps |

## 4. Go / no-go for beta
**GO — private invite beta**, scoped to the stock idea→practice→portfolio loop,
with:
- A seeded demo device (a few positions + one followed portfolio) so the
  journey shows full.
- Honest framing of the gaps (options Monday-validated; fundamentals/news
  expanding; real money is deliberately later).
- The prod deploy executed (credential-gated) with the readiness checklist
  (`PRODUCTION_READINESS_ONBOARDING_WAVE.md`, incl. index.html no-cache).

## 5. Top 5 pre-beta polish items (none are blockers)
1. Landing: add a one-line differentiation + a sample idea-card preview + a
   trust strip (proof/social proof).
2. Seed a demo device so first impressions show a populated journey.
3. Pick a news-rich default symbol for demos (avoid empty fundamentals).
4. Optional: a "See today's idea" secondary CTA on the landing.
5. Confirm options single-stock cards after Monday's validation before featuring
   options in any demo.
