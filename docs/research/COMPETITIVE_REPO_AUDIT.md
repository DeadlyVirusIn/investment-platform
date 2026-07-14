# Competitive Repo Audit — Investor Readiness

**Date:** 2026-06-19 · **Method:** shallow read of READMEs, LICENSE files, docs, and key source. No code copied. Licenses verified from LICENSE files, not badges. Patterns/ideas only.

ArthOS positioning for scoring: beginner-first, trust/transparency AI **investing education** platform. Surfaces = Discover / Learn / Practice / Build / Invest / Automate(future). **Paper-only**, no live trading or brokerage. Honest-data discipline. Per-user proof/track record. Agentic "see the working" layer. Stack: FastAPI + Postgres + React/Vite.

## Scoreboard

| Repo | License | Fit /10 | Priority | One-line leverage |
|---|---|---|---|---|
| FinRobot | Apache-2.0 | 8 | Now | Structured research-report "see the working" engine |
| TradingAgents | Apache-2.0 | 8 | Now | Distilled bull/bear debate + outcome-reflection loop |
| Vibe-Trading | MIT | 8 | Now | `run_card`/`/trace` explainability + Shadow Account behavior diagnostics (same stack) |
| freqtrade | GPL-3.0 | 8 | Now (patterns only) | Single-codepath paper/live parity + standardized backtest report |
| QuantDinger | Apache-2.0 (backend) | 7 | Now | Dual-gate paper-only token + immutable audit log (safety backbone) |
| nofx | AGPL-3.0 | 6 | Later | kernel→agent→runtime skeleton + model decision log |
| tensortrade | Apache-2.0 | 5 | Later | DataFeed/Stream lazy pipeline + explicit-cost simulated exchange |
| AI-Trader | MIT | 5 | Later | Leaderboard/challenge paper engine + skills-as-capabilities |
| awesome-machine-learning | CC0 / NOASSERTION | 4 | Skip-as-build / Later-as-index | Discovery index + Learn-content seed |
| OpenAlice | AGPL-3.0 | 4 | Later (metaphor only) | Trading-as-Git audit metaphor; AGPL → no code reuse |

**License flags:** GPL-3.0 (freqtrade) and AGPL-3.0 (nofx, OpenAlice) are copyleft — **never copy their code** into ArthOS; ideas/patterns only. QuantDinger's **frontend** is source-available/commercial-restricted (backend is Apache-2.0). awesome-ML is a CC0-style dedication but every linked library carries its own license — check each before adopting.

---

## 1. FinRobot — AI4Finance-Foundation

**What it does.** LLM-powered "financial AI agents" for research-grade analysis: forecasting, filing/annual-report analysis, equity-research report generation, strategy ideation. Positions as a full agent *platform* (same org as FinRL/FinGPT → academic credibility).

**Architecture.** Four layers: AI-agents (Financial Chain-of-Thought) → financial LLM algorithms → LLMOps/DataOps routing + multi-source ingestion → plug-and-play foundation models. Each agent runs Perception→Brain→Action; a Smart Scheduler routes tasks to specialized agents. Code: `agents`, `data_source`, `functional` (analyzer/charting/coding/quant/reporting/text).

**License.** Apache-2.0 (verified). Commercial use allowed with attribution + NOTICE.

**Best ideas to borrow.** (1) **Equity-research report generator** — structured, chart-rich, sectioned (thesis → financials → valuation → peers → risks) is the single most investor-impressive demo here and maps almost directly onto Discover "see the working." (2) **Multi-source data abstraction** (`data_source` interface) reinforcing honest-data discipline. (3) Agent-per-task registry/scheduler for future Automate. (4) Financial Chain-of-Thought as a beginner-legible reasoning scaffold.

**Avoid.** The full four-layer/smart-scheduler abstraction (over-engineered, would bloat FastAPI); trade-execution/strategy-ideation agents (push toward active trading); its domain-tuned model assumptions.

**Risks.** Low-moderate — research, not signals; aligned with beginner-first. Watch: report content reading as advice (mitigate with disclaimer discipline); token cost if copied naively.

**Fit 8/10.** Best architectural + demo fit. **Priority: Now** (report pattern for Discover/Learn).

---

## 2. TradingAgents — Tauric Research

**What it does.** Multi-agent LLM framework simulating a trading *firm*: analyst agents gather data, bull/bear researchers debate, a trader proposes, risk/portfolio managers approve. Research-framed (arXiv 2412.20138), paper/simulated by default. Debate transcript is human-legible → high "wow."

**Architecture.** LangGraph. 9 roles: 4 analysts (fundamentals/sentiment/news/technical, run concurrently with tool nodes), 2 bull/bear researchers debating across `max_debate_rounds` with a judge, a Trader, a risk debate (aggressive/conservative/neutral), a Portfolio Manager. `TradingMemoryLog` persists decisions, later **retroactively fetches realized returns and writes reflections** injected into future same-ticker runs. `SignalProcessor` extracts the final call.

**License.** Apache-2.0 (verified from LICENSE — README omits it; badge-only check would have been wrong).

**Best ideas to borrow.** (1) **Bull/bear debate as the explanation UI** — a condensed two-sided case per Discover idea; safety-positive (shows downside, not just the pitch) and the most beginner-trust-building pattern across all 10 repos. (2) **Reflection-memory loop** — record decision → later fetch real return → write a short natural-language post-mortem → feed forward. ArthOS's existing attribution schema (`opened_by_recommendation_id`, `realized_pnl` — MP1A/MP1S) is the exact data substrate. (3) Risk debate as a lightweight "how risky is this?" explainer. (4) LangGraph as a reference for staged, checkpointable Automate workflows.

**Avoid.** Running the full 9-agent multi-round debate per idea in production (cost/latency incompatible with a daily feed → distill into a single-pass "show both sides" prompt); surfacing the trader/position-sizing agent to beginners; presenting alpha-vs-SPY as a headline metric.

**Risks.** Moderate — "trading firm" vocabulary (position sizing, alpha, timing) skews quant; reskin as education ("how analysts argue both sides"), not "our firm's trade call."

**Fit 8/10.** Best *idea* fit; plugs into existing attribution work. **Priority: Now** (distilled debate + reflection post-mortems).

---

## 3. Vibe-Trading — HKUDS

**What it does.** NL research workspace turning finance questions into analysis, backtests, simulations across many markets. From HKUDS (credible lab, ~12.7k stars, actively shipping). **Near-identical stack to ArthOS** (Python 3.11/FastAPI + React 19/TS/Vite).

**Architecture.** LLM orchestrator with persistent memory + tool registry; 36 MCP tools; 13 LLM providers; 29 preset multi-agent "swarm" teams with a DAG that blocks downstream on upstream failure and streams per-worker status in the chat timeline; 18 data loaders with fallback chains; 77 finance skills; 452-factor "Alpha Zoo" with IC/IR ranking. Every run emits `run_card.json/.md` + per-run `llm_usage.json`; `/trace <run_id>` replays the full decision sequence. Validation: Monte Carlo, Bootstrap CI, walk-forward, lookahead-banned at operator layer, AST purity gate. Novel **Shadow Account** behavior-diagnostics feature.

**License.** MIT — patterns freely borrowable.

**Best ideas to borrow.** (1) **`/trace <run_id>` replay + per-run `run_card`** — a near-perfect template for ArthOS's "see the working": a structured, inspectable record per recommendation. (2) Per-run `llm_usage.json` cost auditing (honest-data pattern). (3) **Shadow Account** (strongest borrow) — parse a user's paper trade journal, profile behavior (holding days, win rate, disposition effect, overtrading/anchoring), surface "rule breaks, early exits, missed signals." Maps directly onto Practice + Learn as a per-user, honest, educational feedback loop with zero live risk. (4) Swarm DAG with streaming per-agent status as a live "AI committee" UX in Discover. (5) Pre-flight validation returning actionable JSON errors.

**Avoid.** Live/bounded broker connectors, options/futures/on-chain skills, the 452-factor Alpha Zoo (too quant; day-trade vibe). Don't import the breadth.

**Risks.** Low if scoped to research/education/explainability/behavior-diagnostics. Keep factor-zoo/multi-market vocabulary off ArthOS surfaces.

**Fit 8/10.** Highest stack alignment + MIT + two directly transplantable patterns. **Priority: Now** (trace/run-card + Shadow Account; defer quant).

---

## 4. freqtrade

**What it does.** Mature OSS crypto trading bot — the most polished reference for the full "strategy → backtest → optimize → dry-run → live" loop. README is explicitly educational ("dry-run first; never risk what you can't lose").

**Architecture.** Declarative strategy class (`populate_indicators`/`populate_entry_trend`/`populate_exit_trend`). Subsystems: vectorized/event-hybrid **backtest** (fees/slippage/order types), **Hyperopt** (parameter search w/ custom loss), **dry-run** (paper sharing the *exact same execution codepath* as live via one config flag), **FreqAI** (rolling-retrain ML), SQLAlchemy persistence, Telegram + FreqUI + Plotly reporting.

**License.** GPL-3.0 — copyleft. **Do not copy code.** Patterns only.

**Best ideas to borrow.** (1) **Single-codepath paper/live parity** (the most valuable idea) — architect execution so one engine handles both modes via a flag, so the track record was generated by the *real* engine, not a separate simulator. Core of credible "honest track record." (2) **Standardized backtest report object** — one canonical metrics struct (win-rate, expectancy, max drawdown, profit factor, Sharpe, avg hold, per-trade ledger) computed identically everywhere → prevents inconsistent/fake metrics. (3) Walk-forward / out-of-sample discipline (from Hyperopt) to back any "this works" claim. (4) Candle + entry/exit markers + cumulative-equity plot as a "see the working" visualization.

**Avoid.** Live-execution/exchange-order layer, Telegram trade commands, leverage/futures/shorting, and **Hyperopt-as-a-user-feature** (handing beginners a parameter-optimizer is an overfitting + gambling trap). Keep optimization internal and invisible.

**Risks.** Reputational (borrowed vocabulary reads as "trading bot"); regulatory (its live/automation features are exactly what triggers brokerage/advisory scrutiny — stay paper-only); legal (GPL).

**Fit 8/10.** Best template for paper-validation rigor despite zero code reuse + wrong asset class. **Priority: Now** (report + parity patterns).

---

## 5. QuantDinger — brokermr810

**What it does.** Self-hosted quant infra unifying multi-LLM research, Python strategy authoring, server-side backtesting, and multi-broker execution. ~8.3k stars, mature (v4.0.1).

**Architecture.** Python/Docker Compose; Vue + Flask/Gunicorn + Postgres 16 + Redis 7. "Agent-native": Agent Gateway (`/api/agent/v1`) + published `quantdinger-mcp` MCP server. Multi-LLM ensemble. Two strategy runtimes (IndicatorStrategy dataframe / ScriptStrategy event `on_bar`). Multi-user OAuth + RBAC + billing; GHCR images; AWS Marketplace AMI.

**License.** Backend **Apache-2.0** (patent grant — good). **Frontend (QuantDinger-Vue) is source-available, commercial-authorization required** — do NOT reuse frontend commercially.

**Best ideas to borrow.** (1) **Dual-gate paper-only token model + immutable agent audit log** (single most actionable safety pattern across all 10 repos) — agent tokens are paper-only unless *both* `paper_only=false` on the token *and* a server-side `LIVE_TRADING_ENABLED=true`; every agent call appended to an immutable audit log. Makes "we cannot accidentally trade real money" a **structural property, not a promise** — a real diligence asset. (2) **Server-side backtest computation** (equity/drawdown/trade-log/snapshot) — results computed + stored, not faked client-side. (3) "AI drafts scaffold, Python is source of truth." (4) Agent Gateway + MCP as a clean automation boundary.

**Avoid.** Frontend code (license), live multi-broker/CCXT adapters, the pro-quant dual-runtime strategy surface (over-engineered for beginners — borrow the *gating*, not the authoring UI).

**Risks.** Moderate — pro-quant framing risks a day-trade vibe; but the paper-only-by-default architecture is precisely the *de-risking* backbone ArthOS wants.

**Fit 7/10.** Apache-2.0 backend + Python/Postgres alignment + strongest paper-safety architecture. **Priority: Now** (adopt dual-gate + audit log as safety backbone).

---

## 6. nofx — NoFxAiOS

**What it does.** OSS "AI trading terminal" where AI models **execute live trades** across stocks/commodities/forex/crypto and nine exchanges. ~12.4k stars; Go backend + React/TradingView frontend.

**Architecture.** `kernel` (orchestration loop) → `agent` (AI decision/skills) → `trader` (model output → orders), plus `manager`, "Strategy Studio," single `provider` (Claw402) so users skip key mgmt, `mcp` tool use, `market`, exchange/wallet, `telegram` control. Persisted **model decision log** in the dashboard. "Competition mode" leaderboard of model-driven traders.

**License.** AGPL-3.0 — network copyleft. **No code reuse.**

**Best ideas to borrow.** (1) **kernel→agent→runtime split** as the skeleton for ArthOS "Automate." (2) The persisted **model decision log** as a first-class user-visible artifact (matches ArthOS's "see the working" instinct). (3) MCP as the agent↔tools contract. (4) Read-only competition/leaderboard reframed as **honest per-user paper track-record comparison**.

**Avoid.** All live-execution/exchange code, leverage/derivatives, referral-link monetization, and any AGPL code.

**Risks.** License (AGPL contamination); reputational/regulatory (trading-automation/gambling-adjacent; borrowing its vocabulary/surfaces undercuts beginner-safe positioning).

**Fit 6/10.** High architectural relevance for Automate; low values fit. **Priority: Later** (mine orchestration + decision-log patterns when Automate is scoped). Borrow the skeleton, reject the body.

---

## 7. tensortrade

**What it does.** Research framework for building/training **RL** trading agents — a Gym-style sandbox, not a product.

**Architecture.** Composable: `TradingEnv`, `ActionScheme` (BSH), `RewardScheme` (PBR), `Observer` (windowed features), `Portfolio`/`Wallets`, `Exchange` (simulated, configurable commission/slippage), `DataFeed` (lazy, named **Streams**). Ray RLlib + Optuna.

**License.** Apache-2.0 — permissive.

**Best ideas to borrow.** (1) **DataFeed/Stream lazy pipeline** — composable, named, lazily-evaluated, inspectable feature pipeline; maps onto "see the working" + a clean FastAPI data layer. (2) Pluggable Reward/Action separation = clean strategy-eval architecture. (3) **Simulated exchange with explicit commission/slippage** — a transparent fill model is exactly what a credible paper portfolio needs; their honesty that costs kill profitability is a *teaching moment* for Learn. (4) Portfolio/Wallet accounting model.

**Avoid.** The entire RL agent/training stack (RLlib, reward-shaping, policy training) — an opaque "AI that beats the market" is the opposite of the transparency promise and a gambling-adjacent overpromise. Skip Optuna-as-product.

**Risks.** RL framing invites unrealistic expectations ("robot beats the market"); opaque models conflict with honest-data discipline.

**Fit 5/10.** Beautiful architecture + permissive license, but RL core is off-strategy. **Priority: Later** (steal DataFeed/Stream + cost model; skip RL).

---

## 8. AI-Trader — HKUDS

**What it does.** "Agent-native" platform where autonomous agents publish signals, debate, and **copy-trade/sync real trades across live brokers** (Binance/Coinbase/IBKR) + forex + prediction markets. Includes a $100K paper mode, but live execution is first-class. **Closest stack match** (FastAPI + React + OpenAPI).

**Architecture.** `skills` (`ai4trade`/`copytrade`/`tradesync`), `service`, `research`. Agents register via an integration guide, consume data, publish signals, execute. Copy-trade engine: fractional sizing, slippage, async exec. Experiment/Challenge system with leaderboards + monthly auto-settlement.

**License.** MIT — most permissive.

**Best ideas to borrow.** (1) **Skills-as-capabilities module pattern** (each capability a self-contained, OpenAPI-described skill) for future Build/Automate. (2) **Leaderboard / challenge / auto-settlement engine** — strong, safe, gamified fit for Practice: per-user paper portfolios on an honest mark-to-market board with monthly settlement; reinforces per-user proof *without* live risk. (3) Copy-trade *risk-parameter* layer (capital caps, asset filters, fractional sizing) → reusable as paper portfolio constraints / risk-education sliders, stripped of execution. (4) FastAPI+React+OpenAPI conventions.

**Avoid.** Everything execution: `tradesync`, live brokers, real copy-trading, forex, prediction markets — the exact features ArthOS rejects; importing them inverts positioning + creates regulatory exposure.

**Risks.** High for reuse, low for pattern-borrowing. Any visible association with "fully-automated live trading" damages beginner-safe reputation.

**Fit 5/10.** Best stack/structure match, worst mission match. **Priority: Later** for leaderboard/skills; **Skip** all execution.

---

## 9. awesome-machine-learning — josephmisiti

**What it does.** ~73k-star curated link list of ML frameworks/libraries/resources. Documentation, not software.

**Architecture.** Two-level taxonomy: primary axis = language, secondary = domain (General ML, NLP, CV, DL, Data Analysis/Visualization, Speech, RL), plus Tools and Further Resources (books/courses/MOOCs).

**License.** CC0-style dedication; GitHub reports `NOASSERTION`/"Other". The *list* is reusable; each linked library has its own license — check individually.

**Best ideas to borrow.** Use as a *sourcing index*, not a design input: (1) Python Data Analysis/Visualization libs for ingestion/feature pipelines; (2) the few model-monitoring/calibration/fairness tools (Phoenix, MCGrad) as references for an honest-data "is the model calibrated / drifting" layer; (3) courses/books as raw material for the **Learn** academy curriculum.

**Avoid.** Treating it as an authority on finance ML or evaluation (those sections barely exist); republishing the list; assuming any linked lib is production/compliance-ready.

**Risks.** Very low — mainly link rot + accidental adoption of a copyleft transitive dependency.

**Fit 4/10.** **Priority: Skip** as a build input; keep as a reference bookmark + Learn-content quarry.

---

## 10. OpenAlice — TraderAlice

**What it does.** Autonomous AI trading *agent* running the full **live** lifecycle 24/7 across equities/crypto/commodities/forex/macro, with explicit user approval per execution. ~5.4k stars.

**Architecture.** TS-heavy + Python; Node 22, Turborepo. Alice Process (agent runtime) + UTA Service (broker carrier, "Trading-as-Git" state machine) + Workspace (real dir + git repo + persistent terminal running agent CLIs via MCP). **Trading-as-Git**: stage orders → commit w/ message → push to execute; each push runs guards, dispatches to broker, snapshots state, records an 8-char hash. Guard pipeline (max position, cooldown, whitelist) "like linting." Cron jobs spawn headless workspaces reporting via an Inbox.

**License.** AGPL-3.0 — network copyleft. **Code effectively off-limits for closed SaaS.**

**Best ideas to borrow (concept only).** (1) **Trading-as-Git audit metaphor** — model every ArthOS paper action as a "commit" with a human-readable message + immutable hash → reviewable, honest Practice history. (2) **Guard-pipeline-as-linting** framing for a beginner-safety rail layer. (3) **Inbox** pattern for surfacing scheduled-agent output.

**Avoid.** Any code (AGPL); the entire live-execution/autonomous-24-7/broker-carrier architecture; the "headless terminal running a coding CLI to place trades" model.

**Risks.** Highest of the set — autonomous live trading with real funds is exactly the gambling/day-trade profile ArthOS must avoid; AGPL is a legal trap. Borrow vocabulary/metaphors only.

**Fit 4/10.** Two transferable concepts, but no paper/backtest mode, AGPL code, wrong stack, autonomous-live ethos. **Priority: Later** (mine the Git-audit metaphor for Practice history; otherwise skip).

---

## Cross-repo conclusion

The defensible, beginner-safe core to pursue **now**: (a) **explainability** — FinRobot's research-report engine + TradingAgents' distilled bull/bear debate + Vibe-Trading's `run_card`/`trace` per-recommendation record; (b) **honest proof** — freqtrade's single-codepath paper/live parity + standardized metrics object, feeding TradingAgents' outcome-reflection loop on top of ArthOS's existing MP1A/MP1S attribution; (c) **safety moat** — QuantDinger's dual-gate paper-only token + immutable audit log, making "cannot trade real money" structural. Quarantine all live-execution, copy-trade, leverage, forex, and prediction-market surfaces (AI-Trader, nofx, OpenAlice) — borrow their orchestration *skeletons* and audit *metaphors* only, never their bodies, and never copyleft (GPL/AGPL) code.
