# Investor-Demo P0/P1 Audit & ROI Plan

**Date:** 2026-06-19 · Mode: investor-demo. Goal = trust, credibility, explainability, beginner-friendliness, defensible moat. Constraint: **surface existing data only** — no new agents, LLM providers, automation, brokers, leaderboards, or recommendation engines.

## The investor question this serves

> "Why fund ArthOS when ChatGPT, Robinhood, FinRobot, TradingAgents already exist?"

Answer the demo must make legible: ArthOS is the only beginner-safe, paper-only, **honest-by-construction** AI investing platform where every recommendation shows both sides, exposes its own audit trail, and is graded against real stored outcomes. The P0 set below makes that answer visible.

## A. Audit of current implementation

Key finding from the data-layer review: the live `/api/recommendations` payload already returns, per recommendation, a rich **evidence array** — each factor with `family`, `direction` (bullish/bearish/neutral), `score`, `weight`, and a human-readable `narrative` — plus `composite_score`, `family_scores`, and `policy.adjustments` (dampers = what hurt ranking). The frontend receives this today but types `evidence` as `unknown[]` and does not render it. **Both Bull/Bear and Trace are therefore pure frontend surfacing of already-stored, engine-computed data — no fabrication, no new generation.**

## B. Score per item

| # | Item | Status | Backing data (real, stored) | Gap |
|---|---|---|---|---|
| P0-1 | **Bull vs Bear** | **Partially Exists** | `evidence[].direction/score/narrative` (bull = bullish factors, bear = bearish factors); `composite_score`, `confidence_label`, `thesis`, `policy.adjustments` for "why ArthOS still likes it" | No unified framed card; evidence untyped/unrendered on stock detail. PickPage already shows a weaker `family_scores`-derived why/risks split. |
| P0-2 | **Recommendation Trace** | **Partially Exists** | `evidence[]` (signals + narratives), `family_scores`, `composite_score`, `policy.adjustments` (what hurt), `/recommendations/diagnostics` `top_positive`/`top_negative`/`distance_to_buy`; `candidate_idea.rejection_reason`+`factor_breakdown` (rejected) | Stock UI absent (options has the pattern in `OptionsSetupDetail`). Rejected-candidates need a `candidate_idea` read (separate, optional for v1). |
| P0-3 | **Track Record Integrity Card** | **Partially Exists** | TrackRecord page already computes return %, realized/unrealized P/L, hit-rate (≥10 closes), expectancy, drawdown, freshness, source from real endpoints (`/paper/canonical/stock`, `/paper/executed/*`) | Not assembled as one canonical trust card; recs-generated/closed counts, avg-hold-time not yet surfaced (computable client-side); calibration optional (`model_scorecard` exists). |
| P0-4 | **Reflection Loop** | **Partially Exists (substrate)** | Expected: `recommendation` thesis/confidence/generated_at. Happened: `paper_position.realized_pnl` + hold time (`closed_at-opened_at`) + exit reason (`paper_trade.reason`) via `opened_by_recommendation_id`. `reflections.ts` (localStorage thesis-review) exists | No join endpoint/surface uniting expected↔happened; "what we learned" must be **templated from real numbers**, not LLM prose. |
| P1-5 | **Why Now** | **Missing** | `earnings_event`, `market_event_calendar` (schema/data exist) but **not linked** to a recommendation; PickPage already shows per-symbol news | Needs catalyst↔rec linkage or a lightweight news-derived line. Defer (backend linkage). |
| P1-6 | **Workflow Diagram** | **Missing** | n/a (pure content) | Build as an SVG/section (Methodology or new surface). Low effort, no data. |

## C. Highest-ROI implementation order

1. **P0-1 Bull vs Bear** — flagship, fully backed by the existing `evidence[]` payload, pure frontend, the single most differentiating demo frame. **Do first.**
2. **P0-2 Recommendation Trace** — same payload (`evidence` + `policy.adjustments`), reuse the options ranking-breakdown UI pattern; high "see the working" credibility.
3. **P0-3 Track Record Integrity Card** — assemble existing TrackRecord metrics into one canonical trust card; add recs-generated/closed + avg-hold (client-side compute). High trust, low risk.
4. **P0-4 Reflection Loop** — client-side join of recommendation↔closed-position; templated expected/happened/learned from real numbers.
5. **P1-6 Workflow Diagram** — cheap content win for the deck.
6. **P1-5 Why Now** — deferred; needs catalyst↔rec linkage (small backend change) — schedule after P0.

## D. Smallest work for a dramatically stronger demo

**Render the Bull/Bear "both sides" card on the idea-detail page (PickPage) from the `evidence[]` already in the payload**, plus a one-line "Why ArthOS still likes it" synthesis derived from `composite_score`/`confidence_label`/dampers. One component + one deriver + typing the existing `evidence` field. No backend change, no new data, no risk to records — and it directly answers the investor question (balanced, transparent, not a hype pitch). This is the executed-now item.

## E. Execution

Implementing P0-1 immediately, then continuing through P0-2 → P0-3 → P0-4 autonomously. Each item: build/typecheck, runtime screenshot, separate commit. Stop only on a real technical blocker.
