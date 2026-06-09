// Phase G1 — options portfolio intelligence hook. Read-only aggregate of
// open options paper positions (GET /api/options/portfolio). No mutation.

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';

export interface OptionsPortfolioPosition {
  trade_id: number;
  underlying: string;
  strategy: string;
  capital_at_risk: number;
  max_profit: number;
  net_delta: number | null;
  net_theta: number | null;
  net_vega: number | null;
  dte: number | null;
}

export interface OptionsConcentration {
  underlying: string;
  capital_at_risk: number;
  pct: number;       // 0..1
  high: boolean;     // > 40%
}

export interface OptionsPortfolio {
  status: 'live' | 'empty';
  open_count: number;
  capital_at_risk: number;
  max_profit: number;
  net_delta: number | null;
  net_theta: number | null;
  net_vega: number | null;
  greeks_source: 'current' | 'entry' | 'mixed' | null;
  greeks_as_of: string | null;
  concentration: OptionsConcentration[];
  positions: OptionsPortfolioPosition[];
}

export function useOptionsPortfolio() {
  return useQuery<OptionsPortfolio>({
    queryKey: ['options', 'portfolio'],
    queryFn: () => apiGet<OptionsPortfolio>('/options/portfolio'),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ── Phase H1 — lifecycle advisory (read-only) ──────────────────────────────

export interface AdvisorySignal { level: string; reason: string }

export interface AdvisoryPosition {
  trade_id: number;
  underlying: string;
  strategy: string;
  dte: number | null;
  pct_max_profit: number | null;
  profit_so_far: number | null;
  take_profit: AdvisorySignal | null;
  dte_management: AdvisorySignal | null;
  loss_risk: AdvisorySignal | null;
  assignment_risk: { level: string; reason: string } | null;
  potential_roll_preview: {
    to_expiry: string; short_strike: number; short_mid: number | null; note: string;
  } | null;
  value_source: 'mtm_event' | 'chain' | 'mixed' | null;
  value_as_of: string | null;
}

export interface OptionsAdvisory {
  status: 'live' | 'empty';
  open_count: number;
  positions: AdvisoryPosition[];
}

export function useOptionsAdvisory() {
  return useQuery<OptionsAdvisory>({
    queryKey: ['options', 'portfolio', 'advisory'],
    queryFn: () => apiGet<OptionsAdvisory>('/options/portfolio/advisory'),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ── Phase G2 — portfolio detail (read-only explainability) ──────────────────

export interface OptionsLeg {
  side: 'BUY' | 'SELL';
  option_symbol: string;
  strike: number | null;
  expiry: string | null;
  option_type: string | null;
  qty: number;
  entry_fill_price: number | null;
  bid: number | null;
  ask: number | null;
  mid: number | null;
  open_interest: number | null;
  spread: number | null;
  quote_age_seconds: number | null;
  leg_pnl: number | null;
}

export interface OptionsSetup {
  summary: string;
  max_profit: string;
  max_loss: string;
  profit_when: string;
  risk_when: string;
}

export interface OptionsLifecycle {
  action: string;
  reason: string;
  tp_threshold_pct: number;
  dte_management_days: number;
}

export interface OptionsDetailPosition {
  trade_id: number;
  underlying: string;
  strategy: string;
  status: string;
  opened_at: string | null;
  dte: number | null;
  entry_credit: number | null;
  max_profit: number | null;
  max_loss: number | null;
  reserved_capital: number | null;
  current_cost_to_close: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  captured_pct: number | null;
  priced: boolean;
  lifecycle: OptionsLifecycle;
  setup: OptionsSetup | null;
  legs: OptionsLeg[];
}

export interface OptionsPortfolioSummary {
  cash: number | null;
  reserved_capital: number;
  open_positions: number;
  capital_at_risk: number;
  max_profit: number;
  unrealized_pnl: number;
  realized_pnl: number | null;
  buying_power: number | null;
}

export interface OptionsPortfolioDetail {
  status: 'live' | 'empty';
  portfolio: OptionsPortfolioSummary;
  positions: OptionsDetailPosition[];
}

export function useOptionsPortfolioDetail() {
  return useQuery<OptionsPortfolioDetail>({
    queryKey: ['options', 'portfolio', 'detail'],
    queryFn: () => apiGet<OptionsPortfolioDetail>('/options/portfolio/detail'),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ── Options Trade History (Phase 1) — read-only ────────────────────────────
// Every options paper trade (open + closed), newest first. Additive over the
// existing /options/paper-trades envelope ({ notice, count, trades }).

export interface OptionsTradeHistoryItem {
  id: number;
  status: string;
  underlying: string;
  strategy_name: string;
  strategy_version: string | null;
  opened_at: string | null;
  closed_at: string | null;
  entry_credit_dollars: number | null;
  exit_debit_dollars: number | null;
  realized_pnl_dollars: number | null;
  release_reason: string | null;
  position_id: string | null;
  released_at: string | null;
  proposal_hash: string | null;
}

interface OptionsTradeHistoryResponse {
  notice: string;
  count: number;
  trades: OptionsTradeHistoryItem[];
}

export function useOptionsTradeHistory(opts?: {
  status?: string; strategy?: string; underlying?: string;
}) {
  const status = opts?.status;
  const strategy = opts?.strategy;
  const underlying = opts?.underlying;
  return useQuery<OptionsTradeHistoryResponse>({
    queryKey: ['options', 'paper-trades', status ?? null, strategy ?? null, underlying ?? null],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (status) qs.set('status', status);
      if (strategy) qs.set('strategy', strategy);
      if (underlying) qs.set('underlying', underlying);
      const suffix = qs.toString() ? `?${qs.toString()}` : '';
      return apiGet<OptionsTradeHistoryResponse>(`/options/paper-trades${suffix}`);
    },
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ── Closed-trade analytics (Phase 2) — read-only, display-only ─────────────
// Aggregate over CLOSED / released options paper trades
// (GET /api/options/portfolio/closed-analytics). No mutation.

export interface ClosedByStrategy {
  strategy: string;
  count: number;
  wins: number;
  losses: number;
  realized: number;
  win_rate: number | null;   // 0..1
}

export interface ClosedByExitReason {
  exit_reason: string;
  count: number;
  realized: number;
}

export interface OptionsClosedAnalytics {
  status: 'live' | 'empty';
  total_closed: number;
  wins: number;
  losses: number;
  breakeven: number;
  win_rate: number | null;        // 0..1
  total_realized: number;
  avg_winner: number | null;
  avg_loser: number | null;       // negative
  expectancy: number | null;
  profit_factor: number | null;   // null when no losses (undefined)
  by_strategy: ClosedByStrategy[];
  by_exit_reason: ClosedByExitReason[];
}

export function useOptionsClosedAnalytics() {
  return useQuery<OptionsClosedAnalytics>({
    queryKey: ['options', 'portfolio', 'closed-analytics'],
    queryFn: () =>
      apiGet<OptionsClosedAnalytics>('/options/portfolio/closed-analytics'),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}

// ── Promotion/rejection audit (Phase 3) — read-only, display-only ───────────
// Why option candidates were promoted or rejected per run_date
// (GET /api/options/portfolio/promotion-audit). No mutation.

export interface PromotionAuditRun {
  run_date: string;
  candidates_total: number;
  promoted: number;
  filled: number;
  skip_slot_full: number;
  skip_over_capital_cap: number;
  skip_proposal_duplicate: number;
  skip_other: number;
}

export interface PromotionAuditRejected {
  candidate_id: number;
  run_date: string;
  underlying: string;
  strategy: string;
  confidence: number | null;   // 0..1
  dte: number | null;
  reason: string;              // e.g. 'dte_out_of_range'
}

export interface PromotionAuditGates {
  universe: string;
  strategy: string;
  min_dte: number;
  max_dte: number;
  min_confidence: number;
  days: number;
}

export interface OptionsPromotionAudit {
  status: 'live' | 'empty';
  runs: PromotionAuditRun[];                 // newest first
  rejected: PromotionAuditRejected[];        // non-eligible only, newest first
  eligible_count: number;
  reason_counts: Record<string, number>;
  gates?: PromotionAuditGates;
}

export function useOptionsPromotionAudit() {
  return useQuery<OptionsPromotionAudit>({
    queryKey: ['options', 'portfolio', 'promotion-audit'],
    queryFn: () =>
      apiGet<OptionsPromotionAudit>('/options/portfolio/promotion-audit'),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });
}
