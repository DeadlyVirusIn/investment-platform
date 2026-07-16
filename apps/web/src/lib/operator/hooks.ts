// Phase UI1 — TanStack Query hooks for DL2 / OPS1 endpoints.
// Endpoints defined minimally; backend owns the actual routes.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
import { useSession } from "@/v2/state/SessionContext";
import type {
  PaperSummary, CurrentState, EquityPoint, TradeRow,
  DecisionRow, PerformanceAttribution, ShadowSignal, SystemHealth,
  AnomalyEvent, AnomalySummary, AnomalySeverity, AnomalyStatus,
} from "./types";

const KEYS = {
  summary: ["paper", "summary"] as const,
  state: ["paper", "state"] as const,
  equity: (fromDate?: string, toDate?: string) =>
    ["paper", "equity", fromDate ?? "all", toDate ?? "all"] as const,
  trades: (filter?: string) => ["paper", "trades", filter ?? "all"] as const,
  decision: (asOf: string) => ["decision", asOf] as const,
  performance: ["paper", "performance"] as const,
  shadow: ["shadow", "signals"] as const,
  health: ["system", "health"] as const,
};

// ---------------------------------------------------------------
// Phase A/B — canonical stock practice portfolio (single source of
// truth). Backed by GET /paper/canonical/stock, scoped to ONE
// portfolio (settings.CANONICAL_STOCK_PORTFOLIO_ID). NO aggregation.
// All user-facing portfolio surfaces must read THIS, not usePaperSummary
// (aggregate) or the local PaperBook store.
// ---------------------------------------------------------------
export interface CanonicalStockPortfolio {
  portfolio_id: string;
  name: string | null;
  nav: number | null;
  cash: number | null;
  positions_value: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  daily_pnl: number | null;
  // Date daily_pnl is measured against (prior live snapshot). May be >1 day
  // back when snapshots are sparse → daily_pnl is a "since this date" delta,
  // not a same-day mark-to-market. Used to label the headline honestly.
  daily_pnl_prior_snapshot_date?: string | null;
  starting_capital: number | null;
  total_return_pct: number | null;
  open_positions_count: number;
  as_of: string | null;
  freshness: "fresh" | "degraded" | "stale" | "unknown";
  source_snapshot_id: string | null;
  source: "live";
  status: "live" | "no_live_snapshot";
  // Absent while clients and servers are rolling forward. Never infer
  // ownership from positions when this is unavailable.
  book_scope?: "user" | "shared_demo";
}

export function useCanonicalStockPortfolio() {
  const { user, loading } = useSession();
  const authScope = user?.id ?? "anonymous";
  return useQuery<CanonicalStockPortfolio>({
    queryKey: ["paper", "canonical", "stock", authScope],
    queryFn: () => apiGet<CanonicalStockPortfolio>("/paper/canonical/stock"),
    // Don't fetch until the session resolves: firing under the "anonymous"
    // scope while a valid cookie is present would cache the authenticated
    // user's book under the anonymous key (Sol review, 019f6c32).
    enabled: !loading,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

// Canonical drawdown — client-derived peak-to-trough from the SCOPED
// canonical equity curve. The user-facing shell must NOT read
// summary.max_drawdown_pct (all-portfolios aggregate); risk flags
// derive from the same single canonical portfolio as NAV. Mirrors
// TrackRecord's calc. Returns a negative percent (e.g. -1.8) or null.
export function useCanonicalDrawdownPct(): number | null {
  const { data: book } = useCanonicalStockPortfolio();
  const { data: equity } = usePaperEquity(undefined, undefined, book?.portfolio_id);
  const pts = equity ?? [];
  if (pts.length === 0) return null;
  let peak = pts[0].equity;
  let depth = 0;
  for (const p of pts) {
    peak = Math.max(peak, p.equity);
    depth = Math.min(depth, ((p.equity - peak) / peak) * 100);
  }
  return depth;
}

// NOTE: usePaperSummary is the ALL-PORTFOLIOS aggregate (4 active paper
// portfolios + replay). It MUST NOT drive any user-facing portfolio
// total (NAV / return / positions / P&L / drawdown). Use it only for
// non-financial system telemetry (pipeline status, last-run heartbeat)
// or in admin/internal aggregate surfaces. User-facing shells read
// useCanonicalStockPortfolio (single canonical portfolio).
export function usePaperSummary() {
  return useQuery<PaperSummary>({
    queryKey: KEYS.summary,
    queryFn: () => apiGet<PaperSummary>("/paper/summary"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

export function useCurrentState() {
  return useQuery<CurrentState>({
    queryKey: KEYS.state,
    queryFn: () => apiGet<CurrentState>("/paper/state"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

// Phase X — backend recommendation count for the V2 TrustBanner.
// Source of truth for "Arth's published calls"; replaces the old
// localStorage decision count so the banner never reads 0 when the
// engine has live recommendations.
export function useRecommendations() {
  return useQuery<{ recommendations: unknown[] }>({
    queryKey: ["recommendations"],
    queryFn: () => apiGet<{ recommendations: unknown[] }>("/recommendations"),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ---------------------------------------------------------------
// P0 live recommendations (Today / Opportunities / PickPage).
// Source: GET /recommendations (real engine, 983/day). Effective
// action = adjusted_action ?? action (policy may damp Buy->Hold).
// NO static TODAYS_DESK / arthosData literals anywhere downstream.
// ---------------------------------------------------------------
// One engine factor behind a recommendation (already returned by
// GET /recommendations). `direction` is bullish/bearish/neutral and
// `score` is the signed contribution; `narrative` is the raw quant
// string (e.g. "ATR(14)/price = 3.15%") — keep raw narratives to the
// Layer-3 trace, never the beginner default surface.
export interface RecEvidence {
  factor_key: string;
  family: string | null;
  weight: string | null;
  value: string | null;
  threshold: string | null;
  direction: string | null;   // "bullish" | "bearish" | "neutral"
  score: string | null;       // signed numeric string
  narrative: string | null;
}

export interface RecApi {
  id: string;
  asset_id: string;
  symbol: string | null;
  name: string | null;              // human company name; null until Polygon backfill
  sector: string | null;            // coded (e.g. "consumer_disc"); humanize via sectorLabel
  action: string | null;            // original engine action
  adjusted_action: string | null;   // post-policy (null = unchanged)
  confidence: string | null;        // numeric string e.g. "80.000000"
  confidence_label: string | null;  // High/Medium/Low
  composite_score: string | null;
  adjusted_composite_score: string | null;
  thesis: string | null;
  generated_at: string | null;
  stale_data: boolean | null;
  enough_data: boolean | null;
  engine_version: string | null;
  tags: string[] | null;
  evidence: RecEvidence[] | null;
  family_scores: Record<string, string | null> | null;
  policy: unknown;
  policy_adjustments: unknown[] | null;
  // Wave 1A — read-safe publication-preflight projection. Present only when
  // RECOMMENDATION_PREFLIGHT_ENABLED on the API; verdicts here are always
  // READY or READY_WITH_LIMITATIONS (HOLD/BLOCKED never reach this list).
  preflight?: {
    verdict: 'READY' | 'READY_WITH_LIMITATIONS';
    limitations: string[];
    evaluated_at: string | null;
    freshness_summary: string | null;
  } | null;
}

export interface RecDiagnostics {
  total: number;
  buy_threshold: string | null;
  buys: number;
  action_distribution: Record<string, number>;
  near_buy_tight_count: number;
  near_buy_loose_count: number;
  dampers_applied: number;
  stale_count: number;
  insufficient_data_count: number;
  max_composite: string | null;
}

// Effective (post-policy) action — what the engine actually recommends.
export function effectiveAction(r: RecApi): string | null {
  return r.adjusted_action ?? r.action;
}
export function confidenceNum(r: RecApi): number {
  const v = parseFloat(r.confidence ?? "");
  return Number.isFinite(v) ? v : 0;
}

// Latest-per-asset, highest-confidence first. limit high enough to span
// the day's actionable set without paging.
export function useTodaysRecommendations(limit = 500) {
  return useQuery<{ recommendations: RecApi[]; count: number }>({
    queryKey: ["recs", "today", limit],
    queryFn: () =>
      apiGet(`/recommendations?latest=true&sort_by=confidence&order=desc&limit=${limit}`),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useRecommendationDiagnostics() {
  // Endpoint returns { count, diagnostics, summary }; the batch summary
  // (total / buys / action_distribution / buy_threshold) lives in .summary.
  return useQuery<RecDiagnostics>({
    queryKey: ["recs", "diagnostics"],
    queryFn: async () => {
      const d = await apiGet<{ summary: RecDiagnostics }>(
        "/recommendations/diagnostics",
      );
      return d.summary;
    },
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// Per-recommendation evidence (PickPage reasoning).
export function useRecommendationEvidence(recId: string | null) {
  return useQuery<{ evidence: unknown[] }>({
    queryKey: ["recs", "evidence", recId],
    queryFn: () => apiGet(`/recommendations/${recId}/evidence`),
    enabled: !!recId,
    staleTime: 300_000,
  });
}

// Highest-confidence actionable BUY (effective action). null when none.
export function selectTopBuy(recs: RecApi[]): RecApi | null {
  const buys = recs
    .filter((r) => effectiveAction(r) === "Buy")
    .sort((a, b) => confidenceNum(b) - confidenceNum(a));
  return buys[0] ?? null;
}

export function usePaperEquity(
  from?: string, to?: string, portfolioId?: string,
) {
  const qs = new URLSearchParams();
  if (from) qs.set("from", from);
  if (to) qs.set("to", to);
  // Phase A/B — when scoped to the canonical portfolio, the curve is for
  // that ONE portfolio only (no aggregate of test/demo fixtures).
  if (portfolioId) qs.set("portfolio_id", portfolioId);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return useQuery<EquityPoint[]>({
    queryKey: [...KEYS.equity(from, to), portfolioId ?? "all"],
    queryFn: () => apiGet<EquityPoint[]>(`/paper/equity${suffix}`),
    staleTime: 60_000,
  });
}

export function usePaperTrades(filter?: "open" | "closed") {
  const qs = filter ? `?status=${filter}` : "";
  return useQuery<TradeRow[]>({
    queryKey: KEYS.trades(filter),
    queryFn: () => apiGet<TradeRow[]>(`/paper/trades${qs}`),
    staleTime: 30_000,
  });
}

// Phase 11Z — executed paper trades (account/recommendation path).
// Distinct from usePaperTrades which reads paper_trade_log (selector
// path). After the 2026-05-02 wipe + execution-chain replay,
// paper_trade=18 but paper_trade_log=0; PortfolioTerminal must use
// these hooks to show executed activity.
export interface ExecutedSummary {
  include_replay: boolean;
  trades_total: number;
  trades_buy: number;
  trades_sell: number;
  open_positions: number;
  distinct_symbols: number;
  portfolios_with_activity: number;
  first_fill_date: string | null;
  last_fill_date: string | null;
  has_replay_recovered_rows: boolean;
  // Always-on split counts independent of include_replay.
  live_trades_count: number;
  replay_trades_count: number;
  live_open_positions_count: number;
  replay_open_positions_count: number;
}

export interface ExecutedTrade {
  trade_id: string;
  portfolio_id: string;
  portfolio_name: string;
  symbol: string;
  side: "buy" | "sell";
  quantity: number | null;
  fill_price: number | null;
  notional_usd: number | null;
  fill_ts: string | null;
  realized_pnl: number | null;
  reason: string | null;
  source: "live" | "dev" | "replay" | "test";
  replay_run_id: string | null;
}

export interface ExecutedPosition {
  position_id: string;
  portfolio_id: string;
  portfolio_name: string;
  symbol: string;
  quantity: number | null;
  avg_cost: number | null;
  is_open: boolean;
  opened_at: string | null;
  closed_at: string | null;
  source: "live" | "dev" | "replay" | "test";
  replay_run_id: string | null;
  // Attribution enrichment (display-only; null when no price available).
  current_price?: number | null;
  previous_close?: number | null;
  market_value?: number | null;
  cost_basis?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  day_pnl?: number | null;
  day_pnl_pct?: number | null;
  total_return_pct?: number | null;
}

export function useExecutedSummary(includeReplay = false) {
  const qs = includeReplay ? "?include_replay=true" : "";
  return useQuery<ExecutedSummary>({
    queryKey: ["paper", "executed", "summary", includeReplay],
    queryFn: () => apiGet<ExecutedSummary>(`/paper/executed/summary${qs}`),
    staleTime: 30_000,
  });
}

// `opts.enabled` defaults to true so existing GLOBAL callers (operator /
// admin dashboards that intentionally omit portfolioId) are unchanged.
// Per-user/investor surfaces MUST pass `{ enabled: !!portfolioId }` so the
// hook does NOT fire an unscoped (all-portfolios) request while the canonical
// portfolio id is still resolving — otherwise it would briefly render global
// aggregates. See INVESTOR_DUE_DILIGENCE_AUDIT P0-1.
export function useExecutedTrades(
  includeReplay = false, portfolioId?: string | null,
  opts?: { enabled?: boolean },
) {
  const params = new URLSearchParams();
  if (includeReplay) params.set("include_replay", "true");
  if (portfolioId) params.set("portfolio_id", portfolioId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery<{ count: number; trades: ExecutedTrade[]; include_replay: boolean }>({
    queryKey: ["paper", "executed", "trades", includeReplay, portfolioId ?? null],
    queryFn: () => apiGet(`/paper/executed/trades${qs}`),
    staleTime: 30_000,
    enabled: opts?.enabled ?? true,
  });
}

export function useExecutedPositions(
  includeReplay = false, isOpen?: boolean,
  portfolioId?: string | null,
  opts?: { enabled?: boolean },
) {
  const { user } = useSession();
  const authScope = user?.id ?? "anonymous";
  const params = new URLSearchParams();
  if (includeReplay) params.set("include_replay", "true");
  if (isOpen !== undefined) params.set("is_open", String(isOpen));
  if (portfolioId) params.set("portfolio_id", portfolioId);
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery<{ count: number; positions: ExecutedPosition[]; include_replay: boolean }>({
    queryKey: ["paper", "executed", "positions", includeReplay, isOpen, portfolioId ?? null, authScope],
    queryFn: () => apiGet(`/paper/executed/positions${qs}`),
    staleTime: 30_000,
    enabled: opts?.enabled ?? true,
  });
}

// Closed paper positions joined to the recommendation that opened them —
// substrate for the Reflection Loop (expected vs happened). Real stored
// data only; no fabricated commentary. (GET /paper/closed-recommendations)
export interface ClosedRecommendation {
  rec_id: string;
  symbol: string;
  name: string | null;
  action: string | null;
  confidence: number | null;
  opened_at: string | null;
  closed_at: string | null;
  hold_days: number | null;
  realized_pnl: number | null;
  exit_reason: string | null;
}

export function useClosedRecommendations(portfolioId?: string | null) {
  const qs = portfolioId ? `?portfolio_id=${encodeURIComponent(portfolioId)}` : "";
  return useQuery<{ count: number; items: ClosedRecommendation[] }>({
    queryKey: ["paper", "closed-recommendations", portfolioId ?? null],
    queryFn: () => apiGet(`/paper/closed-recommendations${qs}`),
    enabled: !!portfolioId,
    staleTime: 60_000,
  });
}

export function useDecision(asOfDate: string | null) {
  return useQuery<DecisionRow>({
    queryKey: KEYS.decision(asOfDate ?? ""),
    queryFn: () => apiGet<DecisionRow>(`/decision-log/${asOfDate}`),
    enabled: !!asOfDate,
    staleTime: 300_000,
  });
}

export function usePerformance() {
  return useQuery<PerformanceAttribution>({
    queryKey: KEYS.performance,
    queryFn: () => apiGet<PerformanceAttribution>("/paper/performance"),
    staleTime: 120_000,
  });
}

export function useShadowSignals() {
  return useQuery<ShadowSignal[]>({
    queryKey: KEYS.shadow,
    queryFn: () => apiGet<ShadowSignal[]>("/shadow/signals"),
    staleTime: 60_000,
  });
}

export function useAnomalies(
  status: AnomalyStatus = "open",
  severity?: AnomalySeverity,
) {
  const qs = new URLSearchParams({ status });
  if (severity) qs.set("severity", severity);
  return useQuery<AnomalyEvent[]>({
    queryKey: ["anomalies", status, severity ?? "all"],
    queryFn: () => apiGet<AnomalyEvent[]>(`/anomalies?${qs.toString()}`),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

export function useAnomalySummary() {
  return useQuery<AnomalySummary>({
    queryKey: ["anomalies", "summary"],
    queryFn: () => apiGet<AnomalySummary>("/anomalies/summary"),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ---------------------------------------------------------------
// Phase C — Risk Dashboard (read-only).
// ---------------------------------------------------------------

export interface ConcentrationSymbolRow {
  symbol: string;
  n_open: number;
  total_qty: number | null;
  notional_usd: number | null;
  unrealized_pnl: number | null;
  mark_unavailable: boolean;
}

export interface ConcentrationPortfolioRow {
  portfolio_id: string;
  portfolio_name: string;
  n_open: number;
  notional_usd: number | null;
}

export interface RiskPortfolio {
  portfolio_id: string;
  portfolio_name: string;
  snapshot_date: string;
  nav: number | null;
  cash: number | null;
  positions_value: number | null;
  unrealized_pnl: number | null;
  realized_pnl_cumulative: number | null;
}

export interface RiskDashboardResponse {
  notice: string;
  include_replay: boolean;
  snapshot_date: string | null;
  mark_unavailable: boolean;
  nav: number | null;
  cash: number | null;
  exposure_value: number | null;
  exposure_pct: number | null;
  open_positions_count: number;
  unrealized_pnl: number | null;
  realized_pnl_total: number | null;
  max_drawdown_pct: number | null;
  pending_next_bar_count: number;
  pending_next_bar_note: string | null;
  live_trades_count: number;
  replay_trades_count: number;
  concentration_by_symbol: ConcentrationSymbolRow[];
  concentration_by_portfolio: ConcentrationPortfolioRow[];
  top_5_notional: ConcentrationSymbolRow[];
  portfolios: RiskPortfolio[];
}

export function useRiskDashboard(includeReplay = false) {
  const qs = includeReplay ? "?include_replay=true" : "";
  return useQuery<RiskDashboardResponse>({
    queryKey: ["risk-dashboard", includeReplay],
    queryFn: () => apiGet<RiskDashboardResponse>(
      `/performance/paper/risk-dashboard${qs}`,
    ),
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });
}


export function useSystemHealth() {
  return useQuery<SystemHealth>({
    queryKey: KEYS.health,
    queryFn: () => apiGet<SystemHealth>("/system/health"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
