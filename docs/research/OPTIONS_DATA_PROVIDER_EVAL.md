---
phase: 11A
status: DESIGN ONLY
date: 2026-04-26
locks:
  v1_provider: ThetaData
  v1_provider_cost_per_month_usd: ~60
  v2_provider_options: [Polygon.io Starter, ORATS]
  v3_research_provider: OptionMetrics IvyDB
  provider_adapter_required: true
  provider_swap_in_v2: config_only
sources:
  synthesis: ~/.claude-octopus/discover/options-system-research/synthesis.md
  reviewers: [Codex, Gemini, Sonnet, Opus]
---

# Options Data Provider Evaluation

**Status:** Design only. NO source code. NO API integrations.
**Decision (v1):** **ThetaData** — locked.
**Rationale source:** four-way Octo Discover synthesis (2026-04-26).

---

## 1. Decision summary

**v1 chooses ThetaData** at ~$60/month, with these design constraints:

1. All provider-specific code lives in `apps/api/src/options/data/providers/thetadata.py`.
2. Downstream code (ingest, features, strategies, paper) consumes a normalized `OptionChainSnapshot` dataclass — provider-agnostic.
3. Provider swap (e.g. ThetaData → Polygon in v2) MUST be a config + adapter file change. **Not a refactor.**
4. ORATS adds in v2 if/when IV surface analytics become critical.
5. OptionMetrics added in v3 if serious historical research demands it (academic licensing).

---

## 2. Provider comparison matrix

| Provider | v1 Cost | Hist depth | Intraday | Greeks pre-computed | IV pre-computed | API style | Reliability | Paper-trade fit | Research fit | v1 Verdict |
|---|---:|---|---|:-:|:-:|---|---|---|---|---|
| **ThetaData** | ~$60/mo | EOD chains back to 2005; 1-min OHLC ~3 yrs | ✓ (1-min) | ✓ | ✓ | REST + Python client | Good (practitioner-proven) | ✓ EXCELLENT | ✓ GOOD | ✅ **CHOSEN** |
| Polygon.io Starter | ~$199/mo | Real-time + 5y intraday | ✓ (WebSocket) | ✗ (compute via py_vollib) | ✗ | REST + WebSocket | Good | OK | OK | Defer to v2 |
| Tradier | Free sandbox | Limited | ✓ | ✗ | ✗ | REST | OK | ✓ (broker sandbox) | Weak | Useful for v2 broker simulation |
| ORATS | $200+/mo | Multi-year | ✓ | ✓ (rich) | ✓ (surface) | REST | Good | OK | ✅ **EXCELLENT** | Defer to v2 (surface analytics) |
| OptionMetrics IvyDB | $10k+/yr (academic) | Decades | EOD-only standard | ✓ | ✓ | Bulk download / SQL | Excellent | Weak | ✅ **EXCELLENT** | Defer to v3 (academic-grade research) |
| Cboe DataShop | Per-file | Decades | ✓ | Mixed | Mixed | Bulk file download | Good | Weak | OK | Not v1 (no REST) |
| Alpaca Options | Free / paid tiers | Limited | ✓ | ✗ in free | ✗ in free | REST | OK | OK (broker integration) | Weak | Reject v1 — chain depth weak |
| Nasdaq Data Link | Variable | Variable | Variable | Variable | Variable | REST | OK | OK | OK | Reject v1 — third-party reseller, opaque |

---

## 3. Per-provider notes

### 3.1 ThetaData (v1 CHOSEN)

**Strengths:**
- Cheapest serious provider with **actual bid/ask** data (non-negotiable per all 4 reviewers)
- Pre-computed Greeks (delta, gamma, theta, vega, IV) — saves Black-Scholes implementation work
- Historical EOD chains back to 2005; 1-min OHLC ~3 years — sufficient for IVR/IVP and basic backtesting
- Clean REST API + actively maintained Python client (`thetadata`)
- Practitioner default in TastyTrade / OptionAlpha communities (Sonnet)
- Cost ($60/mo) preserves runway for v1 single-operator team

**Weaknesses:**
- 1-min granularity insufficient for sub-minute strategies (acceptable for v1 30–60 DTE strategies)
- No native IV surface modeling (acceptable; deferred to v2 with ORATS)
- Single-provider risk; mitigated by adapter abstraction

**Use in v1:**
- Primary chain ingest (15-min snapshots during market hours)
- Greeks via pre-computed values; sanity-cross-checked against QuantLib on a fixed test set
- IVR / IVP computed from 252-day EOD history (ThetaData has the depth)
- Paper-trade fill simulation against bid/ask snapshot (never last price)

### 3.2 Polygon.io Starter (DEFER to v2)

**Strengths:**
- Streaming WebSocket — useful for real-time MTM
- 5-year intraday history
- Familiar REST API style (similar to equities side of Polygon)

**Weaknesses:**
- Greeks NOT pre-computed (must compute via py_vollib); adds critical-path work for v1
- $199/mo vs $60/mo — 3.3× cost without 3.3× v1 utility
- No surface modeling

**Use in v2:**
- Add as second provider via `data/providers/polygon.py` adapter
- Switch primary in environments needing real-time streaming
- A/B-validate ThetaData vs Polygon Greeks on overlap dates

### 3.3 Tradier (DEFER to v2)

**Strengths:**
- Free sandbox — useful as broker simulation layer for v2 (when paper trading needs to simulate fills against a real-broker API)
- Decent option chain data

**Weaknesses:**
- Chain data depth weaker than ThetaData
- Best fit is broker simulation, not data primary

**Use in v2:**
- Wire Tradier sandbox as a parallel paper-broker fill simulator
- Compare v1 internal fill model vs Tradier-sandbox fill model

### 3.4 ORATS (DEFER to v2)

**Strengths:**
- **Best-in-class IV surface analytics** (Codex + Gemini both flag)
- Pre-computed surface fits (skew, term, smile)
- Rich Greeks including second-order

**Weaknesses:**
- $200+/mo — overkill for v1's 30–60 DTE defined-risk strategies
- Research-grade API (less quant-pipeline-friendly)

**Use in v2:**
- Add when IV surface modeling becomes critical (e.g. introducing calendar / diagonal spreads, or IV regime classifier sophistication)

### 3.5 OptionMetrics IvyDB (DEFER to v3 / academic)

**Strengths:**
- Decades of clean historical data
- Academic gold standard (DeMiguel/Plyakha/Uppal/Vilkov, Goyal/Saretto, etc.)
- Survivorship-bias-free

**Weaknesses:**
- $10k+/yr academic licensing — out of v1 budget
- Bulk SQL access; not a REST pipeline

**Use in v3 / research projects only:**
- Backtest validation over multi-decade history
- Cross-asset / cross-instrument volatility studies
- PBO / Deflated Sharpe over decades (not just months)

### 3.6 Cboe DataShop (REJECT for v1)

**Strengths:**
- Multi-decade depth
- Authoritative source

**Weaknesses:**
- Pay-per-file; bulk download model (not REST API)
- Requires significant ETL work to feed an automated paper system

**Defer to:** ad-hoc research projects only.

### 3.7 Alpaca Options (REJECT for v1)

**Strengths:**
- Integrates with Alpaca brokerage if v2 wants a unified equity+options broker

**Weaknesses:**
- Newer offering; chain depth weak
- Greeks absent in free tier

**Defer:** unless v2 unifies with Alpaca's equity broker stack.

### 3.8 Nasdaq Data Link (REJECT for v1)

**Strengths:**
- Variety of options datasets aggregated

**Weaknesses:**
- Third-party reseller; data lineage opaque
- Quality varies wildly by dataset

**Defer:** ad-hoc research only when a specific dataset matches a need.

---

## 4. Adapter contract

The `OptionChainSnapshot` dataclass (defined in Phase 11B schema) is the
provider-agnostic boundary. Every provider adapter MUST yield this shape:

```python
# Phase 11B will define this dataclass; included here for clarity
@dataclass(frozen=True)
class OptionChainSnapshot:
    snapshot_at_utc: datetime
    underlying: str
    expiry: date
    strike: Decimal
    right: str               # "C" | "P"
    option_symbol: str       # OCC
    bid: Decimal | None
    ask: Decimal | None
    mid: Decimal | None      # derived
    last: Decimal | None     # NEVER used as fill
    volume: int | None
    open_interest: int | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    iv: Decimal | None
    quote_age_seconds: int   # provider-derived; rejected if > 60
    provider: str            # "thetadata" | "polygon" | etc.
    provider_version: str    # for audit
```

Adapter responsibilities:
1. Convert provider-specific symbol → normalized OCC
2. Map provider-specific Greeks fields → standard names
3. Compute `mid = (bid + ask) / 2` when not provided
4. Set `quote_age_seconds` from provider timestamp
5. NEVER expose provider-specific quirks downstream

**Acceptance test (Phase 11C):** swap adapter from ThetaData to a mock,
ingest job runs unchanged, downstream feature compute produces identical
output for the same input chain.

---

## 5. Cost trajectory

| Phase | Provider stack | Monthly cost | When |
|---|---|---:|---|
| v1 | ThetaData only | ~$60 | Now |
| v2 (optional) | ThetaData + Polygon | ~$260 | When real-time MTM needed |
| v2 (optional) | ThetaData + ORATS | ~$260 | When IV surface analytics needed |
| v2 (broker) | + Tradier sandbox | + $0 (free) | When broker-simulation desired |
| v3 (research) | + OptionMetrics IvyDB | + $850/mo | When multi-decade backtest required |

**v1 budget envelope: ~$60/mo.** Single line item in research SaaS budget.

---

## 6. Reliability + redundancy

- **Single provider in v1** — accepted risk; mitigated by adapter abstraction making swap fast
- ThetaData uptime SLA: ~99.5% per their docs
- Failure mode: ingest job fails → snapshot row missing → downstream features for that 15-min slot missing → operator notices via UI staleness banner
- Recovery: cron retries on next 15-min slot; missed slots are gaps (not interpolated)
- v2 redundancy: Polygon as failover when added

---

## 7. Acceptance for v1 provider choice

1. ThetaData adapter implemented in Phase 11C
2. Adapter contract verified by mock-swap test
3. Pre-computed Greeks cross-validated against QuantLib on a 100-row sanity test set (max relative error < 1%)
4. Bid/ask snapshot freshness invariant enforced (`quote_age_seconds ≤ 60`)
5. Cost confirmed at ~$60/mo on operator's billing
6. Provider swap to Polygon documented as a config + adapter change for v2

`STOP. Awaiting operator approval of full Phase 11A doc set.`
