# ArthOS — Demo Script (2026-06-19)

For first-time-investor demos and innovation-fund pitches. Branch
`mvp/ideas-you-can-follow`. Mobile (390×844) is the hero form factor.

## Pre-demo setup (do this first)
- **Seed a demo device** so the journey shows populated, not cold:
  - Set localStorage `arthos_device_id` to a known demo id.
  - Add 3–5 ideas to paper (so Paper Book has positions + the progress spine
    shows Practice/Build, and the "Ready to diversify" nudge appears).
  - Follow one model portfolio (so My Portfolio + Build are populated).
- Pick a **news-rich symbol** as the day's top idea if possible (avoid an empty
  fundamentals/news section on screen).
- Have a **second, cold device** ready to show the genuine first-run.
- Confirm the running web carries the latest build; hard-refresh once.

---

## 5-minute demo (first-time investor / quick pitch)

**Beat 1 — The promise (30s).** Landing `/v2`.
> "This is ArthOS. Robinhood taught people to *trade*. We teach them to *invest*
> — one plain-English idea a day, with fake money first. We promise literacy,
> not returns."
Point at the honest line: "Nothing real is at stake."

**Beat 2 — A complete idea, in plain English (90s).** Discover → Today's Top
Idea.
> "Here's today's idea. Notice: the *company name*, not just a ticker. Plain
> 'high confidence' — no jargon. And a full plan a beginner can actually act on:
> where to enter, a target, where to get out if it's wrong, and how long to
> hold." Tap "See why" → idea detail:
> "Why it exists, the key risk, recent news. We never invent numbers — if we
> don't have it, we say so."

**Beat 3 — Practice it (45s).** Tap "Add to paper."
> "One tap. Practice money — no real money. Confirmation, and it's now tracked
> in *your* portfolio." → My Portfolio: "Live-marked, honest, yours."

**Beat 4 — Graduate to a portfolio (75s).** Discover → Model Portfolios →
open one.
> "Once they've practised single ideas, they graduate to a ready-made basket.
> We answer who it's for, why it exists, how long to hold — plus plain
> explanations of diversification, volatility, and what could go wrong. One tap
> to Follow — and it lands in the *same* practice book."

**Beat 5 — The journey (30s).** Point at the progress spine.
> "Every user has a path: Discover → Learn → Practice → Build → Automate →
> Invest. They earn each stage by *doing*, not by points or streaks."

Close:
> "A beginner goes from 'I don't know what to buy' to a practised, proven
> portfolio — understanding every step. That's ArthOS."

---

## 15-minute innovation-fund demo

Run the 5-minute flow as Act 1, then:

**Act 2 — Why this is hard to copy (4 min): honesty as a moat.**
- **No fabrication.** Show an idea with an honest empty fundamentals/news state.
  "Competitors hallucinate price targets. We refuse — plans are labelled
  'practice estimate, not advice,' derived from real price + volatility."
- **Per-user truth.** Two devices → two *different* portfolios; a new user gets
  an empty personal book, never a shared demo. "Your track record is yours."
- **De-jargoned by design.** Beginner surfaces have *zero* trading jargon
  (verified). Then open **Options Practice**: advanced, behind a disclosure,
  with the warning — and even there the card is translated ("Time left / Risk
  level / Maximum loss / What would make it fail"). "We meet beginners where
  they are, and gate complexity."
- **Confidence explained**, not asserted.

**Act 3 — The engine + data (3 min).**
- Ideas come from a **real recommendation engine** (hundreds of evaluations a
  day), not a prompt. Company names + sectors from Polygon; plans from real ATR
  + price.
- Honest about the frontier: **fundamentals/news depth** is expanding;
  **single-stock options** are validating against a live quote provider
  (Tradier production) — ETF options work today, single names land after the
  Monday market-hours validation.

**Act 4 — Traction shape + roadmap (3 min).**
- The loop that compounds: Discover → Practice → Build, each with progression
  nudges and a literacy spine. "Engagement isn't a feed; it's a curriculum that
  produces a competent investor by Day 90."
- Roadmap: **Automate** (auto-follow / rebalance) and **Invest** (real-money
  handoff) are deliberately *after* literacy — the regulatory-safe order.
- Beta readiness: scorecard 7.5/10, GO for invite beta on the stock loop
  (`BETA_READINESS_REPORT.md`).

**Act 5 — The ask / close (2 min).**
> "We've built the honest, beginner-first investing copilot the market doesn't
> have. The wedge is literacy + proof, not trades. We're ready for an invite
> beta; [the ask]."

---

## Strongest screens (screenshot kit)
Capture these (mobile, populated demo device, motion off):
1. **Landing** — promise + "Begin Day 1".
2. **Discover** — Today's Top Idea with full plan above the fold (the money shot).
3. **Idea detail** — what to do next / why / risks / news.
4. **Add-to-paper confirmation** — "✓ Added to your practice portfolio."
5. **My Portfolio** — real positions, live-marked.
6. **Model Portfolio detail** — Identity + Education + Trust + Follow.
7. **Progress spine** — the 6-stage journey.
8. **Options Practice** — advanced disclosure + translated card (the "we gate
   complexity" proof).

## Demo hygiene / what to avoid on screen
- Don't open a symbol with empty fundamentals/news during the pitch.
- Don't feature single-stock options until Monday's validation passes.
- Use a populated device for the walkthrough; keep the cold device only for the
  "genuine first-run" beat.
