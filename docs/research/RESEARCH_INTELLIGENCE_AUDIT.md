# RESEARCH INTELLIGENCE + AUDIT LAYER — Phase A No-Code Audit

**Status:** Phase A audit. No code, no schema, no migrations, no API/UI scaffolding. Validation only.
**Source synthesis:** `C:\Users\kunal\.claude-octopus\research\research-intelligence-layer-synthesis.md` (multi-provider review by Codex CLI + Gemini CLI + Claude Opus + Claude Sonnet, completed 2026-04-30).
**Branch:** `phase-1/ledger`.
**Author signature line (operator):** _________________________ Date: __________

---

## Executive Position

Read-only research artifacts only. Zero `Adopt` ratings across 10 reviewed repos. Strongest disposition is `Adapt patterns only` — nothing enters our system as a runtime dependency, no execution path, no scheduler entry, no POST endpoint in Phase B. All architectural choices encode a triple-redundant isolation invariant (DB layer + runtime layer + CI layer) so research artifacts are physically incapable of becoming execution inputs.

This document is the gate to Phase B. Operator signature required at the bottom before Phase B (schema-only) work begins.

---

# SECTION 1 — Per-Repo Classification

For each repo: disposition · components extracted · execution surfaces (rejected) · memory systems (rejected) · dependencies (rejected).

---

## 1. TauricResearch/TradingAgents

**Disposition:** Adapt patterns only.

**Pattern extracted (concepts only, NOT code, NOT runtime):**
- Per-agent narrative production with role taxonomy (4 analysts: fundamentals/sentiment/news/technical → bull researcher → bear researcher).
- Bull/Bear/Tension structured debate summary as a *narrative artifact*, NEVER as a directional signal.
- Reflection mechanism reframed as labeled history only — store realized return + benchmark return alongside the run; never feed back into agent memory or scoring.

**Files / modules in TradingAgents that inform our schema (not borrowed verbatim):**
- `tradingagents/graph/setup.py` — informs the staged DAG concept (we re-implement with our async worker primitives).
- `tradingagents/agents/utils/agent_states.py` — informs our `agent_role` enum.
- `tradingagents/agents/schemas.py` — informs Pydantic structured-output discipline.
- `tradingagents/graph/reflection.py` — informs `research_reflection` table shape.

**Execution surfaces (REJECTED):**
- `Trader` LangGraph node — emits BUY/SELL/HOLD strings. **Reject outright.**
- `Risk Manager` decisioning role — sizes positions. **Reject.**
- `Portfolio Manager` LangGraph node — allocates capital. **Reject.**
- Simulated exchange sink — parallel execution path. **Reject.**

**Memory systems (REJECTED):**
- `~/.tradingagents/memory/trading_memory.md` filesystem persistence — unsigned, mutable, escapes Postgres audit. **Reject.**
- Any reflection-write-back-to-memory edge that lets past decisions shape future agent prompts. **Reject the edge; keep the row only as labeled history.**

**Dependencies (REJECTED):**
- `langgraph` runtime — banned per synthesis constraint.
- `langchain` runtime — banned (transitive surface, version churn, structured-output-via-LLM-routing risk).
- LangGraph filesystem checkpointer (`SqliteSaver`, etc.) — banned. Postgres `research_checkpoint` only.

---

## 2. TraderAlice/OpenAlice

**Disposition:** Adapt discipline only.

**Pattern extracted:**
- Append-only event log discipline: every action recorded as an immutable row with monotonic id and provenance.
- Pre-execution Guard pipeline pattern: validation gates run before any side effect — adapted for us as **DB CHECK constraints + token-strip regex on INSERT** (not a Python-layer "guard pipeline").
- Per-event provenance fields: provider, model, version, prompt_hash, tokens, cost — informs our mandatory-NOT-NULL provenance column block.
- Operator-approval-as-a-gate concept: adapted for us as the Phase A → Phase B operator signature gate (no PR merges into research_ro before this audit is signed).

**Files / modules in OpenAlice that inform our schema:**
- `Trading-as-Git` event-log abstraction — informs append-only INSERT-only role discipline.
- `Guard pipeline` modules — informs CHECK constraint design and CI grep gate.
- Claude Agent SDK telemetry hooks — informs cost/token accounting columns.

**Execution surfaces (REJECTED):**
- `brokers/alpaca*` adapter — **Reject.**
- `brokers/ibkr*` adapter — **Reject.**
- `brokers/ccxt*` adapter — **Reject.**
- Heartbeat agent loop (`agent_loop.ts` or equivalent) — autonomous cadence with broker access. **Reject.**
- "Trading-as-Git" UI framing (push/commit/approve workflow that ends in a real order) — **Reject the UI flow**; adopt only the immutable event-log property at the DB layer.

**Memory systems (REJECTED):**
- "Brain" persistent memory module — encodes trading bias across runs. **Reject.**
- Emotion-tracking module entirely (anthropomorphizes the model; not auditable as facts). **Reject.**
- Vercel AI SDK streaming-action pattern that mutates session state mid-stream. **Reject.**

**Dependencies (REJECTED):**
- Any direct `pnpm add openalice/*` import — entire monorepo execution-coupled. **Reject.**
- Vercel AI SDK as runtime dep when used for streaming actions. (Vercel AI SDK as a thin LLM transport in a future phase is a Phase D+ decision, not Phase B.)
- Claude Agent SDK as a runtime dep — postponed to Phase D+ evaluation; not in Phase A or B.

---

## 3. HKUDS/Vibe-Trading

**Disposition:** Research-only-pattern (concept inspiration, no code import).

**Pattern extracted:**
- Stack alignment validation — Vibe-Trading runs FastAPI + React 19, matching our stack exactly. Confirms our architectural shape is industry-standard for this class of system.
- 5-layer prompt-compression hierarchy → informs our `prompt_template_id` + `prompt_template_version` provenance columns.
- Provider abstraction with 12+ LLM backends → confirms `provider` enum column scope.
- "Preset" naming concept (29 swarm presets like "Value Committee", "Macro Desk") → informs UI methodology badge ("Generated by: 'Value Committee' preset").
- Simulation-only disclaimer posture is the right ceiling for research outputs.

**Files / modules in Vibe-Trading that inform us (concept only):**
- ReAct agent core — informs the conceptual DAG shape; we do NOT use ReAct, we use deterministic sequential nodes.
- 72 specialist skill catalog — informs the *concept* of versioned named skills; we cap at 4-6 agent_role enum values, not 72.
- Provider routing layer → informs our Phase D Pydantic provider abstraction.

**Execution surfaces (REJECTED):**
- The 7 backtest engines exposed as agent skills — **Reject** any LLM-routed dispatch into our backtester.
- Skill-execution dispatcher (LLM output → handler name) — **Reject** as command-injection vector.
- 29 swarm-preset orchestration — **Reject** the runtime; adopt the *naming* concept only as a UI badge.

**Memory systems (REJECTED):**
- `~/.vibe-trading/memory/` filesystem store — **Reject.** No filesystem persistence anywhere in our research layer.

**Dependencies (REJECTED):**
- LangChain as runtime routing layer — **banned.**
- Any LLM-output-as-routing-key pattern (`getattr(module, llm_output)`) — **banned**, enforced by AST scan in CI.

---

## 4. tensortrade-org/tensortrade

**Disposition:** Research-only-pattern.

**Pattern extracted:**
- Decomposition discipline: Observer / Action / Reward as separable concerns → informs our schema separation: `research_run` (input snapshot) / `research_agent_output` (derivation) / `research_reflection` (outcome). Each independently verifiable.
- Reward-scheme decomposition concept → research-side narrative scoring breakdown only; never feeds the alpha rule snapshot.

**Files / modules in tensortrade that inform us:**
- `TradingEnv` abstraction — informs schema-level separation, not runtime.
- `RewardScheme` decomposition — informs reflection-component framing.
- `Observer` abstraction — informs the `input_snapshot_hash` provenance column.

**Execution surfaces (REJECTED):**
- `ActionScheme` integration with our recommendation engine — **Reject.**
- `Portfolio` mutation — **Reject.**
- RL agent training that ingests `paper_decision_log` → ML-execution coupling. **Reject.**

**Memory systems (REJECTED):**
- N/A in Phase B scope (tensortrade has no LLM memory layer).

**Dependencies (REJECTED):**
- `Ray RLlib` — heavy runtime, not needed for narrative research. **Reject.**
- `TensorFlow` — same reason. **Reject.**
- `Optuna` — RL hyperparameter tuning, out of scope. **Reject.**
- PPO training pipeline — RL is non-deterministic; conflicts with our deterministic, idempotent research-run requirement. **Reject.**

---

## 5. huseinzol05/Stock-Prediction-Models

**Disposition:** Reject (literature only).

**Pattern extracted:** None operationally. Cited in audit as "what we explicitly chose not to build" reference. Provenance discipline lesson: this repo lacks model cards entirely, reinforcing why our `provider`/`model_id`/`model_version`/`prompt_hash` columns are NOT NULL.

**Files / modules:**
- 18 deep-learning forecaster notebooks — reference reading.
- 23 RL agent implementations (Q-learning, actor-critic, evolution strategies) — reference reading.

**Execution surfaces (REJECTED):**
- All 23 RL agents as runnable code — **Reject** any direct `pip` / `requirements.txt` ingest.
- Any pickled model weights — **Reject** binary/weight ingest.

**Memory systems (REJECTED):**
- N/A.

**Dependencies (REJECTED):**
- Repo archived 2023-07; no security maintenance, transitive CVE risk. **Reject** any direct dependency.

---

## 6. HKUDS/AI-Trader

**Disposition:** Research-only-pattern.

**Pattern extracted:**
- Per-agent track-record concept → informs `research_reflection` aggregations as **internal-only** model-performance metrics on `JobsHealth.tsx` (catalyst-id accuracy, volatility correlation), never user-facing, never feeding ranking.
- Signed agent-identity pattern — informs the integrity property that artifacts carry verifiable provenance.

**Files / modules:**
- Agent registration + signature flow — informs provenance discipline.
- Reputation-aggregation logic — informs reflection-aggregation views.

**Execution surfaces (REJECTED):**
- All exchange adapters (Binance / Coinbase / IBKR) — **Reject.**
- Copy-trade subscription mechanism — **Reject** (research outputs become orders).
- Signal-publication endpoints — **Reject.**
- Reputation feeding any ranking surface — **Reject.** Reputation-as-implicit-signal is exactly the subtle decision channel that bypasses token blocking; it must remain internal-only on JobsHealth.

**Memory systems (REJECTED):**
- Cross-agent reputation state mutating in real time — **Reject.**

**Dependencies (REJECTED):**
- All exchange SDKs — **Reject.**

---

## 7. NoFxAiOS/nofx

**Disposition:** Reject (counter-example only).

**Pattern extracted:** None. Cited in Phase A audit as the autonomous-execution archetype we explicitly reject. Motivates the hard rule that `research_writer` has zero write access to ANY execution table, and the architectural import test that bans references to autonomous loops.

**Files / modules:** N/A (no integration planned).

**Execution surfaces (REJECTED):**
- Entirely. Specifically: x402 micropayment loop, all 9+ CEX adapters, all 3+ DEX adapters, autonomy heartbeat, agent wallet handling.

**Memory systems (REJECTED):**
- Entirely.

**Dependencies (REJECTED):**
- Go runtime — **N/A** (we don't run Go).
- All exchange SDKs — **Reject.**
- x402 protocol client — **Reject.**

---

## 8. brokermr810/QuantDinger

**Disposition:** Research-only-pattern.

**Pattern extracted:**
- Postgres-as-source-of-truth posture — already matches our system architecture; reinforces the design choice.
- Module-boundary discipline (separate `research/` and `execution/` directories at the import-graph level) — informs our CI architectural import test.
- OAuth-protected read-only research dashboard pattern — already implicit in our auth.

**Files / modules:**
- Docker-compose layout for service isolation — informs our deployment posture (already aligned).
- SECRET_KEY enforcement pattern — already aligned.

**Execution surfaces (REJECTED):**
- All four exchange adapters (Binance / IBKR / MT5 / Polymarket) — **Reject.**
- Polymarket integration (prediction market) — **Reject.**

**Memory systems (REJECTED):**
- Redis as agent-memory bus / cross-agent state store — **Reject.** We use Postgres `research_checkpoint` exclusively. No Redis state for research runs.

**Dependencies (REJECTED):**
- Redis as research persistence — **Reject** (Postgres only).
- Vue frontend — **N/A** (we use React).
- Flask backend — **N/A** (we use FastAPI).

---

## 9. EliteQuant/EliteQuant

**Disposition:** Adapt (discovery index only).

**Pattern extracted:** Use as a research backlog / discovery index for future audit phases. No code, no execution, just a curated link list.

**Files / modules:** N/A (it's a README of links).

**Execution surfaces (REJECTED):**
- N/A — no code in this repo. Risk is only **transitive trust in linked repos** without re-running this audit. Rule: any followed link must pass its own Phase A audit before Phase B work for that link begins.

**Memory systems (REJECTED):** N/A.

**Dependencies (REJECTED):** N/A.

---

## 10. jamesmawm/HFT-with-IB

**Disposition:** Reject.

**Pattern extracted:** Cointegration / spread z-score math is well-documented but already covered better in our R2 deep-extraction (`docs/research/quant-repos-extraction-v2-deep.md`). Pairs concepts are a Phase F+ feature-engine concern, not a research-intelligence-layer concern. Nothing extracted for the research_ro layer.

**Files / modules:** None borrowed.

**Execution surfaces (REJECTED):**
- IBKR adapter — **Reject.**
- HFT order loop — **Reject.** Latency-driven autonomy normalizes removing the human; the philosophical risk alone disqualifies this repo from any Phase A/B integration.
- Dockerfile — **Reject** (it bundles execution).

**Memory systems (REJECTED):**
- Live tick subscription state — **Reject.**

**Dependencies (REJECTED):**
- IBKR API — **Reject.**

---

# SECTION 2 — Token Leakage Map

For each adopted pattern, the leakage points and how the triple guard (DB CHECK + server filter + client guard) blocks them.

## 2.1 TradingAgents — Bull/Bear debate adoption

**Leakage origins:**
- **Prompts:** TradingAgents bull/bear prompts ask the model to "recommend" a trade; if we reuse them verbatim, the LLM emits tokens like "buy", "sell", "target price", "position size".
- **LLM outputs:** even with neutralized prompts, models hallucinate action verbs ("the data suggests a buy here").
- **UI labels:** TradingAgents UI surfaces "BUY thesis" / "SELL thesis" — must never appear in our React components.
- **Logs:** any logger.info() that echoes raw LLM output to stdout would expose tokens to the worker log surface.

**Failure paths blocked:**
1. Prompt with action verbs → we rewrite prompts to use "narrative analysis" framing only; CI source-token grep on `apps/api/src/research/**` would catch any forbidden token in a prompt template at build time.
2. LLM emits "buy" in `body` field → `CHECK body !~* '\m(buy|...)\M'` rejects INSERT; row written to a separate `research_run_rejected` table with `status='token_violation'`. No partial write.
3. Body somehow bypasses CHECK (impossible for a non-superuser, but defense in depth) → server-side render filter scans before serialization to client; returns the standardized `Research note rejected — content failed safety check.` block.
4. Client receives a body that should have been blocked → client-side render guard repeats the regex scan; renders fail-closed message instead of body.
5. Logger output → no `logger.info(body)` calls allowed in `apps/api/src/research/**` (CI source grep).

## 2.2 OpenAlice — Append-only event log adoption

**Leakage origins:**
- **Event-log entries:** OpenAlice events embed action verbs ("trade staged", "order pushed"). If we mirror their event taxonomy verbatim, our `research_run` rows could carry verbs in `error_message` or `error_code` fields.
- **Status enum:** OpenAlice statuses include "approved", "executed" — must never appear in our `research_run_status` enum.

**Failure paths blocked:**
1. Status enum hardcoded to safe values (`pending`, `running`, `succeeded`, `failed`, `partial`, `token_violation`, `cost_exceeded`, `provider_error`, `timeout`, `schema_violation`) — no "approved", no "executed". DB enforces enum at row insert.
2. `error_message` text is bounded by length and passed through the same token-strip CHECK if it ever rendered to UI (Phase B keeps it server-only).
3. CI source-token grep catches any reintroduction of "approve" / "execute" tokens in our research code.

## 2.3 Vibe-Trading — Preset / methodology badge adoption

**Leakage origins:**
- **Preset names:** Vibe-Trading uses presets like "HFT Swarm", "Day Trader Desk" — embedded action language.
- **Skill names:** 72 skill names include verbs like "execute_backtest", "place_simulated_order".

**Failure paths blocked:**
1. We curate our own preset names; no automatic import. Names lint-checked against forbidden-token regex.
2. CI source grep on `apps/web/src/components/research/**` catches any UI string containing "buy"/"sell"/etc.
3. Methodology badge UI component renders a server-validated string — never a free-text user input.

## 2.4 AI-Trader — Reputation-as-internal-metric adoption

**Leakage origins:**
- **Reputation labels:** AI-Trader exposes reputation as user-facing leaderboards; user perceives high-reputation agent as a buy signal.
- **Score names:** "win rate", "PnL%" — directional language.

**Failure paths blocked:**
1. Reputation surface is internal-only on `JobsHealth.tsx` (extends Phase 11V data-health convention). Never user-facing on `Recommendations.tsx` or `Dashboard.tsx`.
2. Metric names rewritten as non-directional: "catalyst identification accuracy", "volatility correlation coefficient". No "win rate", no "PnL", no "alpha".
3. Forbidden-token client-render guard list extended to include `outperform`, `underperform`, `alpha`, `forecast`, `prediction` (Gemini contribution).

## 2.5 tensortrade — Decomposition adoption

**Leakage origins:**
- **Reward-scheme components:** tensortrade rewards include `pnl_change`, `position_value` — directional language.

**Failure paths blocked:**
1. We do NOT borrow tensortrade reward fields. We borrow only the *separation pattern* (input/derivation/outcome are separate tables). No language imported.

## 2.6 OpenAlice / TradingAgents — Reflection adoption

**Leakage origins:**
- **Reflection prompts:** TradingAgents reflection asks "did the trader make the right call?" — the LLM responds with action verbs.
- **Realized-return commentary:** even neutralized, the model writes "this position outperformed".

**Failure paths blocked:**
1. Reflection prompts rewritten to ask for "narrative observation about realized return vs benchmark" — no questions about "the right call".
2. `research_reflection.body` carries CHECK constraint identical to `research_agent_output.body`.
3. Reflection rows have **no FK** into `paper_decision_log` or `candidate_idea`; `decision_id` is plain text. Research rollback is independent of execution rollback.
4. Reflection cannot write back to agent memory (no agent memory exists in our system; only Postgres rows).
5. CI architectural import test forbids `apps/api/src/research/**` from importing `feature_engine`, `recommendation_engine`, `shadow_scorer`, `drift_monitor`, `auto_trader`, `paper_execution` — no code path exists for reflection to influence scoring.

---

# SECTION 3 — Dependency Surface

Per repo: runtime deps · SAFE (concept only) vs REJECT (must not enter).

## 3.1 TradingAgents
| Dep | Disposition | Reason |
|---|---|---|
| `langgraph` | **REJECT** | Banned per synthesis. Conceptual DAG inspiration only. |
| `langchain` | **REJECT** | Transitive surface, version churn, LLM-routing risk. |
| `pydantic` | SAFE (concept only) | We already use Pydantic; structured-output discipline is our existing pattern. |
| `tradingagents/*` (the package itself) | **REJECT** | Not pip-installable into our system. |
| Filesystem persistence (`~/.tradingagents/`) | **REJECT** | Postgres-only. |

## 3.2 OpenAlice
| Dep | Disposition | Reason |
|---|---|---|
| `@anthropic-ai/sdk` (Claude Agent SDK) | **REJECT (Phase A/B)** | Postponed to Phase D+ evaluation; not in scope. |
| `ai` (Vercel AI SDK) | **REJECT (Phase A/B)** | Postponed to Phase D+. |
| `pnpm` workspace structure | N/A | We're Python-first. |
| `ccxt` / `@alpacahq/*` / `ib_insync` | **REJECT** | Broker SDKs. |

## 3.3 Vibe-Trading
| Dep | Disposition | Reason |
|---|---|---|
| `langchain` | **REJECT** | Banned. |
| `langchain_openai`, `langchain_anthropic`, etc. | **REJECT** | LangChain ecosystem. |
| `yfinance` | **N/A** | We have Tiingo + Polygon; not adopting yfinance. |
| `vibe_trading/*` (the package) | **REJECT** | Not pip-installable into our system. |
| Filesystem persistence (`~/.vibe-trading/`) | **REJECT** | Postgres-only. |

## 3.4 tensortrade
| Dep | Disposition | Reason |
|---|---|---|
| `tensortrade` | **REJECT** | RL framework; non-deterministic; out of scope. |
| `ray[rllib]` | **REJECT** | Heavy runtime; out of scope. |
| `tensorflow` | **REJECT** | Heavy runtime; out of scope. |
| `optuna` | **REJECT** | Hyperparam tuning; out of scope. |

## 3.5 Stock-Prediction-Models
| Dep | Disposition | Reason |
|---|---|---|
| `tensorflow` (legacy) | **REJECT** | Archived 2023-07; no maintenance. |
| Repo as a whole | **REJECT** | Literature only. |

## 3.6 AI-Trader
| Dep | Disposition | Reason |
|---|---|---|
| All exchange SDKs (Binance, Coinbase, IBKR) | **REJECT** | Live execution. |
| FastAPI / React stack | N/A | We already have these — reinforces alignment. |

## 3.7 NOFX
| Dep | Disposition | Reason |
|---|---|---|
| Go runtime | **N/A** | We don't run Go. |
| All exchange SDKs (9+ CEX, 3+ DEX) | **REJECT** | Live execution. |
| x402 protocol client | **REJECT** | Micropayment-incentivized loop. |

## 3.8 QuantDinger
| Dep | Disposition | Reason |
|---|---|---|
| Exchange adapters (Binance, IBKR, MT5, Polymarket) | **REJECT** | Live execution. |
| Redis | **REJECT (as research state bus)** | Postgres-only for research. (Existing Redis usage outside research is unaffected.) |
| Flask | **N/A** | We use FastAPI. |
| Vue | **N/A** | We use React. |

## 3.9 EliteQuant
| Dep | Disposition | Reason |
|---|---|---|
| N/A (link list only) | — | No code; no deps to import. |

## 3.10 HFT-with-IB
| Dep | Disposition | Reason |
|---|---|---|
| `ib_insync` | **REJECT** | IBKR live trading. |
| Repo's Dockerfile | **REJECT** | Bundles execution. |

## Explicit confirmations (mandatory)
- **`langgraph` = NOT ALLOWED** as a runtime dep. CI dependency lint enforces.
- **`langchain` = NOT ALLOWED** as a runtime dep. CI dependency lint enforces.
- **No filesystem persistence anywhere** — no `~/.tradingagents/`, `~/.vibe-trading/`, `~/.openalice/`, no other home-relative paths in `apps/api/src/research/**`. CI filesystem-egress lint enforces.
- **No exchange SDKs** anywhere in `apps/api/src/research/**` or `apps/worker/src/research/**` (the latter does not exist in Phase B and will not until a future phase is approved).

---

# SECTION 4 — Data Flow Validation

Trace the complete safe flow and prove no path back to execution exists.

## 4.1 Flow trace (Phase B ships steps 1-2 only as feature-flagged shells; later phases populate)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. INPUT (public schema, READ-ONLY relative to research_writer role)    │
│    - public.candidate_idea  (research_writer: SELECT only)              │
│    - public.paper_run_log   (research_writer: SELECT only)              │
│    - public.context_daily   (research_writer: SELECT only)              │
│    - public.factor_snapshot (research_writer: NO ACCESS)                │
│    - public.alpha_rule_snapshot (research_writer: NO ACCESS)            │
│    - public.paper_decision_log (research_writer: NO ACCESS)             │
└─────────────────────────────────────────────────────────────────────────┘
                                  │ SELECT (whitelisted)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. RESEARCH PROCESS (FUTURE PHASE C-E; not in Phase A or B)             │
│    - Read public inputs as research_writer.                             │
│    - Render prompt server-side; compute prompt_hash.                    │
│    - Call LLM provider with bounded payload (egress allowlist).         │
│    - Parse structured output via Pydantic; fail-closed on malformed.    │
│    - Strip body through token regex; reject row if token present.       │
│    - INSERT into research_ro.research_run + linked tables               │
│      with provenance + cost telemetry NOT NULL.                         │
└─────────────────────────────────────────────────────────────────────────┘
                                  │ INSERT (research_writer)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. PERSIST (research_ro schema)                                         │
│    - research_run, research_agent_output, research_debate_summary,      │
│      research_reflection, research_checkpoint                           │
│    - All append-only (no UPDATE/DELETE granted to research_writer).     │
│    - All body cols protected by CHECK token-strip.                      │
│    - All provenance cols NOT NULL.                                      │
│    - Idempotency unique key on research_run.                            │
│    - FK direction: research_ro → public allowed; reverse forbidden.     │
└─────────────────────────────────────────────────────────────────────────┘
                                  │ SELECT (research_reader)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. API (apps/api/src/api/research.py — GET-only, Phase B stubs)         │
│    - GET /api/research/runs                  → empty list in Phase B    │
│    - GET /api/research/runs/{run_id}         → 404 in Phase B           │
│    - GET /api/research/ticker/{symbol}/latest → null in Phase B         │
│    - GET /api/research/decision/{decision_id} → empty list in Phase B   │
│    - Server-side render filter scans body before serialization.         │
│    - No POST/PUT/PATCH/DELETE handlers; CI test asserts.                │
└─────────────────────────────────────────────────────────────────────────┘
                                  │ HTTP GET
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. UI (apps/web/src/components/research/ — read-only)                   │
│    - ResearchIntelligenceTab on Recommendations.tsx (flag-gated).       │
│    - ResearchPulseCard on Dashboard.tsx (flag-gated).                   │
│    - ResearchJobHealthCard extends JobsHealth.tsx (flag-gated).         │
│    - Mandatory ResearchBanner prop (render guard throws if missing).    │
│    - Client-side render guard repeats token regex; fail-closed render.  │
│    - No buttons matching action verbs (CI snapshot test asserts).       │
│    - No recommendation iconography (CI snapshot test asserts).          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 4.2 Proof: no path exists back to execution

The data flow is unidirectional: `public → research_ro → API → UI`. Reverse direction is blocked by **four independent mechanisms**:

1. **Schema isolation:** `research_ro` is a distinct Postgres schema; `research_writer` has zero `INSERT/UPDATE/DELETE/TRUNCATE` privileges on any `public.*` table. Any attempted reverse write produces `permission denied` at the database, before the SQL even runs against table data.

2. **FK direction:** FKs may point `research_ro → public` (e.g., `research_run.candidate_idea_id` referencing `public.candidate_idea(id)`). The reverse is forbidden, enforced by an Alembic FK scan that fails any migration introducing `public → research_ro` FKs.

3. **Architectural import test:** the CI gate forbids any module under `apps/api/src/research/**` from importing `feature_engine`, `recommendation_engine`, `shadow_scorer`, `drift_monitor`, `auto_trader`, or `paper_execution`. No Python call path exists for research code to invoke an execution function.

4. **Read-only API:** the FastAPI router under `/api/research/*` exposes only GET handlers. POST/PUT/PATCH/DELETE handlers are not registered (verified by `test_research_no_post_endpoint_phase_b`). No HTTP path exists for an external caller to trigger a write to `public.*` via the research surface.

## 4.3 Proof: no mutation possible

Within the research layer:
- `research_writer` has no `UPDATE` or `DELETE` privilege on `research_ro.*` (revoked explicitly). Append-only by DB enforcement.
- `research_reader` has no write privileges anywhere. Read-only by DB enforcement.
- The `is_research_artifact = TRUE` CHECK on `research_run` is a tripwire: any attempt to repurpose a research row by setting the column false fails CHECK.
- All body columns carry token-strip CHECK constraints. Mutating a body row to insert action tokens requires direct DB access bypassing roles, which would also bypass our application entirely.

## 4.4 Proof: no influence on scoring or ML

- `research_reflection.decision_id` is plain `text`, not a FK. Even if reflection rows accumulate over time, no DB-level join causes them to flow into `recommendation_engine.py` or `shadow_scorer.py`.
- The architectural import test (gate 2) makes the Python-level isolation enforceable at CI time.
- ML modules (`apps/api/src/ml/shadow_scorer.py`, `drift_monitor.py`) do not import `apps/api/src/research/**` (their existing imports are `apps/api/src/ml/*` and `apps/api/src/db/models.py` only). A reverse import from a research module into ML is forbidden by gate 2 in the opposite direction (we add a gate 2.b: ML modules cannot import research modules either).

---

# SECTION 5 — Cost Model (Estimate Only)

Bounds for a future Phase E. No implementation in Phase A or B.

## 5.1 Tokens per run (estimate)

Per single ticker, single research run, one full agent chain (4 analysts + bull + bear + reflection):

| Agent role | Input tokens (avg) | Output tokens (avg) |
|---|---|---|
| fundamentals | 1,500 (financial-statement context) | 600 |
| sentiment | 800 (news headlines) | 400 |
| news | 1,200 (news articles excerpt) | 500 |
| technical | 600 (price/volume features) | 400 |
| bull researcher | 2,000 (analyst outputs concatenated) | 700 |
| bear researcher | 2,000 (same) | 700 |
| reflector | 1,000 (run summary + realized outcomes) | 500 |
| **Total per run** | **~9,100 tokens in** | **~3,800 tokens out** |

These are upper-bound estimates assuming verbose prompts. With prompt-compression (Vibe-Trading 5-tier inspiration), input tokens may shrink to ~5,000.

## 5.2 Cost per run (per provider, current pricing as of 2026-04)

| Provider | Model | $/1M input | $/1M output | Cost per run (estimate) |
|---|---|---|---|---|
| Anthropic | claude-opus-4 | $15.00 | $75.00 | ~$0.42 |
| Anthropic | claude-sonnet-4 | $3.00 | $15.00 | ~$0.085 |
| OpenAI | gpt-4-turbo | $10.00 | $30.00 | ~$0.20 |
| OpenAI | gpt-4o | $2.50 | $10.00 | ~$0.061 |
| Google | gemini-2.5-pro | $1.25 | $5.00 | ~$0.030 |

Cheapest viable: ~$0.03/run on Gemini. Most expensive: ~$0.42/run on Opus-4.

## 5.3 Safe daily ceiling (for Phase E manual-only design)

| Tier | Per-run ceiling | Per-day ceiling (sum) | Per-ticker-per-day ceiling |
|---|---|---|---|
| Conservative (recommended for Phase E start) | $0.50 | $25.00 | $2.00 |
| Moderate (after Phase E proven) | $1.00 | $100.00 | $5.00 |
| Aggressive (Phase G+ only, post-checkpoint-resume) | $2.00 | $500.00 | $20.00 |

At conservative tier on Gemini-pro, $25/day covers ~830 runs/day — far more than any plausible manual-only Phase E load (maybe 10-50 runs/day). At moderate tier on Sonnet-4, $100/day covers ~1,180 runs.

**Fail-closed enforcement (future-phase concern, mentioned for Phase A bounds only):**
- Pre-flight check: estimate `(input_tokens × rate_in) + (max_output × rate_out)` before LLM call. If over per-run ceiling, abort before the call; row written with `status='cost_exceeded'`, `body=NULL`.
- Per-day check: query `SUM(cost_usd) WHERE created_at::date = current_date`. If next run would push over per-day ceiling, abort.
- Per-ticker check: query `SUM(cost_usd) WHERE ticker = ? AND created_at::date = current_date`. Same abort discipline.

## 5.4 Storage cost (negligible for Phase B)

- 1 run ≈ 8 KB per body × 7 agent outputs + debate summary + reflection + 7 checkpoints ≈ 80 KB/run.
- 1,000 runs/day × 30 days = 2.4 GB/month.
- Postgres storage at typical cloud rates (~$0.10/GB/month) ≈ $0.24/month for 30-day retention.
- No retention policy set in Phase B (data is sparse).

---

# SECTION 6 — Final Validation

Explicit confirmation of safety properties, line by line.

## 6.1 No execution leakage
- ✅ `research_writer` role has zero `INSERT/UPDATE/DELETE/TRUNCATE` on any execution table (`candidate_idea`, `paper_run_log`, `paper_decision_log`, `alpha_rule_snapshot`, `factor_snapshot`, `paper_position`, `paper_trade_log`).
- ✅ FK invariant enforced: no `public → research_ro` FK is permitted; CI Alembic FK scan fails any such migration.
- ✅ FastAPI router under `/api/research/*` is GET-only; no POST/PUT/PATCH/DELETE registered.
- ✅ No worker job file exists under `apps/worker/src/jobs/research_*.py` in Phase B.
- ✅ No entry in `apps/worker/src/jobs/registry.py` references research.
- ✅ No entry in `apps/worker/src/scheduler/tick_loop.py` references research.

## 6.2 No ML influence path
- ✅ CI architectural import test forbids `apps/api/src/research/**` from importing `feature_engine`, `recommendation_engine`, `shadow_scorer`, `drift_monitor`, `auto_trader`, `paper_execution`.
- ✅ Symmetric gate forbids ML modules (`apps/api/src/ml/*`) from importing research modules — research outputs cannot enter ML training inputs.
- ✅ `research_reflection.decision_id` is plain text, not a FK. No DB-level join into ML feature tables.
- ✅ `is_research_artifact = TRUE` CHECK tripwire on `research_run` prevents row repurposing.

## 6.3 No scheduler dependency
- ✅ No worker job registered in `apps/worker/src/jobs/registry.py`.
- ✅ No tick loop entry in `apps/worker/src/scheduler/tick_loop.py`.
- ✅ Phase A and Phase B explicitly forbid scheduler entries.
- ✅ Future-phase manual run (Phase E) is a separate approval gate; not in Phase B scope.

## 6.4 No write-back path
- ✅ `research_reflection` rows append-only; no UPDATE privilege on `research_writer`.
- ✅ Reflection text passes through CHECK constraint stripping forbidden tokens.
- ✅ Reflection has no FK into `paper_decision_log` or `candidate_idea` — research-side rollback is independent of execution-side rollback.
- ✅ No code path exists from research outputs into agent-memory-shaping prompts (no agent memory in our system; only Postgres rows).
- ✅ Reflection row contents cannot influence future research runs except via operator-curated prompt-template versions; templates are versioned and hashed.

## 6.5 No autonomy
- ✅ No automation in Phase A or Phase B.
- ✅ Manual-only Phase E is the earliest plausible automation, requires its own approval gate.
- ✅ POST endpoint deferred to Phase E gate.

## 6.6 No filesystem persistence
- ✅ No `~/.tradingagents/`, `~/.vibe-trading/`, `~/.openalice/`, or any home-relative path referenced in `apps/api/src/research/**`.
- ✅ CI filesystem-egress lint scans for `~/.` and `os.path.expanduser` in research code.
- ✅ All persistence is Postgres `research_ro.*`.

## 6.7 No recommendation language
- ✅ DB CHECK constraints on every body column reject forbidden tokens.
- ✅ Server-side render filter repeats the check before serialization.
- ✅ Client-side render guard repeats the check before display.
- ✅ CI source-token grep scans `apps/api/src/research/**` and `apps/web/src/components/research/**` for forbidden tokens at build time.
- ✅ Forbidden iconography list enforced via React snapshot tests.
- ✅ Mandatory `Research note — not execution logic. Generated by an LLM. Not financial advice.` banner on every research-aware UI surface.

## 6.8 No LangGraph / LangChain runtime dependency
- ✅ CI dependency lint scans `pyproject.toml` for `langgraph` and `langchain`; fails build if either appears as a runtime dep.
- ✅ Conceptual DAG is re-implemented with our own async worker primitives (Phase C+ concern; not in Phase B).

## 6.9 Provenance guarantee
- ✅ Every row in `research_ro.*` carries provider/model_id/model_version/prompt_hash/tokens_in/tokens_out/cost_usd/status as NOT NULL columns.
- ✅ `prompt_hash` is computed server-side over the rendered prompt; never accepted from LLM payload.
- ✅ Idempotency unique key on `(symbol, as_of, prompt_bundle_hash, input_snapshot_hash, schema_version)` ensures replays are detectable.

---

# Operator Sign-Off

This Phase A audit is complete. By signing below, the operator confirms:

1. The 10-repo classification is accepted as recorded in Section 1.
2. The token-leakage map in Section 2 captures all known leakage vectors.
3. The dependency exclusions in Section 3 (LangGraph, LangChain, all exchange SDKs, all RL frameworks, all filesystem-memory persistence) are accepted.
4. The data flow validation in Section 4 demonstrates unidirectional, isolated, fail-closed flow.
5. The cost-model bounds in Section 5 are accepted as upper-bound estimates for Phase E budgeting.
6. The final validation in Section 6 is accepted.
7. Phase B (schema-only, GET-only API, feature-flagged UI shell) may proceed once the operator sign-off line below is filled in.

**Operator name:** Kunal Khurana
**Date:** 2026-04-30
**Signature / commit hash:** dfefe99 (Phase B implementation commit)

---

**This document does NOT authorize:**
- Any code, schema, migration, API, or UI change before the signature is filled in.
- Any worker job entry or scheduler registration.
- Any LLM client wiring or prompt template file.
- Any POST endpoint registration.
- Any phase past Phase B.

Each subsequent phase (C, D, E, F, G, H) requires its own audit document and approval gate. None is committed by this Phase A audit.
