# External Quant/AI Architecture Review — 2026-07-09

**Scope:** research/architecture sprint only. No production changes, no deploys, no migrations, no recommendation-logic changes, no code vendored. Prepared on the dev machine via GitHub pages/API; nothing cloned to the VM.

**Reviewed for:** ArthOS — "The AI Investing Copilot You Can Trust." Beginner-friendly, paper-only, one idea at a time, plain-English reasoning, honest proof, no live execution. Production lineage `mvp/retire-operator-deprefix` @ `5cdb099`.

---

## 1. Executive verdict

None of the four repositories should contribute code to ArthOS. Three should contribute **patterns**, and one should contribute a **shortlist of small libraries**.

- **QuantDinger** is the most directly useful: its agent-gateway *governance* layer (hashed scoped tokens, paper-only-by-default, per-call confirm flags, a small audit table, bounded job streaming) is verified in code and maps 1:1 onto ArthOS's trust posture. Its execution engine — in-process `exec()` of user/LLM Python — is the single most dangerous pattern in the set and must never enter ArthOS.
- **OpenAlice** is the best *product-shape* source: thesis-as-first-class-object, versioned research workspaces, an Inbox of durable agent reports, and "staged → reviewed → committed" action semantics are exactly what a trust-first paper copilot should feel like. It is AGPL-3.0: concepts only, strict clean-room discipline, zero code contact.
- **TensorTrade** is reference-only. Effectively dormant (one revival burst Feb 2026, nothing since), hard TensorFlow dependency, no seeding, and it lacks precisely the evaluation rigor ArthOS needs. Its OMS decomposition (slippage/execution as swappable services) and PBR reward formulation are worth citing in our own eval-harness design.
- **awesome-machine-learning** yielded a disciplined 9-tool shortlist; the first four (pandera, LightGBM `pred_contrib` → SHAP, sklearn calibration → MAPIE, Optuna) are small, maintained, permissively licensed, and each solves a *named, existing* ArthOS problem.

The differentiation thesis this review supports: **ArthOS should not get bigger; it should get more provable.** Calibrated confidence, per-idea attribution, a durable thesis/evidence ledger, an honest experiment lab, and a Trust Center convert the current "transparent narrative" into *verifiable* transparency — which none of the reviewed projects (all execution-oriented) actually deliver for beginners.

---

## 2. Reviewed source state (exact)

| Repo | Default branch | HEAD SHA | HEAD date | License (verified from LICENSE file) | Version |
|---|---|---|---|---|---|
| brokermr810/QuantDinger | `main` | `fc33395` | 2026-07-03 | Apache-2.0 (template copyright line left unfilled) | v4.0.8 |
| TraderAlice/OpenAlice | `master` | `5da4957` (merge; last substantive `e4cc538`) | 2026-07-08 | **AGPL-3.0** (verbatim, no exceptions) | v0.73.0-beta |
| tensortrade-org/tensortrade | `master` | `d58afba` | 2026-02-09 | Apache-2.0 (Quantopian copyright) | v1.0.4 (2026-02-06, after ~6-year gap) |
| josephmisiti/awesome-machine-learning | `master` | `433f2a1` | 2026-06-18 | "Other" (index only — never a dependency) | n/a |

Review date: 2026-07-09. Shortlisted ML tools were each verified individually (§5, §9); the awesome-list was treated purely as an index.

---

## 3. Repository-by-repository analysis

### 3A. QuantDinger — agent gateway over a Flask trading platform

**State.** Created 2025-12-28; 9.4k stars in ~6 months (treat as unverified hype signal). 428 commits but recent history is squashed version-bump dumps from an apparently private upstream — per-change reviewability is poor. Python 3.10+/Flask/Gunicorn/Postgres 18/Redis 8/Docker Compose; `curl | bash` installer; **Vue frontend ships only as prebuilt GHCR images (source absent)**. CI exists (`basic-ci`, `openapi-ci`, docker publish) with test dirs in backend and MCP server; depth unaudited. Open issues include a trust-critical accounting bug class ("strategy local ledger inconsistent with actual holdings", #165) and an *open* PR titled "Harden auth and secret handling" (#153).

**Verified architecture worth learning from:**
- **Agent tokens** (`app/services/agent_token_service.py`): hashed at rest, prefix + expiry, comma-joined scopes (R read / W write / B backtest / T trading, admin-only C credentials), per-token `rate_limit_per_min`, status revocation. **`paper_only=True` by default**; live requires token flag + server env `AGENT_LIVE_TRADING_ENABLED=true` + per-call `confirm_live_trading=true`. Genuine defense-in-depth.
- **Audit table** `qd_agent_audit`: `agent_name, route, method, scope_class, status_code, idempotency_key, duration_ms, created_at` — small, portable, verified in code (not just README).
- **MCP server** is a thin client over the REST gateway (24 tools; stdio/SSE/streamable-HTTP), i.e., the gateway is the security boundary, not the MCP layer — the right shape.
- **Bounded job streaming**: `wait_for_job` / `stream_job_until_done` with max-events/max-seconds caps.
- **Secret redaction** (`_security.py` `_SECRET_KEYS`, `redact_strategy_row`) applied to API responses.

**Disqualifying findings:**
- `app/utils/safe_exec.py` executes user/LLM strategy code with **in-process `exec()`** behind regex + AST deny/allow lists, restricted builtins, SIGALRM timeout. A subprocess variant exists **but is not wired into the main path**. Denylist sandboxes in the API process are a historically bypassable pattern (dunder obfuscation, numpy/pandas escape hatches); a W-scoped token is effectively remote code execution into the Flask process with DB credentials.
- Live-trading scaffolding, 8 crypto exchanges, USDT billing, community/SaaS layers — all off-thesis surface.

### 3B. OpenAlice — local-first agentic research desktop (AGPL-3.0)

**State.** ~5 months old, very hot (5.9k stars, 1.5k commits, releases every few days, all beta). Electron desktop app, local-first git-backed state, Hono server, node-pty terminals; user supplies broker/LLM keys. Heavy `codex/*` branch naming — much code appears AI-authored; refactors have regressed features (a scheduler was lost in the "UTA-split" and restored via PR). No private vulnerability-reporting channel yet. Issue tracker dominated by broker-integration breakage (IBKR gateway reporting healthy while dead, CCXT/OKX failures).

**Patterns worth clean-room adoption (concept level only):**
- **Workspaces:** each research task gets an isolated, versioned (git) working area — all agent output is diffable files, not transient chat. Their strongest idea; directly transferable as "durable, inspectable research artifacts."
- **Issue-based research tasks:** markdown/DB work items with scheduling metadata as the agent's queue — durable and human-editable.
- **Tracked entities / thesis memory:** tickers, themes, theses as first-class objects that accumulate evidence over time; solves agent amnesia. Early-stage in their code, but the product shape is right.
- **Inbox:** scheduled-run outputs land in one reviewable feed ("where did the agent's work go" solved).
- **"Trading as Git":** intents are *staged*, then *committed/reviewed* before execution — approval semantics borrowed from version control. Perfect fit for ArthOS approval-gated paper actions; their live execution layer is the buggiest part, the *state machine* is the transferable idea.
- **Runtime readiness probes** (days old): verify the agent toolchain works before scheduled tasks run — generic pre-run health-gate pattern; ArthOS's freshness engine is already halfway there.

**License wall.** AGPL-3.0 §13 (network use): if ArthOS became a derivative, the entire backend would have to be offered as AGPL source to every visitor of arthosfinance.xyz. Practical rule adopted for this review: **this document is the only artifact** — anyone implementing ArthOS features works from these generic descriptions, never from the OpenAlice source. No code, schemas, prompts, config formats, or docs text may be copied, ported, or paraphrased; never fetch their source into an ArthOS coding session.

### 3C. TensorTrade — RL trading environment framework

**State.** Revival burst Feb 2026 (gym→gymnasium, Python ≥3.12, CI added, v1.0.4 after a six-year release gap — PR co-authored with Claude), then **zero commits since Feb 9**. One-to-two revival maintainers. `tensorflow>=2.15.1` is a *hard* install dependency (heavy for our VM class). RNG seeding is an open issue since **March 2022** — reproducibility is unsolved upstream. Stale multi-year backlog of install failures and broken notebooks.

**Architecture.** Genuinely well-decomposed: `TradingEnv` composing pluggable ActionScheme (BSH, managed-risk), RewardScheme (`SimpleProfit`, `RiskAdjustedReturns`, **PBR** `R_t = (p_t − p_{t−1})·x_t`, `AdvancedPBR`), Observer over a lazy DataFeed/Stream DAG, and an OMS with commission and **slippage as swappable services**. What it does **not** contain: walk-forward validation, split tooling, overfitting controls, experiment logging/registry, leakage protections, benchmark harness, seeding — every piece of scientific rigor is left to the user, and those are exactly the pieces ArthOS needs.

**Verdict: reference only.** ArthOS's need is rigorous offline evaluation of its *existing* LightGBM recommender (purged walk-forward, cost/slippage sensitivity, benchmark-vs-buy-and-hold/12-1-momentum), not an RL environment loop. ArthOS already has a paper execution engine with fills, costs, and a replay harness. Patterns to cite in our own harness: slippage/execution service decomposition; PBR as a clean position-level attribution formulation; lazy-stream DAG as a leakage-resistant feature pipeline idea.

**RL policy training: not recommended at all.** The BP8–BP27B alpha investigation showed the bottleneck is universe breadth and data, not model class. If ever revisited: offline-only, isolated compute, purged/embargoed walk-forward, realistic costs from day one, benchmark + significance tests, fixed seeds + config registry, canary-style promotion gates, no alpha claims without out-of-sample statistics.

### 3D. awesome-machine-learning — discovery index

Actively maintained index (June 2026 merges). Used solely to seed candidates; every shortlisted tool verified individually. Shortlist and per-tool details in §9 scorecard and §5 license table; sequencing: `pandera` + LightGBM `pred_contrib` (zero new deps) → calibration (`CalibratedClassifierCV` → MAPIE) → `Optuna` → drift (SQL PSI → Evidently *or* river) → experiment tracking decision (Postgres `research_run` table vs MLflow). Deliberately empty: causal inference (premature before a validated alpha). Rejected heavyweights: Kubeflow/ZenML/Metaflow (k8s-class orchestration on a one-VM product), Great Expectations (config sprawl vs pandera), Seldon/BentoML/Feast (serving/feature-store infra for teams), darts/GluonTS (torch stacks vs statsforecast), W&B/Neptune (hosted egress conflicts with self-hosted trust posture).

---

## 4. Recent-update analysis (30–90 days)

| Repo | Signal |
|---|---|
| QuantDinger | v4.0.1→v4.0.8 in ~5 weeks; auth-hardening PR still open; ledger-consistency bug open; releases are opaque squashes — velocity high, auditability low. |
| OpenAlice | Releases every 2–4 days; newest work = readiness probes, onboarding gates, Electron smoke tests; refactor churn has broken shipped features (scheduler). Young and fluid — concepts stable, implementation not. |
| TensorTrade | Nothing since 2026-02-09. The Feb revival did not become sustained maintenance. |
| awesome-ML | Routine index merges; healthy as an index. |

Implication: none of the three code repos is a stable dependency candidate on maintenance grounds alone, independent of fit.

---

## 5. License & security assessment

### License table

| Source | License | Reuse mode | Obligations if that mode is used |
|---|---|---|---|
| QuantDinger | Apache-2.0 (verified; template copyright line unfilled — grant still valid) | **Patterns only** (recommended). If code ever copied: retain LICENSE + attribution ("quantdinger.com / QuantDinger contributors"), state changes, patent grant applies. No copyleft. | None for pattern reuse. |
| OpenAlice | **AGPL-3.0** | **Concepts only, clean-room.** Code/port/paraphrase would put ArthOS's whole network-served backend under AGPL §13 source-offer obligations. | Hard rule: no code contact; this document is the implementation source. |
| TensorTrade | Apache-2.0 (verified) | Reference only. | None for concept reference. |
| pandera | MIT | dependency | attribution in distr. |
| SHAP / Optuna / MLflow | MIT / MIT / Apache-2.0 | dependency | standard notices. |
| MAPIE / river | BSD-3 / BSD-3 | dependency | notices. |
| Evidently / statsforecast | Apache-2.0 | dependency | notices; note statsforecast's slow PyPI cadence (last release Sep 2024). |
| pgvector | PostgreSQL license | pg extension (image change ⇒ deploy approval) | permissive. |

### Security gate (applies to anything crossing into ArthOS)

- **Arbitrary code execution:** REJECT QuantDinger's in-process `exec()` sandbox categorically. ArthOS must never execute LLM- or user-authored Python inside API/worker processes. Any future "strategy script" idea requires an isolated subprocess/container with no DB credentials, read-only data mounts, and resource limits — or doesn't ship.
- **Broker credentials:** none exist in ArthOS and none should be introduced (paper-only charter). OpenAlice's issue tracker is a case study in how broker abstraction leaks (health checks lying about dead gateways).
- **Agent tool scopes:** adopt QuantDinger's shape — hashed tokens, scoped (ArthOS ships R + B only), default paper-only, per-call confirm for anything mutating, per-token rate limits, every call audited. MCP layer stays a thin client; the REST gateway is the boundary.
- **Prompt injection / poisoned market or news data:** any agent-facing research tool must treat fetched news/filings as data, never instructions; provenance (source URL + timestamp) stored with every evidence row; no tool that executes instructions found in fetched content.
- **SSRF / shell:** research fetch tools need an allowlist of data providers; no generic URL fetch, no shell tools in the gateway.
- **Supply chain:** every new dependency pinned, licenses recorded here, `pip` audit in CI (release-gate tooling from 15d7db6 already exists to extend); no `curl | bash` install patterns.
- **Secrets:** keep existing posture (.env never read/printed); adopt response-redaction middleware pattern (QuantDinger `_SECRET_KEYS`).
- **Model artifact integrity:** experiment registry rows carry git SHA + data-window hash + config hash; promoted models referenced by hash (extends existing proposal_hash discipline).
- **Cross-user isolation:** per-user book guards (P1 fix) set the precedent — any agent gateway must resolve identity server-side from session/token, never from client-supplied IDs (M1 already enforces this).
- **Resource exhaustion:** bounded job streaming (max-events/max-seconds), per-token rate limits, experiment-lab runs on dev hardware only (VM disk is a standing constraint).
- **Audit & retention:** one audit table for all agent/privileged calls; retention policy documented; incident history feeds the Trust Center.

---

## 6. Capability comparison matrix

Legend per external capability: **ADOPT** (clean-room/pattern now) · **ADAPT** (reshape to ArthOS) · **STUDY** · **DEFER** · **REJECT**.

| Capability | ArthOS today | QuantDinger | OpenAlice | TensorTrade | ML tools | Classification & why |
|---|---|---|---|---|---|---|
| Research workflow | ad-hoc scripts + docs | agent gateway jobs | workspaces + issues + Inbox | none | n/a | **ADOPT (OpenAlice concept)** — durable tasks/reports fix "work disappears into chat/sessions" |
| Persistent memory / thesis tracking | reasoning envelopes, memory files (operator-side) | none | tracked entities + thesis graph | none | pgvector (later) | **ADOPT (concept)** — Thesis Ledger is the missing product spine |
| Agent orchestration | none (operator drives) | MCP over REST gateway | agent runtimes + probes | none | n/a | **ADAPT later** — gateway pattern, R+B scopes only |
| Model experimentation | walk-forward scripts, no ledger | experiment routes (depth unknown) | none | notebooks only | Optuna + research_run/MLflow | **ADAPT (ML tools)** — registry table + Optuna |
| Backtesting | paper engine + replay harness (proven) | server-side jobs | none real | env loop, no rigor | statsforecast baselines | **KEEP OURS + STUDY** job-submission framing |
| Walk-forward validation | partial (research scripts) | not verified | none | **absent** | sklearn/Optuna | **BUILD** (Experiment Lab) — nobody reviewed has it |
| Explainability | narrative ranking_breakdown | none | none | none | `pred_contrib`/SHAP | **ADOPT (ML tools)** — real attribution under "See the working" |
| Outcome learning | MP1S/MP1A attribution rows | "reflection" not found | lessons implicit | none | n/a | **BUILD** on existing attribution (Learning Loop) |
| Paper portfolios | mature (canonical + per-user + guards) | paper-only default flag | staged paper intents | simulated wallets | n/a | **KEEP OURS**; adopt staged/reviewed states |
| Broker abstraction | none (by charter) | 8 exchanges + IBKR/Alpaca | UTA multi-broker | sim only | n/a | **REJECT** — off-thesis, and both implementations are their buggiest layers |
| Approval gates | HARD-STOP ops discipline (operator) | per-call confirm flags | staged→committed→reviewed | none | n/a | **ADOPT** — state machine on paper actions + confirm flags at tool boundary |
| Audit logging | reasoning envelopes, job_run | `qd_agent_audit` (verified) | git history as audit | none | n/a | **ADOPT** — one small agent/privileged-call audit table |
| Admin observability | /v2/admin jobs/system + stuck flags | ops routes | readiness probes | none | Evidently reports | **ADAPT** — add pre-run readiness + drift panels |
| Security posture | M1 auth, fail-closed flags, release gates | in-process exec sandbox (bad), token model (good) | no vuln channel yet | n/a | n/a | **ADOPT tokens/audit; REJECT exec** |
| Privacy | single-user, self-hosted | SaaS/billing | local-first | n/a | self-hosted libs only | **KEEP** self-hosted; reject hosted trackers |
| Deployment complexity | 1 VM compose (tight disk) | +Redis, GHCR frontend | Electron desktop | TF stack | libs only | **CONSTRAINT** — anything needing new services is DEFER by default |
| Novice UX | strongest asset (plain English, one idea) | trader-oriented | power-user desktop | dev framework | n/a | **KEEP OURS** — none of them serve beginners; this is the moat |
| Evidence quality | honest but narrative | none | sourced reports w/ timestamps | none | calibration/attribution | **ADOPT** — sources+timestamps on every evidence row; calibrated confidence |
| Licensing risk | n/a | low (Apache) | **high (AGPL)** | low (Apache) | low (MIT/BSD/Apache) | clean-room wall around OpenAlice |

---

## 7. Build-vs-borrow decisions

| Decision | Verdict |
|---|---|
| Agent gateway governance (tokens/scopes/audit/confirm) | **Borrow pattern** (QuantDinger), build in FastAPI |
| Research workspace / thesis ledger / Inbox | **Build clean-room** (OpenAlice concepts, our Postgres) |
| Evaluation harness (walk-forward, costs, benchmarks) | **Build** — reuse our paper_execution fill logic; TensorTrade referenced for slippage-service decomposition + PBR only |
| Experiment registry | **Build small** (`research_run` table mirrors existing audit-row pattern); MLflow only if a comparison UI is later wanted |
| Calibration, attribution, validation, HPO, drift | **Borrow libraries** (sklearn/MAPIE, pred_contrib/SHAP, pandera, Optuna, PSI-SQL→Evidently/river) |
| RL, live brokers, strategy-script execution, billing, crypto breadth, Electron | **Neither** — reject |

---

## 8. "Elite ArthOS" product architecture

The six candidate pillars, assessed. They survive as **five** (one merged), in dependency order:

### Pillar A — ArthOS Evidence Graph → shipped as the **Thesis Ledger** (revised)
Relational, not a graph DB: `thesis` (company/sector/theme scope, plain-English statement, status open/strengthened/weakened/closed) ← `evidence` rows (supports/contradicts, source URL, quote, observed_at, weight) ← links to `recommendation`, `paper_trade`, `outcome`, and a generated `lesson`. Builds directly on existing recommendation/attribution/reasoning-envelope rows. Differentiator: beginners see *why the thesis lives or dies over time* — no reviewed product does this. Revision rationale: "graph" is a query pattern here, not a storage engine; Postgres FKs + a couple of recursive views suffice at our scale (pgvector similarity is a later add).

### Pillar B — Research Workspace + Inbox (merged pillar 2 into the delivery surface)
Durable research tasks (question, scope, schedule) whose outputs are stored, timestamped, source-cited reports landing in an Inbox — extending the existing briefing/feedback surfaces. Agent- or operator-produced; every report immutable once delivered. Clean-room adaptation of OpenAlice's strongest ideas (workspaces, issue-tasks, Inbox) without desktop/terminal machinery.

### Pillar C — Experiment Lab (offline)
Dev-machine-only harness: purged walk-forward splits over our price history; commission/slippage sensitivity sweeps reusing `paper_execution` fill semantics; buy-and-hold + 12-1 momentum benchmarks with significance stats; `research_run` registry (params JSONB, metrics JSONB, git SHA, data-window hash, seed); Optuna studies in Postgres; statsforecast probabilistic baselines as the bar to beat; promotion gates identical in spirit to the options-canary process. This is the direct answer to the BP8–BP27B finding that we lacked a durable, honest experiment ledger.

### Pillar D — Agent Gateway (v0 read-only)
FastAPI router + thin MCP client: hashed scoped tokens (R read recommendations/portfolios/evidence, B submit offline research/backtest jobs), paper-only hardwired (no T scope exists at all), per-call confirm on anything that writes a draft, per-token rate limit, every call in one `agent_audit` table, bounded job status streaming. Explicit non-goal: no order execution tools, ever, in this product.

### Pillar E — Trust Center + Learning Loop (paired)
Trust Center: user-facing page assembling what already exists — data freshness (freshness engine), model version (GIT_SHA provenance now baked into images), sample sizes ("accuracy publishes at 10 closed outcomes" made systematic), paper performance vs benchmark, known limitations, model-change log, incident history (P1 written up honestly builds more trust than hiding it), experiment promotions. Learning Loop: recommendation → paper action → outcome → attribution (already stamped via MP1S/MP1A) → **lesson row** (generated, human-reviewed) → surfaced back into the thesis ledger and future briefings. The loop is the moat; the Trust Center is its proof surface.

**Dropped/deferred pillar elements:** autonomous scheduled agents acting without review (trust-negative at this stage); any live-broker abstraction (charter violation); graph database (over-engineering).

Defensibility check: every pillar compounds the same asset — a growing, provable, beginner-legible track record of *reasoning connected to outcomes*. That corpus (theses + evidence + calibrated confidence + honest experiment history) is not clonable by feature-copying, and none of the reviewed projects is even aimed at it.

---

## 9. Prioritized opportunity scorecard

Scores 1–10 (10 = best; for effort/cost/risk, 10 = cheapest/safest). **IF** = Innovation Fund impact.

| # | Opportunity | User value | Differentiation | Trust | Beginner | Evidence | Effort | Op cost | Sec risk | Lic risk | Readiness | IF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | pandera ingest validation (prices/quotes) | 6 | 3 | 8 | 5 | 8 | 9 | 9 | 9 | 10 | 10 | 5 |
| 2 | Real attribution via LightGBM `pred_contrib` into reasoning envelope + "See the working" | 8 | 7 | 9 | 8 | 9 | 8 | 9 | 9 | 10 | 9 | 8 |
| 3 | Confidence calibration (CalibratedClassifierCV → MAPIE intervals) | 8 | 8 | 10 | 9 | 9 | 7 | 9 | 9 | 10 | 8 | 9 |
| 4 | Trust Center v1 (freshness, model version, sample sizes, limits, incidents) | 7 | 8 | 10 | 8 | 8 | 7 | 9 | 8 | 10 | 9 | 9 |
| 5 | `research_run` experiment registry table | 5 | 5 | 8 | 3 | 9 | 9 | 10 | 9 | 10 | 10 | 6 |
| 6 | Offline evaluation harness (purged walk-forward + cost sweeps + benchmarks) | 6 | 8 | 9 | 4 | 10 | 5 | 8 | 8 | 10 | 8 | 8 |
| 7 | Optuna on walk-forward tuning | 5 | 4 | 6 | 3 | 7 | 8 | 9 | 9 | 10 | 9 | 4 |
| 8 | Drift monitoring (SQL PSI job → Evidently/river later) | 5 | 5 | 8 | 4 | 8 | 7 | 8 | 9 | 10 | 8 | 5 |
| 9 | Thesis Ledger schema + UI slice | 9 | 9 | 9 | 8 | 9 | 5 | 8 | 8 | 10 | 7 | 9 |
| 10 | Research Inbox (durable scheduled reports) | 8 | 8 | 8 | 8 | 8 | 6 | 8 | 8 | 9 | 7 | 8 |
| 11 | Paper-action approval state machine (staged→reviewed→executed) | 7 | 7 | 9 | 7 | 7 | 6 | 9 | 8 | 9 | 7 | 7 |
| 12 | Agent Gateway v0 (R+B scopes, audit table, bounded streaming) | 5 | 8 | 8 | 3 | 6 | 5 | 8 | 6 | 10 | 5 | 8 |
| 13 | statsforecast probabilistic baselines in the Lab | 4 | 5 | 8 | 3 | 9 | 8 | 9 | 9 | 9 | 8 | 5 |
| 14 | Secret-redaction response middleware | 3 | 2 | 7 | 2 | 4 | 9 | 10 | 10 | 10 | 10 | 3 |
| 15 | Outcome→lesson generation (Learning Loop v1) | 8 | 9 | 9 | 9 | 9 | 5 | 8 | 8 | 10 | 6 | 9 |
| 16 | pgvector evidence retrieval | 5 | 6 | 5 | 4 | 6 | 5 | 7 | 8 | 9 | 4 | 5 |
| 17 | Readiness probes before scheduled jobs (extend freshness engine) | 4 | 3 | 7 | 3 | 6 | 8 | 9 | 9 | 10 | 9 | 4 |

### Top 5 highest-ROI
1. **#3 Confidence calibration** — makes ArthOS's core promise ("high confidence") *statistically honest*; small, offline, transforms trust messaging.
2. **#2 Real per-idea attribution** — `pred_contrib=True` is nearly free and upgrades "See the working" from narrative to verifiable.
3. **#9 Thesis Ledger** — the product spine for differentiation; everything else attaches to it.
4. **#4 Trust Center v1** — mostly assembles data ArthOS already produces; highest trust-per-effort.
5. **#15 Learning Loop v1** — closes rec→outcome→lesson; with #9 it is the defensible corpus.

### 3 tempting ideas to REJECT
- **RL stock picking** (TensorTrade's whole premise) — weakest evidence class, highest overfit risk, off-thesis.
- **Live broker adapters / "just add Alpaca paper API"** — charter violation; both external implementations are their buggiest, most issue-ridden layers.
- **LLM-authored strategy scripts executed server-side** (QuantDinger) — in-process exec is an RCE pattern; no sandbox story fits our one-VM prod.

### 3 to revisit after product-market validation
- Agent Gateway exposed to *third-party* agents (v0 stays owner-only).
- pgvector semantic retrieval (needs a concrete retrieval feature + image change).
- MLflow UI (only if the `research_run` table's comparison ergonomics become the bottleneck).

### 3 infrastructure patterns to adopt immediately
- **Single audit table for privileged/agent calls** (QuantDinger `qd_agent_audit` shape).
- **pandera schemas at every ingest boundary.**
- **Experiment-run ledger keyed by git SHA + config hash + seed.**

### 3 product patterns to prototype
- **Thesis Ledger card** on the idea page (thesis + live evidence/counter-evidence).
- **Research Inbox** fed by one scheduled weekly research job.
- **Staged→reviewed paper action** flow (one extra confirmation state, "Trading as Git" clean-room).

---

## 10. Top-five recommendation (condensed)

Calibrate the confidence, prove the reasoning, remember the thesis, show the receipts, learn from every outcome — in that order (#3 → #2 → #9 → #4 → #15). All five are offline-or-additive, migration-light, and none touches recommendation logic semantics (calibration wraps outputs; attribution reads the model; the rest is new surface).

---

## 11. Roadmap

### NOW — 0–30 days (beta-safe, low-risk)
**M1: Data honesty floor.** pandera schemas on yfinance/Tiingo/Polygon ingest (price>0, monotonic dates, adjusted-price sanity vs raw, staleness budget) + `pred_contrib` top-5 attributions written into reasoning-envelope rows and rendered under "See the working."
- Outcome: users see real drivers per idea; bad provider data caught at the door. Architecture: pure library adds in ingest + envelope writer; one new JSONB column *or* reuse envelope payload (no migration needed if payload JSON). Deps: pandera (MIT). Data: none new. Security: none (offline/in-process, no new surface). Tests: schema-violation fixtures; attribution snapshot test per model version. Cost: ~0. Migration: none. Rollback: feature-flag render. Metric: 100% ingests validated; attribution visible on every fresh idea. Non-goals: SHAP plots, model changes.

**M2: Calibration report (offline).** CalibratedClassifierCV/MAPIE study over historical recommendations vs realized outcomes in the Lab (dev machine); publish the reliability curve to the owner console first.
- Outcome: we *know* whether "high confidence" is honest before telling users. Rollback: n/a (report). Metric: Brier/coverage numbers exist for every confidence band. Non-goal: changing displayed confidence yet (that's a product decision after seeing the data).

**M3: `research_run` registry + Trust Center v1 (owner slice).** One table; walk-forward scripts write to it. Trust Center page assembling freshness, GIT_SHA, sample sizes, paper record vs SPY, known limitations, incident log (start with the P1 writeup).
- Migration: 1 additive table (approval per policy). Rollback: page unlinked. Metric: every research run since adoption is queryable; Trust Center live behind owner gate.

### NEXT — 31–90 days (evidence + research workflow + lab)
**M4: Evaluation harness.** Purged/embargoed walk-forward over Postgres history; cost/slippage sensitivity sweeps reusing paper_execution fill logic; buy-and-hold + 12-1 momentum benchmarks with significance stats; statsforecast baselines; Optuna studies (Postgres storage). Runs on dev hardware only. Metric: LightGBM engine has a benchmark-relative, cost-adjusted scorecard per universe.
**M5: Thesis Ledger.** `thesis` + `evidence` tables (additive migration, approval-gated), evidence rows carry source URL + observed_at; idea page shows thesis card with supports/contradicts; recommendation and outcome rows link to thesis. Security: evidence ingestion treats fetched text as data (no instruction following), provider allowlist.
**M6: Research Inbox.** Durable `research_task`/`research_report` tables + one scheduled weekly job (uses existing scheduler + P0-5B-healthy claims) delivering a cited report; Inbox UI. Rollback: disable job row.
**M7: Paper-action approval states.** `proposed → reviewed → executed` states on user-initiated paper actions (additive column), UI confirmation step. Non-goal: autonomous actions.

### LATER — 3–6 months
**M8: Agent Gateway v0.** Owner-only: hashed R+B tokens, `agent_audit` table, bounded job streaming, thin MCP client. No T scope exists in code. Security controls per §5. Metric: every agent call audited; zero write paths beyond draft reports/job submissions.
**M9: Learning Loop v1.** Lesson generation on closed outcomes (template + LLM-assist, human-reviewed), lessons attach to theses and surface in briefings; Trust Center gains promotion/incident history automation.
**M10 (conditional): drift panels + pgvector retrieval** if M4-M6 usage proves the need.

Global non-goals for the whole roadmap: live trading, broker credentials, RL training, server-side execution of generated code, multi-tenant agent tokens, new always-on services on the prod VM.

---

## 12. Risks & rejected ideas

- **AGPL contamination** — mitigated by the clean-room wall (§3B, §5); this document is the only permitted OpenAlice artifact.
- **Scope creep toward a trading terminal** — the matrix (§6) shows every reviewed project drifts toward brokers/exchanges; ArthOS's rejection list is a product decision, restated: no live execution, no broker creds, no strategy-script engine, no crypto breadth, no billing complexity now.
- **VM constraints** — every NOW/NEXT item is a library or additive table; heavy compute (harness, Optuna, calibration) is dev-machine-only by design; TF-class deps rejected.
- **Score inflation risk** — effort scores assume the existing surfaces (envelopes, freshness engine, admin console, scheduler) are reused; greenfield estimates would be lower.
- **Hype risk** — QuantDinger's star velocity and OpenAlice's AI-authored churn were both treated as noise; only code-verified findings drove ADOPT ratings.

---

## 13. Next implementation sprint (recommendation)

**Sprint: "Provable Ideas" (1–2 weeks, dev-only, no deploy):**
1. pandera schemas on the three ingest paths + violation tests (#1).
2. `pred_contrib` top-5 attribution into reasoning envelopes + "See the working" render behind a flag (#2).
3. Offline calibration study of confidence_v2 vs realized outcomes; reliability curve into the owner console data (not user-facing yet) (#3, report stage).
4. `research_run` table spec + first walk-forward script instrumented (#5) — migration proposal presented for approval, not applied.

Exit criteria: attribution visible on a dev idea page; calibration report with per-band coverage; ingest validation red/green in tests. Everything else in this document waits on those results.

---

*Prepared 2026-07-09 on the dev machine. Branch `research/external-quant-ai-review`. Not merged; no production artifacts touched.*
