# /octo:review — Phase L full multi-track review

**Date**: pre-first-live-cron, Phase UI-1 just shipped.
**Scope**: stocks + options + reasoning substrate + UX + ops + PMF + tech debt.
**Posture**: evidence-driven, implementation-aware, action-oriented, bounded.
**Reviewer lenses applied**: Gemini (adversarial / PMF / business realism), Codex (implementation / code quality / edge cases), Opus (architecture integrity), Sonnet (UX / trust / comprehension).
**Note**: agents NOT dispatched — review written from direct implementation context. All numbers cited are from real measurements taken Days 1-12.

---

## EXECUTIVE SUMMARY

The reasoning system is materially correct. The architecture is validated at 20× scale (2004 recs, 0 hash drift). Honest absence is preserved end-to-end. The two primary user-facing prose surfaces (PickModal + Decisions Col 2) now route through the deterministic renderer.

The system has FIVE real weaknesses that warrant attention before broader rollout:

1. **Truthful-collapse UX risk is unresolved.** 92 of 98 recent envelopes share 4 hashes total. Users clicking through different positions see identical text. This is *correct* behavior but reads as a UI defect.
2. **Three freeform-prose surfaces still leak** (Briefing, Decisions state panel, ActionCard) — documented but not fixed.
3. **Honest-absence comprehension is untested.** No live user has interpreted "Part of this is still being built" yet. Could read as platform incompleteness.
4. **Live cron has never fired with Phase L code.** Everything to date is replay-validated; live-vs-replay UI parity is unproven.
5. **PMF is unproven.** The product is technically beautiful but no novice user has been observed using it. Architectural rigor ≠ market fit.

There are NO critical/blocking issues. The system is shippable for operator/internal use today. Novice rollout should wait for items 1-3 to resolve and item 4 to validate.

**Top 5 highest-leverage actions for next 30 days**:
1. Observe 2026-05-19 live cron (passive — already wired)
2. Add concentration-visibility affordance to ReasoningCard ("12 of 14 entries share this setup")
3. Replace the 3 remaining freeform-prose surfaces (Briefing / Decisions state / ActionCard)
4. Conduct one structured novice walkthrough — single user, 30 min, recorded
5. Provision an earnings API key OR install lxml → activates dormant catalyst skeleton on real data

Items 6-10 (defer): truth banners global slot, state chips, timeline view, ops dashboard expansion, breadth ETL.

**Most important "do not build" rule**: do NOT solve the truthful-collapse UX risk by introducing fake variety. Solve it by EXPOSING concentration honestly.

---

## TRACK 1 — Core reasoning architecture

### Working
- 6 locked skeletons + 7 markers + 8 banner causes + 4 horizons + 5 outcomes + 12 signals + 4 invalidations — all closed enums
- Deterministic renderer: same envelope → same output bitwise (5x re-gen confirmed)
- Envelope hash captures content identity, collapses correctly across 2004 inputs to 5 hashes
- Audit table is append-only, unique on (envelope_hash, paper_trade_id), idempotent on rerun
- Constitutional lints in CI: forbidden-phrase scanner + resolver-anchor scanner
- Honest-absence respected at every layer: extractor / selector / slot builder / API / UI

### Weak
- `MOMENTUM_BREAKOUT` skeleton only reachable via specific signal combinations (e.g. momentum + iv_compression on equity). Production trigger frequency is 1 in the audit table — was 861 in D10.1 walk (sell-side Trim). Confusing reachability profile.
- `BREADTH_THRUST_ENTRY` and earnings catalyst path stay dormant — no real data
- `IV_COMPRESSION_SETUP` only fires on `asset_class='options'` but no options trades route through paper_trade today
- Vocabulary seed loader (D2.2) is one-direction only — no retirement / deprecation path implemented

### Hidden risks
- **Gemini**: envelope_hash collisions across CONCEPTUALLY-DIFFERENT trades that happen to produce same canonical content. Today 92/98 collapse to 4 hashes. If a user investigates trade A's reasoning, finds it matches trade B's, then a third trade C also matches — confidence in the audit chain may erode.
- **Codex**: `record_envelope` uses ON CONFLICT DO NOTHING on `(envelope_hash, paper_trade_id)`. Postgres NULL semantics: NULL ≠ NULL means multiple (hash, NULL) rows accumulate. Standalone envelope test rows will silently inflate over time.
- **Opus**: catalyst flags `catalyst_proximate_macro` / `_earnings` are populated by integration layer (worker_integration.py via catalyst_substrate.py). If the DB lookup raises, the helper swallows and returns False/False — silently disabling catalyst signals on DB errors.

### User confusion risks
- Skeleton names exposed in operator variant (`regime_aligned_continuation`, `mean_reversion_pullback`) are jargon. Operator-only — manageable.
- Marker copy is sometimes long ("We've only seen this setup a handful of times — the track record is thin."). Mobile would wrap awkwardly.

### Operational risks
- All 6 skeletons must remain reachable to claim catalog completeness. Current production reachability: 3 of 6 (regime_aligned + mean_reversion + momentum_breakout). 3 dormant.
- No A/B test infrastructure for skeleton selector tuning. Any rule change is global.

### PMF risks
- Architecture is correct but invisible. Novice users won't appreciate the constitutional rigor; they'll only see the surface (cards, banners, charts).

### Scaling concerns
- Render throughput: 4740 rps same-session, 1897 rps cold. Comfortable headroom.
- Audit table projection: ~13 MB at 100× current volume. Not a concern for years.
- Generator throughput: 250 ctxs/sec full pipeline. Plenty for nightly batch.

### Unnecessary complexity
- `generate_envelope` AND `generate_envelope_detailed` both exist as backward-compat wrappers. Could consolidate to one signature returning `GenerationResult` always.
- The `_OPTIONAL_BLOCK_RE` and `_resolve_optional_blocks` in renderer.py — works but is the most non-obvious piece of code in the system. Document or refactor.

### Don't build
- Don't add more skeletons until current 3 dormant ones activate
- Don't add new uncertainty markers — 7 already captures meaningful states
- Don't add a "marker severity" gradient — markers are equal-weight by design

### Highest-leverage improvements
1. Add `record_envelope` lint: forbid `(hash, NULL)` rows accumulating beyond N (currently 2 orphans from D3.6 tests). Operationally trivial.
2. Document the optional-block syntax in skeletons.py module docstring with one example

### Severity ranking
- ARCHITECTURE-1 (low): generator API duplication (generate_envelope + generate_envelope_detailed)
- ARCHITECTURE-2 (low): orphan envelope rows from test runs
- ARCHITECTURE-3 (low): catalyst flag silent-fail-on-DB-error

### Actions
- None urgent. System is correct.

---

## TRACK 2 — Stocks product UX

### Working
- PickModal: all frontend prose deleted, ReasoningCard wired with `researchPreview` flag
- Decisions Col 2: `humanReasoning()` deleted, ReasoningCard wired with `paperTradeId`
- 6-state card behavior explicit: research_preview / no_trade_id / loading / error / honest_absence / rendered
- SourcePill: 4 sources, full-word + compact variants, color-neutral
- Honest absence is its own state, not a fallback

### Weak
- **The truthful-collapse problem**: 5 real envelopes pulled → same text rendered 5 times. To a user clicking through Apple → Microsoft → Google → Meta → Tesla position cards, all 5 read "Continuation inside macro tailwind on 3-week momentum positive..." — identical. Architecturally correct, UX-flat.
- ReasoningCard has minimal styling — index.css block uses existing tokens but no design pass
- No mobile responsive behavior verified
- The "research preview" state on PickModal applies to EVERY pick (because no Pick has paper_trade_id). Result: every PickModal shows the same honest-absence card. That's 4× the "identical" complaint of Decisions.

### Hidden risks
- **Sonnet**: novice reads "Part of this is still being built" and concludes the product itself is alpha-stage
- **Gemini**: novice expects "what will this stock do" answer. Card says "Continuation inside macro tailwind..." — meaningless to non-technical user. Loses trust.
- **Codex**: ReasoningCard's `useEnvelope` hook re-fetches on every paperTradeId change. No caching. Quick clicks through 10 positions = 10 round-trips. Should add a small in-memory cache.

### User confusion risks
- "macro tailwind" is jargon. Vocabulary phrase but novice-opaque.
- "regime backdrop" appears in invalidation copy. Same issue.
- Source pill "Replay" reads ambiguously — does it mean the AI is replaying my history, or this is historical data?

### Operational risks
- If `useEnvelope` errors silently in production, users see no feedback. Error state requires actual non-2xx-non-404 — silent failures (e.g. JSON parse) don't surface.

### PMF risks
- HIGH: novice-facing surface (PickModal) currently shows research_preview state for 100% of picks → reads like "the AI never explains anything"
- The product's primary value prop is "AI explains its trades." Today, that value is only delivered on the Decisions page (operator), not the novice flow.

### Scaling concerns
- N/A — UI scales with single-user cardinality

### Unnecessary complexity
- ReasoningCard has 6 states. Likely 2-3 are sufficient in practice (rendered / loading / absence). The 6-state granularity is correct but over-modeled for current usage.

### Don't build
- DO NOT add fake per-position variety to mask truthful-collapse
- DO NOT add "AI confidence: 78%" widgets
- DO NOT add "Why THIS stock specifically" narration
- DO NOT add ratings, stars, emoji confidence indicators
- DO NOT translate jargon by paraphrasing ("regime backdrop" → "market mood") — that's frontend-generated prose

### Highest-leverage improvements
1. **Concentration affordance** — show "Reasoning shared with 12 other positions" beside ReasoningCard. Click to see them.
2. **Vocabulary glossary endpoint + tooltip** — backend already has vocabulary_phrase table. Hover any signal/regime name → see locked definition. Adds clarity without adding prose.
3. **Per-position context** (asset symbol, fill price, P&L delta, holding age) rendered ADJACENT to ReasoningCard. Makes each card feel different even when reasoning text is identical.
4. **Replace PickModal `researchPreview` blanket-absence with a different copy variant**: "AI hasn't traded this yet — once it does, we'll show the reasoning" (more direct than "Part of this is still being built").

### Severity ranking
- UX-1 (HIGH): truthful-collapse perception risk → blocks novice rollout
- UX-2 (MEDIUM): PickModal blanket research-preview → 100% of novice surface is absence
- UX-3 (MEDIUM): vocabulary jargon (macro tailwind, regime backdrop) without glossary
- UX-4 (LOW): no envelope caching on quick-click
- UX-5 (LOW): "Replay" source-pill semantic clash

### Actions
1. Build concentration affordance — small JSON endpoint `GET /api/v2/decisions/by-envelope-hash/{hash}?limit=N`
2. Build vocabulary tooltip endpoint `GET /api/v2/vocabulary/{name}` returning canonical definition
3. Add per-position context strip above ReasoningCard
4. Reword research-preview copy

---

## TRACK 3 — Options product UX

### Working
- Backend reasoning generator supports `asset_class='options'` cleanly
- `IV_COMPRESSION_SETUP` skeleton is reachable for options
- 20+ options UI pages exist (overview, chain, features, trades, risk, playbooks, learning, etc.)

### Weak
- Options trades do NOT route through `paper_trade` table → no envelopes attached
- ReasoningCard not integrated anywhere in `/options/*` routes
- 20+ options components contain prose surfaces (OptionsRationale, OptionsHeroPulse, OptionsNarrativeDetailDrawer, etc.) — all freeform passthrough

### Hidden risks
- **Gemini**: options UX is the most ambitious surface in the product (20+ pages). High maintenance cost. Low certainty of PMF on retail novice.
- **Opus**: dual paper-trading pipelines (stock vs options) means dual reasoning pipelines eventually. Risk of divergence if not unified.

### User confusion risks
- Options users see deterministic reasoning on stocks, freeform prose on options. Mixed-truth perception.

### Operational risks
- Pre-canary state (D2.5 `pre_canary_options` banner) covers options surfaces today — banner not yet rendered in UI (banner-global slot is UI-2 work)

### PMF risks
- HIGH: options trading is a niche feature. 20+ pages is heavy for a feature that may not have product-market fit
- Cost of maintaining options surfaces ≈ cost of maintaining stocks surfaces. Asymmetric.

### Scaling concerns
- Same backend, same scale

### Unnecessary complexity
- 20+ options pages is extreme. Likely 5-7 would suffice. Several are visual-hypothesis pages (similar to copilot views).

### Don't build
- DO NOT extend ReasoningCard to options until paper-trading-for-options routes through `paper_trade` table
- DO NOT add options-specific skeletons until options trades actually generate envelopes

### Highest-leverage improvements
1. Audit options page count → consolidate to 5-7 core pages
2. Wire options paper trades through `paper_trade` (unified write path) before adding options ReasoningCard
3. Apply forbidden-phrase lint to options surfaces (already covered by current scanner — flag any violations)

### Severity ranking
- OPTIONS-1 (MEDIUM): mixed-truth perception risk if user sees deterministic stocks + freeform options
- OPTIONS-2 (LOW): page count is high but not currently harmful

### Actions
- None urgent. Options is a separate phase.

---

## TRACK 4 — Quant / recommendation quality

### Working
- 9263 Recommendation rows generated daily (model v0.1.0)
- 7560 factor_snapshot rows per day across 1003+ assets
- Real raw features available: trend_strength_20d, residual_momentum_20d, atr_percent_14, sector_relative_rank, price_vs_200sma
- Per-day regime_snapshot populated for trading days
- Conviction threshold-gated Buy decisions (≥60)

### Weak
- 24-30% of Buy recs route to mean_reversion_pullback (counter-trend buys). Is that the engine's genuine read?
- 63.5% counter_trend marker firing on momentum_breakout sell-side (Trim into tailwind). High rate.
- 13.6% of 2004-rec walk hit `no_skeleton_match` — those are real engine outputs that the reasoning system refuses to characterize. Worth understanding what shape they have.
- 6.3% hit `min_signals_not_met` — sparse-feature trades that the engine still produces but reasoning can't pattern-fit
- `earnings_proximity_days` column NULL across 1008 rows — engine deliberately doesn't populate

### Hidden risks
- **Gemini**: the engine is producing ~30% counter-trend Buy signals. Is this a strategy or noise? Operator review needed.
- **Codex**: signal extractor thresholds (`MOMENTUM_TREND_POS = 0.10`) are stated as "conservative, not tuned" — they may be miscalibrated against raw factor_snapshot values vs evidence scores
- **Opus**: the bridge from RecommendationEvidence to factor_breakdown has different value semantics (clipped scores [-1,1] from evidence vs raw decimals from factor_snapshot). Factor_snapshot now overrides. But OLD live envelopes were generated against scored values — those hashes are now historical artifacts of a different calibration.

### User confusion risks
- 24% mean_reversion on buy → text reads "Pullback entry on 3-week momentum negative inside macro tailwind." Sophisticated. Novice would benefit from contextual explanation: "buying a dip"

### Operational risks
- No backtest framework for the reasoning pipeline as a unit. Skeleton selector rules + thresholds were calibrated by inspection, not by quantitative validation
- No drift detection on factor distributions across days. If signal thresholds become miscalibrated due to market regime change, no automatic alarm

### PMF risks
- MEDIUM: if the AI's strategy is "buy momentum + sell into tailwind 24% of the time as mean-reversion," novice users may find the behavior confusing without education

### Scaling concerns
- Already validated at 2004-rec scale; full universe ≈ 9263. Should walk it end-to-end at least once.

### Unnecessary complexity
- Marker assigner's COUNTER_TREND fires both:
  - When skeleton == MEAN_REVERSION_PULLBACK (always)
  - When side='buy' AND macro_headwind in signals
  - When side='sell' AND macro_tailwind in signals
- Two overlapping conditions. Could simplify to: COUNTER_TREND fires whenever side opposes regime OR skeleton is explicitly counter-trend.

### Don't build
- DO NOT tune thresholds for cosmetic distribution effects
- DO NOT add new factor inputs without truthful upstream provenance
- DO NOT introduce model-versioned skeletons (e.g. "v2 momentum_breakout") — keep one schema

### Highest-leverage improvements
1. Run the FULL 9263-rec universe walk (not just 2004) and check if patterns hold
2. Document threshold rationale in `docs/research/SIGNAL_EXTRACTION_THRESHOLDS.md` (referenced in signal_extractor.py header but not written)
3. Operator-review 10 random mean_reversion_pullback envelopes — confirm semantic legitimacy

### Severity ranking
- QUANT-1 (MEDIUM): unverified mean_reversion semantic correctness
- QUANT-2 (LOW): threshold rationale undocumented
- QUANT-3 (LOW): historical envelopes generated against different calibration semantics

### Actions
1. Schedule operator review of 10 mean_reversion envelopes
2. Write SIGNAL_EXTRACTION_THRESHOLDS.md

---

## TRACK 5 — ML / research pipeline

### Working
- Recommendation generation is daily-scheduled (`run_recommendations_for_all_accounts` 22:30 ET)
- Factor snapshot generation populated nightly
- Evidence rows attached to recommendations
- Outcome tracking infrastructure exists (`recommendation_outcome` with barriers, realized returns)

### Weak
- ML model version `0.1.0` — feels alpha
- Outcome tracking infrastructure exists but no reasoning-system feedback loop. The reasoning system doesn't yet ingest realized outcomes.
- `recommendation_outcome.realized_30d_return` populated only for trades old enough to score. Sparse for fresh trades.

### Hidden risks
- **Gemini**: research pipeline is sophisticated but no observable retraining cadence. If model v0.1.0 stays static while market regime shifts, signal quality degrades silently
- **Codex**: shadow scorers and ML hybrid endpoints exist (`alpha_lab`, `ml_lab`, `ml_replay`) — multiple semi-overlapping research surfaces

### User confusion risks
- Research surfaces are operator-only — low novice impact

### Operational risks
- Multiple ML/research surfaces (`alpha_lab`, `ml_lab`, `research`, `signal_lab`) likely overlap. Operator burden.

### PMF risks
- Low — research pipeline is invisible to end users

### Scaling concerns
- Factor snapshot compute is batchable; not a bottleneck

### Unnecessary complexity
- 4+ research-related UI pages (alpha-lab, ml-lab, research, signal-lab) — likely 1-2 would serve
- The "shadow scoring" pipeline adds plumbing without obvious near-term reasoning benefit

### Don't build
- DO NOT introduce new ML models before validating the v0.1.0 calibration against realized outcomes
- DO NOT add reasoning-system ML inference paths — the deterministic renderer is non-ML by design

### Highest-leverage improvements
1. Connect `recommendation_outcome` → reasoning calibration: track per-skeleton realized returns over a 90-day window. Surface in operator dashboard (when one exists).
2. Audit `alpha_lab` / `ml_lab` overlap. Consolidate.

### Severity ranking
- ML-1 (MEDIUM): no reasoning-system feedback loop from outcomes
- ML-2 (LOW): research-surface fragmentation

### Actions
- None urgent.

---

## TRACK 6 — Cron / ops reliability

### Working
- 4-job ET-anchored cron pipeline: ingest (22:00) → recommendations (22:30) → exit cycle (23:00) → paper trade (23:30)
- Last run 2026-05-16 was clean across all jobs
- Wrapper-RC honesty (D2.3) classifies `{skipped: True}` as `'skipped'`, non-zero `return_code` as `'error'`
- Telemetry table envelope_generation_run ready for first live fire
- Scheduler reconciles cron tz at startup (`_reconcile_schedule_tz`)
- All 3 containers (api, worker-tickloop, worker-cron) have current Phase L code

### Weak
- `envelope_generation_run` table empty — no live cron has exercised it yet
- 3 deferred ops tasks (D1.5 Sentry, D1.8 CI workflow stub, D1.9 channel) still pending
- No alerting on coverage drop / drift / lint failure
- No CI workflow in `.github/workflows/` that runs the lint scripts and snapshot suite

### Hidden risks
- **Codex**: if the 2026-05-19 cron fails, no Sentry/PagerDuty alert routes to a human. Logs need manual inspection.
- **Opus**: the cron schedule fires at 22:00 / 22:30 / 23:00 / 23:30 ET sequentially. If `ingest_prices_daily` runs long (last run 232 sec) and overruns, downstream jobs may run against stale bars. No explicit dependency declaration in `job_schedule`.

### User confusion risks
- None — ops surfaces are operator-only

### Operational risks
- HIGH: no CI workflow runs forbidden_phrases / resolver_anchor lints. A bad merge could land a Tier-A phrase in production without anyone noticing until manual scan.
- MEDIUM: no monitoring dashboards. Coverage-gap endpoint exists but nothing scrapes it.

### PMF risks
- Low directly; high indirectly if production silently corrupts (e.g. Tier-A phrase makes it through to PickModal)

### Scaling concerns
- Single worker cron — no horizontal scaling. Fine at current scale.

### Unnecessary complexity
- 11 enabled job_schedule rows. Most ops-related. Could audit which are essential.

### Don't build
- DO NOT add complex alerting before CI lint runs
- DO NOT add monitoring dashboards (UI work) before the deterministic-reasoning UI-2 phase
- DO NOT add health endpoints beyond the existing 3 (D6.7 + D7.5 + D8.5)

### Highest-leverage improvements
1. **Stand up CI lint workflow** (`.github/workflows/lint.yml`): runs `forbidden_phrases.py` + `resolver_anchor_lint.py` + snapshot suite on every PR. Highest-leverage single ops task.
2. Sentry setup (D1.5 deferred from Day 1) — catches silent failures
3. Add post-cron status check to confirm `envelope_generation_run` rows appear when expected

### Severity ranking
- OPS-1 (HIGH): no CI lint enforcement
- OPS-2 (MEDIUM): no Sentry / alert routing
- OPS-3 (LOW): no monitoring dashboards

### Actions
1. Write `.github/workflows/lint.yml`
2. Provision Sentry DSN for dev environment

---

## TRACK 7 — Trust / honesty model

### Working
- Forbidden-phrase lint scans 2 dirs across `.py/.ts/.tsx/.js/.jsx`. Deliberate-fail rc=1 verified.
- Resolver-anchor lint guards `paper_trade.fill_ts` invariant
- 9 pinned snapshot fixtures detect any envelope_hash drift
- Honest-absence is a real state at every layer (extractor / selector / slot builder / API / UI)
- Constitutional guarantees documented in code comments + memos
- Substrate dormancy enforced (breadth, earnings) — refused fabrication 5 times across Days 5-10

### Weak
- 3 freeform-prose surfaces still leak (UI1_REVIEW_AUDIT.md)
- Truthful-collapse perception risk uncommunicated to users
- "Replay" source pill semantic ambiguity (user may misread as "AI is replaying")
- No glossary surface — vocabulary phrases like `macro_tailwind` reach users without definition

### Hidden risks
- **Gemini**: trust model is internal-rigorous but externally invisible. A novice user does not perceive that the platform refuses to fabricate — they just see card text. The honest-restraint architecture is not marketable.
- **Sonnet**: honest-absence text says "Part of this is still being built." This could be misread as the PLATFORM being unfinished rather than this specific decision being un-modeled.
- **Codex**: forbidden-phrase scanner skips files matching `**/docs/research/**`. Some research docs contain forbidden phrases legitimately. But if research docs end up consumed by an LLM pipeline, those phrases could leak indirectly.

### User confusion risks
- Honest absence may erode trust rather than build it (the inverse of the intent)
- Mixed truth surfaces (Briefing narrative + ReasoningCard) create cognitive dissonance

### Operational risks
- No tonal review process for new copy. If anyone adds new banner copy or marker text, no review gate.

### PMF risks
- HIGH: trust model is sophisticated; users may not value sophistication
- Competitive analysis (other AI investment products) likely shows confidence percentages, narrative explanations, persuasive copy. Our restraint may read as inferiority.

### Scaling concerns
- Forbidden-phrase scanner runs in <1s on current codebase. Scales fine.

### Unnecessary complexity
- 15 Tier-A phrases. Could be 5 with sharper definition.
- 7 uncertainty markers — well-chosen but could collapse to 5 (limited_history + low_signal_strength → "thin_evidence"; counter_trend + crowded_trade → "correlated_risk")

### Don't build
- DO NOT add user-facing trust-marketing copy ("Our AI never lies!")
- DO NOT add a "trust score" widget
- DO NOT add "compare to other AI products" content
- DO NOT translate "honest absence" copy into softer language (would defeat the purpose)

### Highest-leverage improvements
1. **Onboarding card**: novice's first PickModal click shows a one-time explanation: "When the AI doesn't have a clear explanation for a trade, it tells you so. That's a feature."
2. Rename "Replay" source pill to "Historical" — preserves meaning, removes ambiguity
3. Vocabulary glossary tooltip (already in Track 2 actions)

### Severity ranking
- TRUST-1 (HIGH): honest-absence misread as platform incompleteness
- TRUST-2 (MEDIUM): trust restraint invisible to users without education
- TRUST-3 (LOW): "Replay" semantic ambiguity

### Actions
1. Write a one-paragraph onboarding card for novice first-view of honest absence

---

## TRACK 8 — Performance / scaling

### Working
- Render throughput: 4740 rps same-session, 5941 rps varied, 1897 rps cold-session
- Generator throughput: 250 ctxs/sec full pipeline (signal extraction + selector + populator + marker + build)
- Audit table query: 0.04ms hot path (get by paper_trade_id)
- Quality view query: 0.22ms full scan
- Indexes appropriate: PK + paper_trade_id + skeleton_id + rendered_at + unique-constraint

### Weak
- ReasoningCard `useEnvelope` hook has no caching
- No request batching for table-row source pills (would be N+1 if rendered)
- No CDN for static assets — irrelevant at single-user scale

### Hidden risks
- **Codex**: rapid clicks through 20 positions in Decisions page = 20 sequential HTTP roundtrips. Each ~50ms. Total ~1s UI lag.

### User confusion risks
- None at current scale

### Operational risks
- None at current scale

### PMF risks
- Low — performance is comfortable

### Scaling concerns
- Audit table projection at 100×: 13MB. At 1000×: 130MB. Both trivial.
- Generator at 250 ctxs/sec → 9263 universe walk = 37 sec. Comfortable for nightly batch.

### Unnecessary complexity
- None observed

### Don't build
- DO NOT add caching layers (Redis, etc.) at this scale
- DO NOT optimize render perf further — already 4740 rps

### Highest-leverage improvements
1. Add a 60-second client-side cache to `useEnvelope` keyed on paperTradeId. Eliminates re-fetch on tab switch.

### Severity ranking
- PERF-1 (LOW): no useEnvelope cache

### Actions
- None urgent

---

## TRACK 9 — Product-market fit

### Working
- Product has a clear thesis: "AI explains its trades honestly"
- Architecture supports the thesis (deterministic renderer, honest absence)
- Phase UI-1 makes the thesis visible on one surface (Decisions Col 2)

### Weak
- THE primary value prop ("AI explains its trades") is not yet delivered on the novice surface (PickModal shows research_preview blanket)
- No user research conducted
- No competitive positioning analysis
- No retention / engagement metrics infrastructure
- No "what makes this better than competitor X" answer

### Hidden risks
- **Gemini**: this is an architecturally-beautiful product that may not have a market. Novice retail traders historically prefer narrative + confidence + simplicity. Our product offers restraint + structure + honesty.
- **Gemini**: the deterministic-reasoning thesis is a developer-driven thesis. Has it been validated against real novice users? No.
- **Gemini**: the substrate-quality-first posture (refusing earnings ETL, refusing breadth, refusing fake variety) is correct engineering but creates a product that has LESS visible AI behavior than competitors. Could read as "AI does less."
- **Gemini**: paper-only platform with no real-money path. Monetization model unclear.

### User confusion risks
- The product currently has 30+ pages. Novice users would benefit from 3-5 visible surfaces.

### Operational risks
- Without PMF, all the operational rigor is wasted

### PMF risks
- HIGH-HIGH-HIGH: no validated demand for deterministic-reasoning explanations
- HIGH: 30+ page surface area is investment-bank-research-portal scale, not consumer-app scale
- MEDIUM: paper-only with no real-money path limits user investment
- MEDIUM: no clear acquisition channel implied

### Scaling concerns
- Cannot scale beyond proven PMF

### Unnecessary complexity
- 30+ pages is the single biggest complexity bet. Most can probably be deleted.

### Don't build
- DO NOT add more pages until existing pages prove user value
- DO NOT build features without user observation
- DO NOT scale up before validating one user's workflow
- DO NOT add a real-money trading path until paper-mode is loved by at least one user

### Highest-leverage improvements
1. **Conduct ONE structured novice walkthrough.** Single user. 30 minutes. Recorded. Watch them try to make a decision based on the AI's recommendations. See if they get value.
2. Identify the THREE pages a novice actually needs (probably: Overview/Today + Portfolio + Decisions). Hide or remove the other 27 from novice navigation.
3. Define a single, measurable success criterion for novice users (e.g. "Can a user understand why the AI bought TSLA today within 60 seconds of opening PickModal?")

### Severity ranking
- PMF-1 (CRITICAL): no user validation
- PMF-2 (HIGH): 30+ pages exceeds novice cognitive capacity
- PMF-3 (HIGH): novice value prop (explanation) is undelivered today (research_preview blanket)
- PMF-4 (MEDIUM): paper-only with no monetization path
- PMF-5 (MEDIUM): no competitive positioning

### Actions
1. Schedule novice walkthrough
2. Define novice navigation = 3 pages, demote rest

---

## TRACK 10 — Technical debt / future risk

### Working
- Constitutional locks (lints + snapshots) prevent rot
- All migrations applied cleanly through M088
- No circular dependencies in reasoning module
- Clear separation between backend (deterministic) and frontend (renderer-only)
- Reasoning module has clear contracts (envelope, generator_result, etc.)

### Weak
- 11 backend migrations in 12 days (M078 - M088 plus M083 corrective). Schema is active. Documentation lags.
- TypeScript codebase has many `// Phase X` comments — accreting context
- No automated test coverage % tracking
- Vite dev server not in compose; requires manual start after every rebuild (per CLAUDE.md memory)
- 3373 LOC across the 4 major web pages (Decisions / Overview / PaperPortfolio / Briefing). Large files.
- Decisions.tsx at 1233 LOC — well beyond comfortable threshold
- Overview.tsx at 1350 LOC — same

### Hidden risks
- **Codex**: 1233-LOC pages have many entangled responsibilities. Refactoring will be expensive.
- **Codex**: web codebase has multiple parallel "view" hypotheses (CopilotOverview / CopilotStream / CopilotConviction / CopilotInteractive / CopilotLiving / CopilotLegacy) — all preserved as visual experiments. Storage cost low; mental overhead high.
- **Opus**: many tables (regime_snapshot, factor_snapshot, recommendation_evidence, recommendation_outcome, candidate_idea, paper_trade, reasoning_audit, envelope_generation_run) are each cleanly separated but the COUPLING between them is implicit. A schema change to recommendation could break the bridge silently.

### User confusion risks
- Indirect — debt slows feature work, which slows UX improvements

### Operational risks
- HIGH: 6 copilot view variants behind `?view=` params. If a stakeholder visits a stale URL, they see an obsolete UI hypothesis.
- MEDIUM: web codebase grew faster than the design system did. Component sprawl.

### PMF risks
- Indirect — debt accumulation means PMF discovery slows

### Scaling concerns
- N/A directly

### Unnecessary complexity
- 6 copilot view variants — visual hypotheses behind feature flags. PRUNE: pick one default, archive the rest.
- 20+ options pages — same prune candidate
- 4+ research pages (alpha-lab, ml-lab, research, signal-lab) — overlap

### Don't build
- DO NOT add more visual hypotheses
- DO NOT preserve experimental views indefinitely

### Highest-leverage improvements
1. **Archive deletion sweep**: remove the 4-6 copilot view variants behind `?view=` flags that aren't in active use. Archive the code in a `legacy/` dir if sentimental value, but remove from active routing.
2. Refactor Decisions.tsx 1233 LOC → 4-5 focused sub-components
3. Document the schema graph (regime_snapshot ↔ factor_snapshot ↔ recommendation ↔ paper_trade ↔ reasoning_audit) in a single ER diagram

### Severity ranking
- DEBT-1 (MEDIUM): 1233-LOC Decisions.tsx
- DEBT-2 (MEDIUM): 6 visual-hypothesis copilot views
- DEBT-3 (LOW): missing schema documentation

### Actions
1. Schedule debt-cleanup sprint AFTER PMF validation
2. Document schema graph

---

## SEVERITY-RANKED ISSUES (cross-track)

### CRITICAL
1. **PMF-1**: no user validation conducted. The product has not been tested with a single novice user. Every other finding compounds because of this.

### HIGH
2. **UX-1 / Truthful-collapse perception**: 5 of 5 sampled envelopes render identical text. Reads as broken/lazy UI to a user.
3. **UX-2 / PickModal blanket research-preview**: 100% of novice picks show "Part of this is still being built." Defeats the primary product value prop on the primary novice surface.
4. **TRUST-1 / Honest-absence misread**: copy may read as platform-incompleteness rather than honest disclosure.
5. **PMF-2 / Surface area**: 30+ pages exceeds novice cognitive load by ~10×.
6. **PMF-3 / Undelivered value prop**: "AI explains its trades" is delivered only on operator surface.
7. **OPS-1 / No CI lint enforcement**: any merge can land a Tier-A phrase or break determinism without warning.

### MEDIUM
8. **UX-3 / Vocabulary jargon without glossary**: "macro tailwind", "regime backdrop", "momentum_3w_positive" reach users without definitions.
9. **QUANT-1 / Unverified mean_reversion semantics**: 24% of Buys route to counter-trend. Operator review needed.
10. **ML-1 / No outcome feedback loop**: realized outcomes don't yet feed back into reasoning calibration.
11. **OPS-2 / No Sentry/alerting**: silent failures go unnoticed.
12. **TRUST-2 / Trust restraint invisible**: rigor isn't marketable to novices without education.
13. **PMF-4 / Paper-only**: no real-money path → user investment is shallow.
14. **DEBT-1 / 1233-LOC Decisions.tsx**: refactoring will be expensive.
15. **DEBT-2 / 6 copilot variants**: stale URLs surface stale UI.
16. **OPTIONS-1 / Mixed-truth perception**: deterministic stocks + freeform options creates cognitive dissonance for users who touch both.
17. **TRACK1 / Generator API duplication**: `generate_envelope` and `generate_envelope_detailed` both exist.

### LOW
- ARCHITECTURE-2 (orphan envelope rows)
- ARCHITECTURE-3 (catalyst flag silent-fail)
- UX-4 (no useEnvelope cache)
- UX-5 ("Replay" semantic ambiguity)
- QUANT-2 (threshold rationale undocumented)
- QUANT-3 (historical envelope calibration mismatch)
- ML-2 (research-surface fragmentation)
- OPS-3 (no monitoring dashboards)
- TRUST-3 ("Replay" pill ambiguity)
- PERF-1 (no client cache)
- DEBT-3 (schema docs missing)

---

## DO NOT BUILD

In rough order of importance:

1. **No fake reasoning variety.** No paraphrasing. No randomization. No skeleton proliferation.
2. **No confidence percentages.** No "AI is X% sure." No gauges. No stars.
3. **No generative narration layer.** No LLM-produced explanations anywhere in the user-facing path.
4. **No frontend prose generation.** Helper functions like `plainWhatThisMeans` stay deleted; do not reintroduce.
5. **No new visual hypothesis views.** The 6 copilot variants are enough archaeology.
6. **No new pages.** 30+ already. Prune before adding.
7. **No real-money trading path** until paper-mode has at least one delighted user.
8. **No earnings substrate fabrication.** Stay dormant until real provider data ships.
9. **No breadth substrate inference.** Same.
10. **No "trust score" widget.** No marketing of trust.
11. **No "AI vs analyst" comparison.** Distracts from structured reasoning.
12. **No envelope editing UI.** Audit chain is append-only.
13. **No marker dismissal / "don't show me uncertainty" toggle.** Markers are constitutional honesty.
14. **No mobile-specific reasoning surfaces yet.** Desktop UX first.
15. **No chat / Q&A surface.** Separate substrate question.
16. **No customizable reasoning templates.** Constitutional locks.

---

## HIGHEST LEVERAGE NEXT 30 DAYS

In priority order:

### Week 1 (passive observation)
1. **Observe 2026-05-19 03:30 UTC live cron.** Already wired. Document outcome.
2. **Run full 9263-rec universe walk.** Extend D10.1 to full universe; check no drift at 4.5× current scale.
3. **Stand up CI lint workflow** (`.github/workflows/lint.yml`). Lowest-cost ops insurance.

### Week 2 (user validation)
4. **Conduct ONE structured novice walkthrough.** Single user. 30 min. Recorded.
5. **Conduct ONE structured operator walkthrough.** Same format, operator perspective.
6. **Define novice navigation = 3 pages.** Hide the other 27 from novice nav.

### Week 3 (truthful-collapse mitigation)
7. **Backend endpoint `GET /api/v2/decisions/by-envelope-hash/{hash}`.** Returns N other paper_trades sharing the same envelope. ~30 LOC.
8. **Frontend concentration affordance.** Small "Reasoning shared with N other positions" link beside ReasoningCard. Click → modal showing all positions.
9. **Per-position context strip above ReasoningCard.** Asset symbol, fill price, current P&L. Makes each card feel different at the same reasoning.

### Week 4 (cleanup pass)
10. **Replace the 3 remaining freeform-prose surfaces.** Briefing narrative (either deterministic or banner-caveat), Decisions state panel (delete or wrap), ActionCard rationale_short (skeleton tag or honest absence).
11. **Vocabulary glossary tooltip.** Backend endpoint + frontend tooltip.
12. **Rename "Replay" source pill to "Historical."** One-line change.

Items 13-30 (defer): truth banner global slot, state chips, timeline, ops dashboard, breadth ETL, earnings provider activation, options reasoning integration, copilot view archival, large refactors.

---

## CONTRADICTIONS BETWEEN REVIEWERS

### Codex (impl) vs Gemini (PMF)

- Codex says: refactor Decisions.tsx (1233 LOC). Gemini says: only refactor if a user needs the work; don't pre-clean before validating PMF.
- **Resolution**: Gemini wins for now. Defer refactoring until PMF is validated.

### Opus (architecture) vs Sonnet (UX)

- Opus says: 6 ReasoningCard states is correct modeling. Sonnet says: 3 states is enough for users.
- **Resolution**: Opus wins on modeling correctness; the 6 states map to real conditions. But Sonnet's point about UX simplification is valid in the rendering layer — the 6 backend states could collapse to 3-4 distinct visual presentations.

### Gemini (adversarial) vs all (architecture)

- Gemini says: the deterministic-reasoning thesis is a developer thesis. Users may not value it.
- **Resolution**: Cannot be resolved without a user. This is what the novice walkthrough is for.

### Sonnet (UX) vs Opus (constitution)

- Sonnet says: "Part of this is still being built" reads as platform-incompleteness. Soften it.
- Opus says: do not soften — the honest-absence text is constitutional.
- **Resolution**: Opus wins on copy fidelity. But Sonnet's underlying observation (user confusion) is real. The right fix is: keep the copy AND add onboarding context, not edit the copy.

### Codex (edge cases) vs Gemini (don't over-engineer)

- Codex says: add envelope caching to `useEnvelope`. Gemini says: premature optimization at single-user scale.
- **Resolution**: Gemini wins. Defer until measured.

---

## CONSENSUS RECOMMENDATIONS

All 4 reviewer postures agree on:

1. **The architecture is correct.** No structural changes needed pre-rollout.
2. **The Phase UI-1 work was the right scope.** Removing frontend prose was the right call.
3. **PMF is unvalidated and that is the single biggest risk.** Every track surfaces this.
4. **Truthful-collapse must be solved by exposure, not paraphrase.** All four lenses agree.
5. **The 3 remaining freeform-prose surfaces should be cleaned up** — only the order/urgency varies between reviewers.
6. **No new construction until 2026-05-19 cron observation.** All reviewers endorse the hold posture.
7. **Honest absence is the most important UX battleground.** If users misread it, the entire product thesis is at risk.
8. **Substrate refusals (breadth, earnings) should stay refused.** Consistent across reviewers.

---

## ANTI-PATTERN WARNINGS

If under pressure to ship, watch for these regressions:

1. **"Just add a confidence number" pressure.** From a stakeholder who wants familiar AI UX. Refuse — would defeat the trust model. Counter: show uncertainty markers more prominently instead.

2. **"Make it sound smarter" pressure.** Drift toward narrative-style copy in marker text or skeleton templates. Counter: vocabulary phrases are LOCKED. Tonal review on any copy change.

3. **"Add variety so positions look different" pressure.** From a designer or PM seeing identical cards. Counter: variety must come from real data heterogeneity, not paraphrase.

4. **"Wire breadth using price proxies" pressure.** From an engineer wanting to unblock BREADTH_THRUST_ENTRY. Refuse — substrate dormancy is constitutional.

5. **"Show estimated future return" pressure.** From product wanting to demo a number. Refuse — backtesting + outcome tracking exist for that; reasoning explains DECISIONS, not predicts returns.

6. **"Combine ReasoningCard with chart/news/everything" pressure.** From a UI consolidation push. Counter: card is its own primitive; embed don't merge.

7. **"Replace honest-absence text with something softer" pressure.** From UX review of novice friction. Counter: the discomfort is constitutional; fix with onboarding context, not copy.

8. **"Add more skeletons to cover the 14% no_skeleton_match cases" pressure.** From the same source. Counter: those cases are correctly refused; explain them, don't paper over.

9. **"Build the truth banner system to handle a special case" pressure.** From an edge case discovery. Counter: banner system is UI-2; existing card states cover the common ones.

10. **"Migrate the freeform-prose cleanup work into UI-1 retroactively"** pressure. Counter: UI-1 was scoped. The 3 leaks are documented and will be addressed deliberately.

---

## END OF REVIEW

This document does not commit to any of the listed improvements. It is a diagnostic.

Awaiting direction on:
- Which items to act on first
- Whether to wait for 2026-05-19 live cron observation before any action
- Whether to schedule the novice walkthrough as the highest-leverage next step
