# Investor Upgrade Roadmap — Top 10

**Date:** 2026-06-19 · Source: [`COMPETITIVE_REPO_AUDIT.md`](COMPETITIVE_REPO_AUDIT.md). Ranked by investor-impact × beta-impact, gated by ArthOS's beginner-safe / paper-only / honest-data constraints. Effort: S (≤2 days), M (≤1 sprint), L (multi-sprint). "Now" = before next investor meeting.

Ordering principle: ship the **narrative + proof surfaces** investors evaluate in a 20-minute demo first (cheap, high-trust), then the **structural moat** features that survive technical diligence.

---

### 1. Investor-facing "How ArthOS works" / methodology page
- **Why investors care:** the first diligence question is "what is the engine and why should we trust the numbers?" A single, honest methodology narrative answers it and signals maturity.
- **User benefit:** beginners see the reasoning and the guardrails — builds trust, reduces "is this a scam?" friction.
- **Effort:** S (content-only; a Methodology route already exists). **Risk:** very low (no data, no records, no creds).
- **Sprint size:** S · **Now.**

### 2. Standardized track-record explanation card (honest metrics object)
- **Why investors care:** borrowed from freqtrade's discipline — one canonical metrics struct (return, realized P/L, win-rate *only when N≥threshold*, expectancy, max drawdown, avg hold) computed identically everywhere proves you don't cherry-pick. "We refuse to show a win-rate we can't back" is a memorable diligence moment.
- **User benefit:** an honest, legible scorecard instead of vanity stats.
- **Effort:** S–M (TrackRecord page already reads real closed trades; formalize the metrics object + "why this is honest" copy). **Risk:** low.
- **Sprint size:** S · **Now.**

### 3. Bull/bear "both sides" card on Discover ideas
- **Why investors care:** TradingAgents' debate pattern is the single most differentiating, demo-able feature — a two-sided case (not a hype pitch) screenshots beautifully and signals a defensible, balanced engine.
- **User benefit:** sees the downside before acting — beginner-protective.
- **Effort:** M (distill the 9-agent debate into a cheap single-pass "show both sides" prompt; do NOT run the full graph). **Risk:** low-moderate (keep "trade call" vocabulary out; frame as education).
- **Sprint size:** M · **Now/Later** (start now, ship next sprint).

### 4. Per-recommendation "see the working" trace / run-card
- **Why investors care:** Vibe-Trading's `run_card` + `/trace` is the explainability moat — every recommendation has a structured, inspectable record (inputs → reasoning → evidence → confidence). Proves the engine isn't a black box.
- **User benefit:** can audit any idea end to end.
- **Effort:** M (ArthOS already has ranking_breakdown / evidence surfaces; formalize into one canonical per-rec record). **Risk:** low.
- **Sprint size:** M · **Now/Later.**

### 5. Outcome-reflection loop (closed-idea post-mortems)
- **Why investors care:** TradingAgents' reflection loop on top of ArthOS's existing MP1A/MP1S attribution (`opened_by_recommendation_id`, `realized_pnl`) = a credible **closed learning loop** — "the system grades its own past calls and feeds that forward." This is the hardest thing for a competitor to fake.
- **User benefit:** honest "here's how our last call actually did" per idea.
- **Effort:** M (data substrate already exists; add a short NL post-mortem per closed position). **Risk:** low.
- **Sprint size:** M · **Later (high value).**

### 6. Dual-gate paper-only guarantee + immutable audit log
- **Why investors care:** QuantDinger's pattern turns "we're paper-only" from a promise into a **structural property** — execution is gated behind two independent flags and every engine action is appended to an immutable log. De-risks the entire diligence conversation (no accidental real-money exposure).
- **User benefit:** indirect — safety they can rely on.
- **Effort:** M (formalize the existing paper-only posture into an explicit dual-gate + audit-log abstraction). **Risk:** low (hardening, not new capability). Do NOT add live capability.
- **Sprint size:** M · **Now/Later.**

### 7. Shadow Account — per-user behavior diagnostics
- **Why investors care:** Vibe-Trading's standout novel feature, reframed for education — profiles a user's paper behavior (holding days, disposition effect, overtrading) and coaches. A retention + differentiation story with zero live risk.
- **User benefit:** personalized, honest "here's your behavior pattern" coaching → Learn↔Practice loop.
- **Effort:** L (new analytics over the paper journal). **Risk:** low-moderate (avoid diagnostic over-claims; describe behavior, don't psychoanalyze).
- **Sprint size:** L · **Later.**

### 8. Agent-workflow diagram + backtest/paper-validation summary card
- **Why investors care:** one diagram of the pipeline (data → reasoning → recommendation → paper validation → track record) + a validation summary card makes the moat legible on a slide.
- **User benefit:** understands how ideas are vetted.
- **Effort:** S (diagram + a static/derived summary card). **Risk:** very low.
- **Sprint size:** S · **Now.**

### 9. Demo-screenshot kit + landing trust strip
- **Why investors care:** a curated screenshot set (Discover both-sides card, honest track record, trace, methodology) + a landing "trust strip" (paper-only · honest-data · per-user proof) is the deck's visual backbone.
- **User benefit:** clearer first-impression of credibility.
- **Effort:** S. **Risk:** very low.
- **Sprint size:** S · **Now.**

### 10. Leaderboard / paper-challenge engine (gamified Practice)
- **Why investors care:** AI-Trader's leaderboard/auto-settlement reframed as honest per-user paper competition = an engagement + retention metric investors love — *without* any live-trading risk.
- **User benefit:** motivation, social proof, progress.
- **Effort:** L. **Risk:** moderate (keep mark-to-market honest; avoid gambling framing — no stakes, no real money).
- **Sprint size:** L · **Later.**

---

## Now vs Later

**Now (pre-investor, low-risk):** #1 methodology page, #2 track-record honest-metrics card, #8 workflow diagram + validation card, #9 demo-screenshot kit + trust strip. Start #3, #4, #6.

**Later (post-meeting, higher effort/moat):** #5 reflection loop, #7 Shadow Account, #10 leaderboard. Finish #3/#4/#6.

**Sequencing rationale:** the "Now" set is mostly content + surfacing of data ArthOS already has — it makes the existing engine *legible and trustworthy* in a demo without touching portfolio records, credentials, or execution. The "Later" set deepens the structural moat (closed learning loop, behavior diagnostics, gated automation) and is where defensibility compounds.
