# Elite ArthOS — Master Roadmap

**Date:** 2026-07-09 · **Branch:** `feature/elite-arthos-provable-ideas` (off `mvp/retire-operator-deprefix` @ `5cdb099`) · Program artifacts: `docs/research/*` (forensics, attribution, calibration, external review), `docs/architecture/*` (6 specs), dev prototypes (attribution card, thesis card, trust center — all flag-off). **Nothing in this program is deployed.**

## 1. Current state (evidence-based, from Sprint 1 forensics + Sprint 3 study)

- Stock ideas are produced by the **rule engine**; confidence = agreement score occupying only **50–66.67** of a 0–100 scale. LightGBM is shadow-only: no persisted artifact, dead inference seam, kill switch on.
- **First calibration evidence (research data):** High-band Buys hit **54.4%** vs the ~64% the score implies (overconfident, outside CI); Medium (56.5%) outperformed High — label ordering inverted; AUC **0.52** → near-zero discrimination. Displayed confidence overstates certainty and its granularity is currently unsupported.
- Outcome machinery is real and rich (barrier labels, regimes, horizons) — 7,752 resolved research outcomes — but production publishes almost nothing about it yet.
- Nightly paper fills carry **zero commission/slippage**; costs exist only in weekly rebalance.
- No experiment ledger, no artifact registry, no thesis persistence, no drift monitoring.
- Trust surfaces (freshness engine, GIT_SHA provenance, admin console, honest empty-states) are strong foundations — the proof layer is what's missing.

## 2. Validated opportunities vs rejected ideas

**Validated by this program's own evidence:** ingest contracts (built, 11 tests) · real attribution (built, reconciles to 2e-15) · calibration measurement (built; found real miscalibration) · research_run registry (spec) · thesis ledger (spec + prototype) · trust center (spec + prototype) · research inbox (spec) · learning loop (spec) · agent gateway v0 (spec + threat model).

**Rejected (unchanged from external review):** RL stock picking · live brokers/credentials · server-side execution of generated strategy code · crypto breadth · billing/SaaS complexity · Electron desktop · heavyweight MLOps platforms · **plus, newly evidence-backed:** shipping a fitted confidence calibrator now (data-blocked: all live decisions in one quarter vs the 100-day embargo) and any UI implying High>Medium reliability while AUC ≈ 0.52.

## 3. Feature ranking

| Item | Rank |
|---|---|
| Wire ingest contracts into `ingest_symbol` + nightly report row | **BUILD NOW** |
| Trust Center v1 (owner route, live feeds replacing fixtures) | **BUILD NOW** |
| research_run registry (migration 109 + walk-forward scripts write to it) | **BUILD NOW** |
| Confidence wording review (product decision from calibration data) | **BUILD NOW** (decision), copy change gated on owner approval |
| Thesis Ledger (migrations 110/111 + idea-page card) | **PROTOTYPE → BUILD** (31–90d) |
| Experiment Lab harness (walk-forward + cost sweeps + benchmarks vs buy-and-hold/12-1) | **BUILD** (31–90d) |
| Research Inbox (112 + weekly scheduled report) | **PROTOTYPE** (31–90d) |
| Learning Loop lessons (113) | **DESIGN DONE → BUILD** (90–180d, needs resolved prod outcomes) |
| Agent Gateway v0 (114, owner-only R/P/B/D) | **DESIGN ONLY → BUILD** (90–180d) |
| Attribution on live candidates (requires reviving the shadow inference seam + registry) | **DEFER** until a model passes Experiment Lab gates |
| Fitted calibrator / MAPIE intervals | **DEFER** to ≥3 embargo-separated quarters of live decisions (~2027Q1) |
| Commission/slippage in nightly paper track | **BUILD** (31–90d; prerequisite for honest benchmark claims) |
| pgvector retrieval, MLflow UI, drift dashboards (Evidently) | **DEFER** (SQL-PSI job first) |
| Public Trust Center v2 | **DESIGN ONLY** (separate approval; redaction serializers per spec) |
| Multi-tenant / third-party agent tokens | **REJECT for now** |

## 4. Sequencing, dependencies, migrations

Migration order (all proposals, none generated): **109 research_run (+approval table) → 110/111 thesis+evidence → 112 research inbox → 113 lesson → 114 agent gateway tokens/audit**. Each additive-only, each with down-revision and rollback documented in its spec. Dependency spine: registry ⟶ experiment lab ⟶ (promotion gates) ⟶ attribution-on-live; thesis ledger ⟶ inbox ⟶ learning loop; trust center consumes all of them but launches first on existing feeds.

## 5. Gates

- **Security gates:** external-review §5 checklist per item; agent gateway threat model (114 spec) before any token exists; prompt-injection containment = review-gated generated evidence (110 CHECKs).
- **Product gates:** no user-facing copy change without owner approval; confidence wording change requires the calibration report reviewed by owner; public Trust Center is a separate HARD-STOP.
- **Evidence gates:** nothing labeled `proven` in Trust Center without production-data backing; no model promotion without registry-recorded out-of-sample, cost-adjusted, benchmark-relative results (spec §promotion); aggregate lessons need N≥30 (Wilson).

## 6. Costs & infra impact

Dev-machine only for research compute (calibration study ran in seconds; walk-forward harness minutes). VM impact of the whole NOW tranche: one additive table (109), one nightly report row per symbol batch, one owner route — negligible CPU/disk. NEXT tranche adds 4 tables and one weekly job. No new services, no Redis, no vector DB, no TF. Token/LLM costs: lesson/evidence generation deferred to 90–180d and templated (single-digit calls/day).

## 7. Success metrics

- 100% of nightly ingests produce a contract report; zero silent provider regressions (measured: quarantine/abort events surfaced in admin within 1 day).
- Every research run since adoption reproducible from its registry row (git_sha + config_hash + seed re-run → same metrics hash).
- Trust Center live with ≥10 sections fed by real data; zero `proven` labels without evidence.
- Calibration: production reliability curve auto-refreshes as outcomes resolve; wording decision made and documented.
- Beta impact: idea page gains thesis card + honest confidence framing without losing the plain-English voice (UX-judge check before any enable).

## 8. Innovation Fund narrative

"Trust" as an engineering system, demonstrable in artifacts: a reliability curve we measured on our own engine **and acted on**, per-idea attribution that reconciles to machine precision, an incident log that includes our worst bug, a registry that makes every research claim reproducible, and a paper track record with costs modeled. No competitor in the reviewed set (execution-oriented, power-user tools) is even aimed at provable transparency for beginners.

## 9. 30 / 90 / 180-day plans

**0–30d (production-bound, each behind its own approval):** wire ingest contracts (+ nightly report persistence, admin panel row) · migration 109 + instrument existing walk-forward scripts · Trust Center owner route on live feeds · owner decision on confidence wording · pandera-vs-custom note closed (custom shipped).
**31–90d:** Experiment Lab harness (purged walk-forward, cost/slippage sweeps reusing paper_execution, buy-and-hold + 12-1 benchmarks, statsforecast baselines, Optuna) writing to the registry · Thesis Ledger 110/111 + idea-page card (UX-judge review) · nightly-cost model in paper track · SQL-PSI drift job.
**91–180d:** Research Inbox 112 + weekly research job · Learning Loop 113 once production resolved-outcome count clears N≥30 · Agent Gateway v0 (114) owner-only · calibrator re-study when live decisions span ≥3 quarters · public Trust Center v2 decision.

## 10. Explicit non-goals (program-wide)

Live trading, broker credentials, generated-code execution, autonomous agent actions, multi-tenant tokens, new always-on services, any claim of alpha without registry-recorded out-of-sample evidence.
