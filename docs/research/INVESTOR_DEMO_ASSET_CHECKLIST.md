# Investor Demo Asset Checklist

**Date:** 2026-06-19 · Companion to [`INVESTOR_UPGRADE_ROADMAP.md`](INVESTOR_UPGRADE_ROADMAP.md) (item #9). A shot-list of screenshots/assets to capture for the investor deck and live demo, using **surfaces that already exist today** plus a small "build-next" set. Capture on the restored demo device (NAV ~$105K, 30 open, realized +$5,952) so every number is real and consistent.

## Capture environment
- Device/portfolio: owner-demo device → `bc207e65` (per-device book), NAV ~$105,211.76, 30 open, realized +$5,951.82.
- Browser at 1440×900, clean profile, no devtools, light + dark variants where relevant.
- Verify freshness shows "fresh" before each capture (avoid stale-data screenshots).

## Tier 1 — capture now (surfaces that exist)
1. **Discover** (`/v2/discover`) — the today's-ideas feed with the live market ticker visible. Shows the product's front door + real recommendations.
2. **Methodology** (`/v2/methodology`) — the 5-section "How ArthOS reaches its decisions" page. The trust/transparency narrative; strong diligence asset.
3. **Track Record** (`/v2/track-record`) — real closed trades, realized P/L, equity curve; the honest "only show what we can back" framing (no fabricated win-rate). Core proof shot.
4. **Portfolio / Practice** (`/v2/portfolio`) — the $105K book, 30 open positions, per-user paper proof.
5. **Pick / idea detail** (`/v2/today/pick/:symbol`) — the per-idea "see the working": ranking breakdown, evidence, considered-and-rejected. The explainability story.
6. **Learn home + a lesson** (`/v2/learn`, `/v2/learn/lesson/:slug`) — the education spine (beginner-first positioning).
7. **Options setup detail** (`/v2/today/options/:id`) — structured setup with as-of/freshness + "what the engine is seeing" (shows depth without leverage/gambling vibe).
8. **Global ticker** — close-up of the running market tape (atmosphere/credibility).

## Tier 2 — capture after the "Now" roadmap items ship
9. **Bull/bear "both sides" card** (roadmap #3) — the single most differentiating demo frame; shows downside, not just the pitch.
10. **Per-recommendation trace / run-card** (roadmap #4) — inputs → reasoning → evidence → confidence, as one inspectable artifact.
11. **Honest track-record metrics card** (roadmap #2) — canonical metrics + the "we suppress win-rate until N≥threshold" honesty note.
12. **Agent-workflow diagram** (roadmap #8) — data → reasoning → recommendation → paper-validation → track record, one slide.
13. **Landing trust strip** (roadmap #9) — paper-only · honest-data · per-user proof.

## Deck narrative order (suggested)
1. Problem + positioning (beginner-safe, the market capability-racers can't serve) → Tier-1 #1 Discover.
2. Trust/transparency → #2 Methodology + #5 Pick detail (and Tier-2 #9 both-sides).
3. Honest proof → #3 Track Record + #4 Portfolio (and Tier-2 #11 metrics card).
4. Moat → the 7 pillars from [`TECHNICAL_MOAT_PLAN.md`](TECHNICAL_MOAT_PLAN.md) + Tier-2 #12 workflow diagram.
5. Safety/regulatory posture → paper-only-by-construction (dual-gate, roadmap #6).

## Honesty guardrails for captures
- Never stage a fabricated win-rate, NAV, or position count — use the real restored demo state.
- If a metric is suppressed (insufficient N), screenshot the suppression copy — it *is* the differentiator.
- Label any replay/backfill data as such; only screenshot `source=live` for headline numbers.
