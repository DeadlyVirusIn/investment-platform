# Final External Repo Gap Review — 2026-07-12

Evidence-first comparison of four external repositories against the ArthOS
Elite program as it actually exists on `feature/elite-arthos-provable-ideas`
(reviewed at `e401d53`, dev DB at migration 118, prod at 109). Supersedes the
2026-07-09 external review for gap-analysis purposes; that document remains
the record of the original pattern extraction.

Product boundary applied throughout: ArthOS is a beginner-friendly,
paper-only, evidence-driven investing copilot. Anything that pulls toward a
live-trading terminal, autonomous execution, crypto breadth, or a generic
agent workspace is rejected regardless of engineering quality.

---

## 0. Licensing firewall (verified 2026-07-12)

| Repo | Commit reviewed | License (GitHub API spdx_id) | Review method |
|---|---|---|---|
| github.com/TraderAlice/OpenAlice | `733c957846b0f80abbf3278e2bafb34c92fb49a0` (master, pushed 2026-07-12) | **AGPL-3.0** (triple-confirmed: API, README, LICENSE file; no dual-license language found) | **Clean-room**: GitHub API metadata + README/product-docs prose only. No clone, no source/schema/prompt/test files opened, nothing fetched into any ArthOS workspace, no code quoted. Concepts restated independently. |
| github.com/NoFxAiOS/nofx | `dc68884559c5eae7d28cfeb22d5ee82ba8b8b29e` (dev, pushed 2026-07-11) | **AGPL-3.0** (verified via API) | **Clean-room**: README + `docs/architecture/*`, `docs/guides/TROUBLESHOOTING.md` prose only; no source read or quoted. |
| github.com/brokermr810/QuantDinger | `fc33395cbbf162e0145372341740b9ae4bac3f6a` (main, v4.0.8, pushed 2026-07-11) | **Apache-2.0** (verified). Caveat: its Vue frontend and mobile client live in separate repos under a **source-available non-commercial license** — those are NOT Apache and are treated as AGPL-equivalent walls (patterns describable, code untouchable). | Deep README/docs/file-tree review permitted for the Apache backend; pattern-level extraction only, no code vendored. |
| github.com/josephmisiti/awesome-machine-learning | `a0692c7f92adead8f2f769d309a6445c2a127761` (2026-07-11) | `NOASSERTION` (custom notice) — irrelevant: pure link index, nothing vendored | Used strictly as a discovery index; every candidate library license-verified individually on PyPI/GitHub (§D). |

**Clean-room provenance statement.** No AGPL (or source-available) code,
schema, API shape, prompt, UI structure, test, comment, or naming was copied,
ported, translated, or paraphrased. No AGPL source was fetched into the
ArthOS implementation workspace at any time. Everything recommended below is
specified from independently expressed product concepts plus ArthOS's own
existing architecture. The four reviews above were performed by isolated
research agents whose outputs were concept summaries in their own words; those
summaries — not the repositories — are the only inputs to this plan.

---

## 1. Phase 1 — the real ArthOS baseline (verified in code, this branch)

| Capability | ArthOS status | Evidence | Production status | Remaining limitation |
|---|---|---|---|---|
| Discover + idea detail | BUILT, polished (Elite WebUI passes 1–2) | `v2/pages/Opportunities.tsx`, `PickPage.tsx`; truthful freshness (`v2/lib/freshness.ts`); approved "Meets the buy bar" copy default | Not deployed (web) | Per-idea "what changed" absent (M3) |
| Thesis Ledger | BUILT, flag-off | `domain/thesis/service.py` (state machine, `ALLOWED_TRANSITIONS`, no un-invalidating), migrations 110/111, `api/thesis.py` | Dev only | No UI beyond dev ThesisCard fixture; not linked from Inbox reports |
| Evidence + counter-evidence | BUILT | Bulls-vs-Bears equal prominence (`BothSidesCard`), thesis evidence rows w/ review-gating CHECKs (110) | Dev | Evidence generation is template/rule-driven; no LLM evidence in prod path |
| Mandatory falsifier | BUILT + DB-enforced | `MIN_WRONG_IF_LEN`, `ck_thesis_wrong_if_len` CHECK; UI "Exit if wrong" on every idea | Dev (schema), copy live in dev web | — |
| Attribution prototype | BUILT (reconciles to 2e-15) | `docs/research/ATTRIBUTION_PROTOTYPE.md`; MP1A/MP1S stamps (migrations 099/100, runtime-validated) | 099/100 deployed earlier; Elite parts dev | Portfolio-level rollup not surfaced |
| Calibration study | DONE (research) | `CONFIDENCE_CALIBRATION_REPORT.md`: High-band 54.4% vs ~64% implied, AUC 0.52 | Research only, honestly labeled | Fitted calibrator data-blocked (needs ≥3 quarters live decisions) |
| Confidence wording decision | DECIDED + SHIPPED (dev web default) | `CONFIDENCE_WORDING_DECISION.md`; `confidenceDisplay.ts` default-on | Dev web | Backend Trust Center body still says "copy change not yet applied" (stale sentence) |
| Trust Center | BUILT (backend + redesigned UI) | `api/trust_center.py` (6 honesty labels), `AdminTrustCenter.tsx` (grouped, no raw JSON) | Dev only | Sections limited to existing feeds; no action affordances (by design) |
| Research Inbox backend | BUILT | `domain/research_inbox/service.py` (forced-pending, versioned corrections, retained rejections), migration 112+117 | Dev, flag-off | `correct_report` has no HTTP route |
| Research Inbox UI | BUILT (this branch, dev flag) | `AdminResearchInbox.tsx` + 6 tests | Dev | No task board, no correction action, no thesis linking |
| Learning Loop | BUILT | `domain/learning/service.py`, migration 113, hindsight guard | Dev, flag-off | Aggregate lessons gated on N≥30 production outcomes |
| Experiment Lab | **NOT BUILT** (spec'd; 31–90d roadmap) | `walk_forward_baseline.py` script exists; no harness/registry writes | — | The biggest open Elite commitment |
| Research-run registry | BUILT | migration 109 (research_run + approval), `test_research_run_pg.py` | **109 applied to prod** | Not yet written to by a lab harness |
| Ingest contracts | BUILT, flag-off | `domain/prices/contracts.py`, 11+ tests, `INGEST_CONTRACTS_ENABLED=False` | Dev | Not wired into prod nightly |
| Drift monitoring | BUILT (SQL-first) | `domain/monitoring/drift.py`, `governance/drift_monitor.py`, `ml/drift_metrics.py`, 17+ tests | Dev | No owner UI panel |
| Realistic paper costs | BUILT (stamp), flag-off | `execution_costs.py` (`as_stamp`), migration 115, `PAPER_COST_MODEL_ENABLED=False` | Dev | Stamps recorded, not yet applied to fills/track-record math |
| Outcome tracking | BUILT + rich | `score_outcomes.py`, 75k+ resolved rows (dev), barrier labels/regimes/horizons | Partially in prod | Censored/still-open outcomes not modeled statistically |
| Agent Gateway R/P/B/D | BUILT, flag-off | `domain/agent_gateway/{tokens,audit,jobs}.py`, migrations 114/116/117, ~130 tests | Dev | In-memory rate limiter (single replica), owner-only principal |
| Gateway audit + token controls | BUILT | `audit.py`, owner console `/admin/agent-tokens` | Dev | No audit-log viewer UI; 30-day retention |
| Scheduler claims + execution lease | BUILT + fenced | `scheduling/execution_lease.py` (fence tokens), migration 118, 12 tests + live 6-way proof | Dev (118); prod scheduler still dual-run guarded | Flag off; prod promotion pending |
| Freshness / provider health | BUILT | `api/freshness.py` (19K), quote-age hardening, `ops/scheduling_health.py` | **In prod** (older rev) | Signals not unified into one machine-readable posture |
| Profile / personalization | BUILT (collect-only) | `ProfilePage.tsx` (why-we-ask), profile API | Dev web | Personalization consumes nothing yet (by design, honest) |
| Paper portfolio workspace | BUILT | Elite WebUI (demo-book honesty, snapshot honesty, share precision) | Dev web | Costs not in headline math (see paper costs) |
| Global error/empty/degraded states | BUILT | `StatusPanel`, `EvidenceBadge`, `RouteErrorBoundary`, 241-test suite | Dev web | — |
| Elite WebUI | DONE (2 passes) | `docs/ux/ELITE_WEBUI_AUDIT.md` + session report; all CRITICAL/HIGH + most MEDIUM closed | Dev web | M1 ticker values, M6 operator options vocabulary |
| Staged production promotion | PLANNED + gated | `ELITE_ARTHOS_PRODUCTION_PROMOTION_PLAN.md` (7 stages); B1 currently NO-GO (disk/log/scheduler blockers now largely remediated) | Stage B pending | The actual bottleneck for everything above |

**Rule applied below:** nothing is recommended merely because another repo
has it. Each gap survives only if the baseline above lacks it AND it serves a
beginner, trust, or evidence need.

---

## 2. Phase 2 — repository reviews vs the baseline

### A. OpenAlice (AGPL-3.0 — concepts only)

Strongest concepts and their ArthOS disposition:

| OpenAlice concept | ArthOS today | Verdict |
|---|---|---|
| Issue-based research tasks (self-describing spec) | `research_task` table (title/question/scope/schedule_expr) — equivalent core | ALREADY BUILT (backend); board UI missing |
| Inbox delivery + provenance (hash-pinned revision, launcher-stamped author) | Research Inbox: versioned reports, server-forced `pending`, `generated_by` stamped server-side (117) — same trust property achieved differently | ALREADY BUILT |
| Report versioning / corrections never overwrite | `correct_report` inserts version+1, old row byte-identical (pinned in tests) | ALREADY BUILT (missing only the HTTP route + UI action) |
| Scheduled/recurring research | `research_task.schedule_expr` exists; no runner wired | PARTIAL — wire to existing scheduler when Inbox is promoted |
| Human review with durable trail | approve/reject with reviewer identity, retained forever | ALREADY BUILT |
| Tracked entities + wikilink graph | Thesis Ledger has typed FK links (evidence/catalyst/risk/thesis_link) but no free entity (theme/sector/person) tracking, no cross-artifact navigation | **GENUINE PARTIAL GAP** → §4.1 |
| Research readiness (automation health separate from task status) | `scheduling_health.py` covers jobs; nothing per research-task | SMALL GAP → folds into Mission Board (§4.2) |
| Task handoff semantics (explicit assignee, no silent swap) | Gateway jobs carry token identity; single-owner product → low value now | DEFER (multi-user era) |
| Agent status visibility (stable ids, never self-identified) | Gateway audit stamps server-side identity — same property | ALREADY BUILT |
| Workspaces / terminals / generated-code execution / Trading-as-Git | — | **REJECT** (product boundary; execution environment + git-push-to-trade metaphor are terminal-feel and unsafe for beginners) |

### B. NOFX (AGPL-3.0 — concepts only)

| NOFX concept | ArthOS-safe translation | ArthOS today | Verdict |
|---|---|---|---|
| "Model proposes, runtime disposes" hard boundary | Deterministic gates the LLM/engine cannot override | Partially embodied (guardrails, review-gated evidence, forced-pending) but **no unified publication gate** | **BUILD** → Recommendation Publication Preflight (§4.3) |
| Launch preflight | Publication preflight per idea + system posture check | Scattered checks (enough_data, stale_data, contracts) — no verdict artifact | **BUILD** (§4.3) |
| Failure safe mode (quarantine new entries, keep exits alive) | Research Safe Mode: stop publishing NEW ideas when inputs degrade; keep existing ideas/portfolios readable; paper exits keep running | Nothing automatic — guard-absorbed failures logged only | **BUILD** (§4.4) |
| Full-cycle decision records (inputs→reasoning→decision→result as one audit unit) | Decision Replay Timeline reusing existing immutable artifacts (rec row + snapshot_hash + evidence + trades + outcome + lesson) | All artifacts exist; no unified read/UI | **BUILD (read-only)** (§4.5) |
| Model-attributed comparison / leaderboard | Owner-only offline Experiment Comparison Arena with evidence gates (no public profit ranking) | Experiment Lab not built yet | DESIGN → Wave 3 (§4.6) |
| Provider health monitoring | Freshness engine already stronger than NOFX's implicit retry | ALREADY BUILT (fold into posture signal) |
| Credential safety, venue-side stops, crypto perps, leverage, autopilot, public leaderboard, x402 payments | — | **REJECT** (no live trading, no credentials to protect beyond data keys, paper-only) |

### C. QuantDinger (Apache-2.0 backend)

| QuantDinger pattern | ArthOS today | Residual gap |
|---|---|---|
| Agent gateway + scoped tokens + paper-only default + append-only audit | Gateway R/P/B/D is equal-or-better (server-forced pending drafts, frozen job enum, queue caps, revoke-terminate SSE) | Gateway **token-management UX exists** (owner console) but no **audit-log viewer UI**; no **OpenAPI artifact** for the gateway |
| Two-key live-trading unlock | N/A — ArthOS has no live path at all (stronger position) | none |
| Fail-closed startup config validation (refuse default secrets) | Partial (`verify-deploy-safe`, preflight.py) | Small: adopt refuse-to-boot posture check in promotion plan — folded into Safe Mode/preflight work |
| Backtest lifecycle w/ SSE + cancel + persisted artifacts | Gateway jobs have SSE + cancel + caps; research_run registry for artifacts | **Experiment Lab harness still missing** (known); artifact-browser UI absent |
| Experiment comparison (frozen code+params snapshots) | research_run has git_sha + config_hash + seed (better reproducibility) | Comparison UI absent → Arena (§4.6) |
| OpenAPI from code | FastAPI auto-generates `/openapi.json` already | Residual: no exported, versioned gateway contract doc; trivial to add at promotion time |
| Multi-user roles, billing, mobile app shells, grid/live trading, 9 exchanges | Out of boundary | REJECT |
| Job lifecycle: thread-in-process workers | ArthOS DB-claim + fenced-lease scheduler is more durable | none — ArthOS ahead |

### D. Awesome-ML → vetted dependency shortlist (each verified on PyPI/GitHub 2026-07-12)

| Library | License | Verdict for ArthOS |
|---|---|---|
| scikit-learn 1.9 calibration | BSD-3 | PREFER-EXISTING — covers calibrator when data unblocks |
| LightGBM `pred_contrib` | MIT | PREFER-EXISTING — native exact contributions; SHAP redundant |
| MAPIE 1.4.1 | BSD-3 | **ADOPT-when-needed** (Wave 4) — conformal intervals, dep tree already installed |
| lifelines 0.30.3 | MIT | **ADOPT-when-needed** (Wave 4) — KM/CoxPH for censored open-position outcomes; only credible option at light-medium weight (matplotlib hard dep noted) |
| statsmodels 0.14.6 | BSD-3 | **ADOPT-when-needed** (Wave 3/4) — `multipletests` (Benjamini-Hochberg) for the Experiment Lab; light |
| Optuna 4.9 | MIT | ADOPT-when-needed (Experiment Lab sweeps; SQL storage reuses Postgres) |
| pandera 0.32.1 | MIT | NOT NEEDED — custom ingest contracts already shipped and tested (decision recorded in roadmap; stands) |
| statsforecast 2.0.3 | Apache-2 | **DEFER** — currently pins `scipy<1.16` vs our scipy 1.18: active resolver conflict. Revisit at Lab build time |
| River 0.25 | BSD-3 | DEFER — nightly batch pipeline; scipy KS/PSI drift already built |
| Evidently | Apache-2 | REJECT-too-heavy (second web server + NLTK on a small VM) |
| MLflow | Apache-2 | REJECT-too-heavy (a second app; SQL-first registry already exists and is the differentiator) |
| sktime | BSD-3 | DEFER — framework-sized; need estimators, not a toolkit |
| SHAP | MIT | REJECT-redundant vs `pred_contrib` |

---

## 3. Phase 3 — cross-repository capability matrix

Legend: ✔ has it · ◐ partial · ✗ absent · n/a out of scope for that repo.

| Capability | OpenAlice | NOFX | QuantDinger | ML eco | ArthOS today | Gap? | Recommendation |
|---|---|---|---|---|---|---|---|
| Research task management | ✔ | ✗ | ◐ (jobs) | n/a | ◐ backend only | UI gap | Mission Board (Wave 2) |
| Tracked entity graph | ✔ | ✗ | ✗ | n/a | ◐ typed thesis links | partial | Thin tracked-entity link model, DESIGN then PROTOTYPE (Wave 2) |
| Research memory (durable, navigable) | ✔ | ✗ | ◐ | n/a | ◐ (reports+theses, no navigation) | partial | Linking + navigation, Wave 2 |
| Report inbox | ✔ | ✗ | ✗ | n/a | ✔ (backend+UI) | no | — |
| Immutable corrections | ◐ | ✗ | ✗ | n/a | ✔ service (route/UI missing) | small | Correction route+UI (Wave 2) |
| Thesis lifecycle | ✗ | ✗ | ✗ | n/a | ✔ | no | ArthOS ahead |
| Evidence review gate | ◐ | ✗ | ✗ | n/a | ✔ | no | — |
| Recommendation preflight | ✗ | ✔ (launch) | ◐ (install) | n/a | ✗ unified | **YES** | **BUILD NEXT** (Wave 1) |
| Research safe mode | ✗ | ✔ | ✗ | n/a | ✗ | **YES** | **BUILD NEXT** (Wave 1) |
| Provider-health gate | ✗ | ◐ | ◐ | n/a | ✔ signals / ✗ gate | partial | Fold into preflight+safe mode |
| Decision replay | ◐ (audit) | ✔ | ◐ | n/a | ◐ artifacts w/o surface | **YES** | BUILD read-only timeline (Wave 1) |
| Outcome learning | ◐ | ✗ | ◐ (reflection) | ◐ | ✔ (Learning Loop) | no | — |
| Experiment registry | ✗ | ✗ | ◐ snapshots | MLflow (rejected) | ✔ (research_run, stronger reproducibility) | no | — |
| Experiment comparison UI | ✗ | ✔ leaderboard | ◐ | n/a | ✗ | YES | Arena, owner-only, Wave 3 |
| Model promotion gates | ✗ | ✗ | ◐ | n/a | ◐ spec'd, not built | YES | Promotion queue UI, Wave 3 |
| Model attribution | ✗ | ✔ per-model | ✗ | ◐ | ✔ (2e-15 reconciliation) | no | — |
| Calibration | ✗ | ✗ | ✗ | sklearn | ✔ measured (calibrator data-blocked) | no new | — |
| Drift | ✗ | ✗ | ✗ | River/Evidently (deferred/rejected) | ✔ SQL-first | no | Surface in Control Room later |
| Paper execution realism | ✗ | n/a | ◐ | n/a | ◐ stamps built, not applied | YES (known) | Apply cost model behind flag (Wave 4 w/ Lab evidence) |
| Agent gateway | ✗ | ✗ | ✔ | n/a | ✔ (≥ parity) | no | Export OpenAPI artifact at promotion |
| Job streaming + cancel | ✗ | ✗ | ✔ | n/a | ✔ (bounded SSE) | no | — |
| Audit viewer UI | ◐ | ◐ | ◐ | n/a | ✗ (data exists) | YES | Wave 3 |
| Mobile usability | ✗ | ✗ | ✔ (separate license) | n/a | ✔ responsive web | no | — |
| Operator control room | ✗ | ✔ dashboard | ✔ | n/a | ◐ (admin pages + Trust Center, fragmented) | YES | Wave 3 |
| Incident history | ✗ | ◐ | ✗ | n/a | ✔ (Trust Center honesty ledger) | no | — |
| Onboarding | ◐ | ✔ guided launch | ✔ install.sh | n/a | ✔ (why-we-ask, elite pass) | no | — |
| Accessibility | ✗ | ✗ | ✗ | n/a | ✔ (audited, tested) | no | ArthOS ahead |
| Explainability | ◐ | ✔ reasoning logs | ◐ | pred_contrib | ✔ (see-the-working + audit trail) | no | — |
| Multi-user isolation | ✗ | ✗ | ✔ | n/a | ✔ (named-user beta authz, 23-test matrix) | no | — |

---

## 4. Phase 4 — targeted gap investigations

### 4.1 Knowledge Graph — verdict: **DESIGN ONLY (thin), DEFER full graph**
Thesis Ledger already gives typed, DB-enforced links (thesis↔evidence/
catalyst/risk, thesis↔thesis supersedes). A full entity/relationship graph
(company/sector/theme/macro/person + 9 relation types) is owner-researcher
value, not beginner value; beginners get narrative, not graphs. The genuinely
useful slice: a `tracked_entity` (kind: symbol|sector|theme) + `entity_link`
(entity↔{thesis,report,recommendation}) so the Inbox can answer "show me
everything we know about semiconductors." That thin slice is designed in the
Opus plan (Wave 2, PROTOTYPE); free-text wikilinks are rejected (parser
surface, low trust value).

### 4.2 Research Mission Board — verdict: **PROTOTYPE (Wave 2)**
Needed: one owner surface over EXISTING state — research_task (+schedule),
research_report review states, gateway jobs (queued/running/failed), derived
staleness. Columns: Queued/Running/Review needed/Delivered/Corrected/Stale/
Failed. No new state machine, no new tables (a `blocked` state is NOT added —
nothing produces it today; harsh-review cut). Pure aggregation + navigation.

### 4.3 Recommendation Publication Preflight — verdict: **BUILD NEXT**
Deterministic gate producing a persisted verdict per candidate idea before
Discover exposure: READY / READY_WITH_LIMITATIONS / HOLD / BLOCKED.
Checks (all from existing signals): source freshness (freshness.py), ingest
contract status, enough_data, evidence present + counter-evidence (bears
non-empty), falsifier present (exit-if-wrong derivable), confidence wording
valid (label in allowed set), calibration status surfaced (chip data),
engine/snapshot provenance present, no open provider incident (safe-mode
posture), no duplicate open idea for symbol, entry/target/exit consistency
(target>entry>exit for Buy), prohibited-language scan (existing copy lint
list server-side). Paper-capacity check deferred (engine max_open already
enforces). **No LLM can override**: pure function of stored facts; verdict
row immutable. UI: LIMITATIONS render as honest chips on the idea.

### 4.4 Research Safe Mode — verdict: **BUILD NEXT**
System-level posture: NORMAL / RESTRICTED (publish with limitations) /
SAFE (no new publications). Triggered by: freshness beyond threshold, ingest
contract quarantine/abort, scheduler health red (stuck/overdue), drift
breach, provenance missing (git_sha unknown), outcome labeling stalled,
owner-declared incident. Existing ideas/portfolios stay readable; paper exit
cycle continues (mirrors "keep exits alive"). Recovery: automatic re-arm when
signals clear for a full cycle PLUS owner acknowledgment for SAFE→NORMAL;
every transition audited (who/what/why row). Trust Center shows posture;
Discover shows a calm banner in SAFE ("Publishing paused while data heals —
nothing you hold is affected").

### 4.5 Decision Replay Timeline — verdict: **BUILD (read-only)**
Everything needed already persists immutably: recommendation rows
(engine_version, snapshot_hash, family_scores, evidence, generated_at),
preflight verdicts (new), paper trades + costs stamps, thesis revisions,
outcomes, lessons. One read-only endpoint + one page:
`/today/pick/:symbol/history` (user) and owner deep view. Hindsight-proof
because it renders stored rows only — no recomputation of "what we would
have said." No migration.

### 4.6 Experiment Comparison Arena — verdict: **DESIGN ONLY now, build in Wave 3 after the Lab**
Blocked by the un-built Experiment Lab harness (the real Wave-3 anchor).
Arena = owner-only table over research_run rows: temporal OOS windows,
calibration (Brier/reliability), discrimination (AUC), drawdown, turnover,
cost-adjusted return (cost stamps), sample size, stability across windows,
reproducibility hash-check, promotion status. "Winner" requires evidence
gates (min sample, OOS, cost-adjusted, benchmark-relative) — enforced by the
existing registry promotion spec. No public leaderboard ever.

### 4.7 Owner Operations Control Room — verdict: **PROTOTYPE (Wave 3)**
Division of labor: **Trust Center = evidence & transparency (read, honest
labels)**; **Control Room = readiness & action (posture, gates, levers)**.
Contents: current posture (safe mode), publication-preflight rollup, provider
status, scheduler health, contracts, stale snapshots, outcome pipeline lag,
drift, active incidents, research jobs, promotion queue, gateway health +
token count, feature flags (read), disk/backup state (from ops scripts).
Mostly existing endpoints; new = posture + preflight rollup (Wave 1 outputs).

### 4.8 "What changed?" engine — verdict: **BUILD NEXT (smallest contract)**
No new tables. Service compares latest vs previous recommendation row per
symbol (both already stored): action changed, confidence label changed,
family_score deltas → plain-English "evidence added/removed", price move vs
entry/exit corridor, freshness delta, thesis revision reference (when
ledger on), outcome progress for held ideas. One endpoint
`GET /recommendations/{symbol}/delta` + reuse in Discover cards, PickPage
"What changed" block (fills mission Phase-4 narrative slot 4), Briefing
strip (already shipped shell), Inbox (report supersedes note).

### 4.9 Research Inbox UI completeness — verdict: gaps confirmed, small
Missing vs mission list: task list/board view (→ 4.2), correction action
(service exists, needs POST /reports/{id}/correct route + UI), follow-up
task creation from a report, thesis/entity linking (→ 4.1 thin slice).
Tasks/reports/versions/citations/freshness/review queue: all present.

### 4.10 ML / outcome science — verdicts (checked against code)
- Censored outcomes / survival: NOT modeled (open positions ignored by
  hit-rate). lifelines KM curve of time-to-TP/SL = honest addition. Wave 4.
- Class imbalance: shadow-model era concern; registry records it; DEFER.
- Probability calibration: measured; calibrator DATA-BLOCKED (documented) —
  re-study trigger already defined. No action now.
- Prediction intervals: MAPIE when calibrator unblocks. Wave 4.
- Regime stability: regime snapshots exist; stability analysis = Lab metric.
- Statistical significance + multiple testing: MISSING; statsmodels
  `multipletests` in Lab harness. Wave 3.
- Benchmark robustness: Lab scope (buy-and-hold, 12-1) — spec'd, unbuilt.
- Feature leakage: PIT lookups exist (`data/pit_lookup.py`); Lab adds purged
  walk-forward as the systematic guard.
- Survivorship/delisted/corporate actions: KNOWN limitation (universe from
  current constituents; splits handled, delistings not). Document in Lab
  data-quality preamble; defer fixing until universe expansion (BP28 line).
- Transaction-cost sensitivity: cost stamps built; sensitivity sweep = Lab.
- Portfolio-level attribution: per-position built; rollup = small SQL view
  in Arena. Wave 4.

---

## 5. Phase 5 — classification & scores

Scale 1–5 (5 best; effort/risk 5 = low effort/low risk). Priority =
(beginner+trust+evidence+differentiation) weighted against (effort+risks).

| Idea | Class | Beginner | Trust | Evidence | Diff | Effort | Sec risk | Lic risk | Infra | Deps | Prod risk | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Publication Preflight | **BUILD NEXT** | 4 | 5 | 5 | 5 | 3 | 5 | 5 | 5 | 5 | 4 | **P1** |
| Research Safe Mode | **BUILD NEXT** | 4 | 5 | 4 | 5 | 3 | 5 | 5 | 5 | 5 | 4 | **P1** |
| "What changed?" contract | **BUILD NEXT** | 5 | 4 | 3 | 4 | 4 | 5 | 5 | 5 | 5 | 5 | **P1** |
| Decision Replay Timeline | **BUILD NEXT** (read-only) | 4 | 5 | 4 | 5 | 3 | 5 | 5 | 5 | 5 | 5 | **P2** |
| Inbox completeness (correction route/UI, follow-ups) | **BUILD NEXT** (small) | 2 | 4 | 4 | 3 | 5 | 5 | 5 | 5 | 5 | 5 | **P2** |
| Research Mission Board | **PROTOTYPE** | 2 | 4 | 3 | 4 | 4 | 5 | 5 | 5 | 5 | 5 | P3 |
| Tracked-entity thin slice | **PROTOTYPE** (after design) | 2 | 3 | 4 | 4 | 3 | 5 | 5 | 5 | 5 | 5 | P3 |
| Experiment Lab harness (pre-existing commitment) | **BUILD** (Wave 3 anchor) | 2 | 5 | 5 | 5 | 2 | 5 | 5 | 4 | 4 | 4 | P2* |
| Comparison Arena UI | **DESIGN ONLY** → Wave 3 | 1 | 4 | 5 | 4 | 3 | 5 | 5 | 5 | 5 | 5 | P3 |
| Promotion queue UI | DESIGN ONLY → Wave 3 | 1 | 4 | 5 | 4 | 4 | 5 | 5 | 5 | 5 | 5 | P3 |
| Audit-log viewer | PROTOTYPE → Wave 3 | 1 | 4 | 3 | 3 | 4 | 4 | 5 | 5 | 5 | 5 | P4 |
| Owner Control Room | PROTOTYPE → Wave 3 | 1 | 4 | 3 | 4 | 3 | 4 | 5 | 5 | 5 | 5 | P3 |
| Survival analysis (lifelines) | DEFER → Wave 4 | 2 | 3 | 5 | 4 | 3 | 5 | 5 | 5 | 4 | 5 | P4 |
| MAPIE intervals | DEFER (data-blocked with calibrator) | 3 | 4 | 4 | 4 | 4 | 5 | 5 | 5 | 5 | 5 | P4 |
| statsmodels multiple-testing | ADOPT in Lab | 1 | 4 | 5 | 3 | 5 | 5 | 5 | 5 | 5 | 5 | P3 |
| Gateway OpenAPI artifact export | BUILD (tiny, at promotion) | 1 | 3 | 2 | 2 | 5 | 5 | 5 | 5 | 5 | 5 | P4 |
| Full knowledge graph (9 relation types) | **DEFER** | 1 | 2 | 3 | 3 | 1 | 4 | 5 | 4 | 5 | 4 | — |
| Wikilink free-text linking | **REJECT** (parser surface, no beginner value) | — | — | — | — | — | — | — | — | — | — | — |
| Task handoff/assignee semantics | **DEFER** (single-owner today) | — | — | — | — | — | — | — | — | — | — | — |
| Workspaces/terminals/codegen execution | **REJECT** (boundary) | — | — | — | — | — | — | — | — | — | — | — |
| Trading-as-Git execution | **REJECT** (boundary) | — | — | — | — | — | — | — | — | — | — | — |
| Autonomous trading/exchanges/leverage/crypto/leaderboard | **REJECT** (boundary) | — | — | — | — | — | — | — | — | — | — | — |
| MLflow/Evidently/SHAP/sktime/River | **REJECT/DEFER** (weight vs need; §2D) | — | — | — | — | — | — | — | — | — | — | — |
| pandera | ALREADY DECIDED (custom shipped) | — | — | — | — | — | — | — | — | — | — | — |

\* Experiment Lab is P2 by value but Wave 3 by sequencing (bigger build; the
Wave-1 spine is smaller and unblocks trust messaging immediately).

## Phase 8 — harsh review (what got cut and why)

- **Full knowledge graph** — bigger, not more trustworthy; beginners don't
  navigate graphs. Thin typed slice only, and only in Wave 2.
- **Wikilinks** — cute, unparseable trust story, injection surface. Cut.
- **`blocked` column on Mission Board** — no producer of that state exists;
  inventing states for symmetry is dashboard theater. Cut.
- **Public Trust Center changes** — out of scope; remains its own HARD STOP.
- **Leaderboards of any kind** — competition framing contradicts "calm,
  credible"; Arena is owner-only with evidence gates.
- **New infra services** — zero added: no Redis, no queue, no MLflow, no
  Evidently server. Everything below is Postgres + FastAPI + existing web.
- **Immediate statsforecast adoption** — real resolver conflict today
  (scipy pin). Deferred with a re-check gate.
- **Anything touching production** — every item is dev-first, flag-off,
  additive-migration only; production promotion of EXISTING Elite work
  (Stage B onward) remains the program's actual critical path and is not
  displaced by this roadmap.

Deliverable plan: `docs/roadmap/POST_ELITE_OPUS_IMPLEMENTATION_PLAN.md` ·
machine-readable scores: `docs/roadmap/post_elite_priority_matrix.json`.
