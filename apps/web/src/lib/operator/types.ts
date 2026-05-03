// Phase UI1 — TypeScript contracts for DL2 / OPS1 endpoints.
// Mirrors backend schema: paper_portfolio_snapshot, paper_trade_log,
// decision_log, context_daily, features_daily.

export type Regime = "stress" | "directional" | "none";
export type Engine = "A" | "B" | "none";
export type Status = "production" | "candidate" | "diagnostic";
export type TradeStatus = "open" | "closed" | "cancelled";

export interface PaperSummary {
  as_of_date: string;           // YYYY-MM-DD
  equity: number;
  cash: number;
  total_return_pct: number;     // cum_pct
  max_drawdown_pct: number;
  daily_pnl: number;
  regime: Regime;
  engine_active: Engine;
  open_positions_count: number;
  last_decision_ts: string;
  pipeline_status: "success" | "partial" | "failed";
}

export interface CurrentState {
  as_of_date: string;
  stress_regime: boolean;
  directional_regime: boolean;
  engine: Engine;
  fire: boolean;
  reason: string;
  decision_version: string;
  blocked_by: string | null;
  gates_favorable: number;
  inputs_used: Record<string, unknown>;
  context_values: Record<string, boolean>;
  diagnostic_snapshot: Record<string, unknown>;
}

export interface EquityPoint {
  date: string;                 // YYYY-MM-DD
  equity: number;
  cum_pct: number;
  dd_pct: number;               // negative
  daily_pnl: number;
}

export interface TradeRow {
  trade_id: string;
  engine: Engine;
  instrument: string;
  entry_date: string;
  exit_date: string | null;
  entry_price: number;
  exit_price: number | null;
  position_size_pct: number;
  gross_ret_pct: number | null;
  net_ret_pct: number | null;
  pnl_dollar: number | null;
  regime_at_entry: Regime;
  status: TradeStatus;
  days_held: number | null;
  decision_version: string;
  reason: string | null;
}

export interface DecisionRow {
  id: string;
  decision_ts: string;
  as_of_date: string;
  engine: Engine;
  action: string;
  instrument: string;
  inputs_used: Record<string, unknown>;
  context_values: Record<string, boolean>;
  diagnostic_snapshot: Record<string, unknown> | null;
  decision_version: string;
  reason: string | null;
  blocked_by: string | null;
  // SYSTEM-ALPHA-2 additions — populated by nightly job
  factor_attribution?: {
    momentum?: number;
    volatility?: number;
    regime?: number;
    catalyst?: number;
    data_quality?: number;
    risk?: number;
    execution?: number;
    version?: string;
  } | null;
  factor_version?: string | null;
}

export interface PerformanceAttribution {
  engine_a: EngineStats;
  engine_b: EngineStats;
  stress_regime: RegimeStats;
  directional_regime: RegimeStats;
  monthly_pnl: MonthlyPnL[];
}

export interface EngineStats {
  n_trades: number;
  win_rate: number;
  avg_return_pct: number;
  avg_duration_bars: number;
  total_pnl_pct: number;
  sharpe_proxy: number;
}

export interface RegimeStats {
  n_bars: number;
  n_trades: number;
  pct_of_time: number;
  mean_return_pct: number;
}

export interface MonthlyPnL {
  month: string;                // YYYY-MM
  pnl_pct: number;
  n_trades: number;
}

export interface ShadowSignal {
  name: string;                 // gex_sign / ts_ratio / cot_context_flag
  status: Status;
  value: number | boolean | null;
  value_display: string;
  context_flag: boolean | null;
  source: string;
  last_updated: string;
  notes: string;                // e.g. "Phase X3 FAIL — not used in production"
}

export interface SystemHealthItem {
  key: string;
  severity: "info" | "warn" | "error";
  label: string;
  detail: string;
  first_seen: string;
  last_seen: string;
}

export interface SystemHealth {
  as_of_date: string;
  overall: "healthy" | "degraded" | "failed";
  items: SystemHealthItem[];
}

export type AnomalyCategory = "decision" | "trade" | "regime" | "data" | "shadow";
export type AnomalySeverity = "info" | "warning" | "critical";
export type AnomalyStatus = "open" | "acknowledged" | "resolved";

export interface AnomalyEvent {
  id: string;
  as_of_date: string;
  category: AnomalyCategory;
  severity: AnomalySeverity;
  rule_key: string;
  title: string;
  description: string;
  related_engine: string | null;
  related_trade_id: string | null;
  related_decision_id: string | null;
  metrics_snapshot: Record<string, unknown>;
  status: AnomalyStatus;
  created_at: string;
}

export interface AnomalySummary {
  total_open: number;
  by_severity: Record<AnomalySeverity, number>;
  by_category: Record<AnomalyCategory, number>;
  top3: AnomalyEvent[];
}
