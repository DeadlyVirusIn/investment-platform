# UX-10 Conviction Engine — Debate Brief

> Shared brief read by all 4 models (Gemini · Codex · Claude Opus 4.7 · Claude Sonnet 4.6).
> This is a 3-round adversarial debate. Each model writes 2,000–3,000 words per round.

## What we are validating

UX-10 is the biggest product pivot to date for an AI-investing copilot.

**OLD (UX-5 → UX-9 Stream):** observational intelligence, market awareness, ambient AI commentary.

**NEW (UX-10):** AI-guided conviction — actionable, decision-oriented, opinionated, explainable.

The system now centers around verbs: **BUY · ACCUMULATE · WATCH · HOLD · REDUCE · SELL · WAIT**.

## What this debate is NOT about

Not in scope: backend systems, pipelines, routing, abstractions, motion engines, token plumbing, infra. Those are solved enough.

## What this debate IS about (the 11 questions)

1. **Conviction language.** How do we make BUY/SELL/WATCH feel intelligent, trustworthy, premium, grounded — not spammy, casino-like, manipulative, overconfident?

2. **Confidence system.** Current proposal: numeric scoring (`Confidence 0.82`). Is this good? Fake-precise? Should it be percentages, ranges, stars, tiers, "high/med/low"? How do we make confidence *earned*, *explainable*, *trustworthy*?

3. **ActionCard density.** Current model: verb · ticker · entry · target · confidence · thesis · invalidation · CTA. Right density? What's missing/too much? What creates scanability + emotional confidence?

4. **Overview hero.** Current: "AI FOUND 3 HIGH-CONFIDENCE MOVES TODAY" + 3 ActionCards. Too "stock picks app"? Too transactional? Loses market context? How preserve situational awareness while adding conviction?

5. **Stock detail page (Research Cockpit).** May become the CORE product. Stress-test section hierarchy, first paint, thesis structure, entry/exit presentation, financials, news+filings, reasoning drawer, invalidation UX. What makes users trust it enough to act?

6. **Options experience.** How communicate BUY CALL / BUY PUT / SELL PREMIUM / ROLL without becoming gambling UI / WSB energy? How surface risk?

7. **Trust safeguards.** Anti-gambling. Anti-overconfidence. Anti-signal-spam. Anti-addiction. Anti-neon. Anti-casino motion. Define them.

8. **Visual system.** Validate proposed conviction bars, confidence rings, verb badges, gradients, conviction tints, layered cards, score glyphs. What feels premium vs cheap vs trading-app cliché?

9. **AI reasoning drawer.** May replace "See the working." What should users see vs stay hidden? What builds trust without overwhelming?

10. **Biggest failure modes.** Each model MUST explicitly identify how UX-10 fails. Examples: signal spam, fake confidence, action bias, overwhelming beginners, emotionally manipulative, overtrading, generic stock-picker feel, lost premium identity.

11. **Final synthesis.** Conviction language system, confidence system, hero rules, ActionCard contract, Research Cockpit structure, options rules, trust safeguards, visual system, anti-pattern list, implementation priorities.

## Emotional target — locked

The product should feel like **"an AI investment strategist helping me make better decisions."**

NOT: gambling app · hype machine · ticker feed · signal spam · stock-picking casino.

Required emotional qualities: intelligent · trustworthy · modern · premium · actionable · explainable · confidence-building · future-oriented.

## Hard constraints

- Long-horizon investing, not day-trading.
- Paper trading only at present (real $ later).
- Beginners + experienced users both.
- Read-only research (no orders placed from these surfaces).
- Equities + options now; crypto/forex/commodities later.
- US market focus; some intl tickers.

## What was already locked in earlier UX phases (do NOT re-debate)

- Working/Layer-3 escape hatch ("See the working") — exists, separate concern.
- Object types (Brief / Observation / Decision / Exception) — locked in UX-6.
- Lifecycle pill — locked in UX-8.
- Three-condition vocabulary STABLE/PRESSURED/OPPORTUNISTIC — locked in UX-8B (may be subsumed by UX-10 conviction).
- Stream identity (vertical card feed, hero + grid) — locked in UX-9. UX-10 builds ON it, not against.
- Anti-AI-theater ban: no orb, no chat dock, no "Powered by AI", no suggested-question chips. STILL LOCKED.

## Round mechanics

**Round 1 — Independent position.** Cover all 11 questions. No reading other models. Adversarial framing: assume your view will be attacked, defend it preemptively. Take strong positions; no fence-sitting.

**Round 2 — Critique + refine.** You will read the other 3 models' R1 positions. Identify the weakest claim in each. Defend your own where attacked. Refine where conceded. Tag every disagreement explicitly.

**Round 3 — Final convergence.** Document final position. Mark which of your earlier claims you maintain, which you've conceded, which remain in dispute. Propose synthesis where possible.

## Output format per model per round

```
# Model: <name>
## Round: <1|2|3>

## Position summary (300 words max)
[the headline]

## Q1. Conviction language
[your view, with disagreement tags]

## Q2. Confidence system
[...]

[... through Q11]

## Disagreements with other models (R2/R3 only)
- [model X] said [claim], I disagree because [reason]
- ...

## Concessions (R2/R3 only)
- I concede [claim] from [model X]'s R1, because [reason]
- ...

## Open disputes (R3 only)
- [issue], my position vs [model]'s
```

## Reference: anti-pattern list (preliminary, models can add)

- Casino green/red (high saturation)
- Flashing/pulsing badges
- Emoji verbs
- Overconfident absolute statements ("AI is sure...")
- Hidden costs/IV/spread
- Verbs without invalidation
- Paywalled reasoning
- "Hot picks" framing
- Hero with > 5 actions
- Confidence with no decay over time
- Reasoning that's "trust us, AI said so"

## What success looks like

After R3, Opus synthesizes a single locked master at `docs/research/UX_10_CONVICTION_ENGINE.md` with:
- Conviction language system
- Confidence system (final design)
- Overview hero rules
- ActionCard contract (props + invariants)
- Research Cockpit structure (sections + first-paint hierarchy)
- Options UX rules
- Trust safeguards (named, enforceable)
- Visual conviction system (tokens + components)
- Anti-pattern list (locked)
- Implementation priorities (10A → 10I phasing)

If the 4 models cannot converge on any item, the master MUST document the dispute and recommend a default with reasoning.
