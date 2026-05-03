// Phase UI1 — TanStack Query hooks for DL2 / OPS1 endpoints.
// Endpoints defined minimally; backend owns the actual routes.

import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api";
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

export function usePaperEquity(from?: string, to?: string) {
  const qs = new URLSearchParams();
  if (from) qs.set("from", from);
  if (to) qs.set("to", to);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return useQuery<EquityPoint[]>({
    queryKey: KEYS.equity(from, to),
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
}

export function useExecutedSummary(includeReplay = false) {
  const qs = includeReplay ? "?include_replay=true" : "";
  return useQuery<ExecutedSummary>({
    queryKey: ["paper", "executed", "summary", includeReplay],
    queryFn: () => apiGet<ExecutedSummary>(`/paper/executed/summary${qs}`),
    staleTime: 30_000,
  });
}

export function useExecutedTrades(includeReplay = false) {
  const qs = includeReplay ? "?include_replay=true" : "";
  return useQuery<{ count: number; trades: ExecutedTrade[]; include_replay: boolean }>({
    queryKey: ["paper", "executed", "trades", includeReplay],
    queryFn: () => apiGet(`/paper/executed/trades${qs}`),
    staleTime: 30_000,
  });
}

export function useExecutedPositions(
  includeReplay = false, isOpen?: boolean,
) {
  const params = new URLSearchParams();
  if (includeReplay) params.set("include_replay", "true");
  if (isOpen !== undefined) params.set("is_open", String(isOpen));
  const qs = params.toString() ? `?${params.toString()}` : "";
  return useQuery<{ count: number; positions: ExecutedPosition[]; include_replay: boolean }>({
    queryKey: ["paper", "executed", "positions", includeReplay, isOpen],
    queryFn: () => apiGet(`/paper/executed/positions${qs}`),
    staleTime: 30_000,
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

export function useSystemHealth() {
  return useQuery<SystemHealth>({
    queryKey: KEYS.health,
    queryFn: () => apiGet<SystemHealth>("/system/health"),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
