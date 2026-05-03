// Shared TypeScript types for API responses. Keep aligned with backend
// Pydantic shapes. Nulls preserved where backend returns null.

export interface PortfolioSummary {
  id: string;
  name: string;
  starting_cash: string;
  cash: string;
  positions_value: string;
  total_equity: string;
  unrealized_pnl: string;
  realized_pnl_cumulative: string;
  total_return_pct: string | null;
  is_active: boolean;
  created_at: string | null;
}

export interface Position {
  position_id: string;
  asset_id: string;
  symbol: string;
  quantity: string;
  avg_cost: string;
  last_price: string | null;
  market_value: string | null;
  unrealized_pnl: string | null;
  opened_at: string | null;
}

export interface TradeCounts {
  wins: number;
  losses: number;
  breakeven: number;
}

export interface Trade {
  trade_id: string;
  asset_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: string;
  fill_price: string;
  fill_ts: string | null;
  submitted_at: string | null;
  realized_pnl: string | null;
  reason: string | null;
  recommendation_id: string | null;
}

export interface EquityPoint {
  snapshot_date: string | null;
  cash: string;
  positions_value: string;
  total_equity: string;
  unrealized_pnl: string | null;
  realized_pnl_cumulative: string | null;
}

export interface DrawdownStats {
  max_drawdown_pct: string | null;
  max_drawdown_duration_days: number | null;
  peak_equity: string | null;
  trough_equity: string | null;
}

export interface ConfidenceValidationRow {
  bucket: string;
  count: number;
  wins: number;
  losses: number;
  hit_rate: string | null;
  avg_realized_pnl: string | null;
}

export interface PortfolioDetail extends PortfolioSummary {
  open_positions: Position[];
  trade_counts: TradeCounts;
  validation: {
    drawdown: DrawdownStats;
    confidence_validation: ConfidenceValidationRow[];
  };
}

export interface PortfolioListResponse {
  portfolios: PortfolioSummary[];
  count: number;
}

export interface TradesResponse {
  trades: Trade[];
  count: number;
  counts: TradeCounts;
}

export interface PaperPerformanceSummary {
  portfolio_id: string | null;
  total_return: string | null;
  max_drawdown: string | null;
  hit_rate: string | null;
  expectancy: string | null;
  profit_factor: string | null;
  sharpe: string | null;
  trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  empty_state: boolean;
}

export interface PaperEquityCurvePoint {
  date: string;
  equity: string;
}

export interface PaperEquityCurveResponse {
  portfolio_id: string | null;
  points: PaperEquityCurvePoint[];
}

export interface EquityResponse {
  current: {
    cash: string;
    positions_value: string;
    total_equity: string;
    unrealized_pnl: string | null;
    realized_pnl_cumulative: string | null;
  };
  curve: EquityPoint[];
}

// --- Recommendations ---

export interface Evidence {
  factor_key: string;
  family: string;
  weight: string | null;
  value: string | null;
  threshold: string | null;
  direction: string | null;
  score: string | null;
  narrative: string;
}

export interface Recommendation {
  id: string;
  asset_id: string;
  symbol: string | null;
  action: 'Buy' | 'Hold' | 'Trim' | 'Sell' | 'Watch' | string;
  confidence: string | null;
  confidence_label: string | null;
  enough_data: boolean;
  stale_data: boolean;
  engine_version: string | null;
  snapshot_hash: string | null;
  thesis: string | null;
  tags: string[];
  composite_score: string | null;
  family_scores: Record<string, string>;
  generated_at: string | null;
  evidence: Evidence[];
  adjusted_action: string | null;
  adjusted_confidence: string | null;
  adjusted_composite_score: string | null;
  policy_adjustments: Array<{ rule: string; reason: string }>;
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
  count: number;
}

// --- Performance ---

export interface CoreMetrics {
  total_trades: number;
  wins: number;
  losses: number;
  neutral: number;
  hit_rate: string | null;
  win_rate: string | null;
  expectancy: string | null;
  avg_return: string | null;
  median_return: string | null;
  profit_factor: string | null;
  total_return: string | null;
}

export interface BucketRow {
  bucket: string;
  count: number;
  hit_rate: string | null;
  expectancy: string | null;
  median_return: string | null;
}

export interface AssetRow {
  symbol: string;
  asset_id: string;
  count: number;
  wins: number;
  losses: number;
  hit_rate: string | null;
  expectancy: string | null;
  median_return: string | null;
}

export interface RegimeRow {
  regime: string;
  count: number;
  hit_rate: string | null;
  expectancy: string | null;
  median_return: string | null;
}

export interface MatrixCell {
  confidence_bucket: string;
  regime: string;
  count: number;
  hit_rate: string | null;
  expectancy: string | null;
  median_return: string | null;
}

export interface Insights {
  confidence_inversion: Array<{
    higher_bucket: string;
    higher_hit_rate: string;
    lower_bucket: string;
    lower_hit_rate: string;
    spread: string;
  }>;
  regime_sensitivity: Array<{
    dimension: string;
    best_regime: string;
    best_hit_rate: string;
    worst_regime: string;
    worst_hit_rate: string;
    spread: string;
  }>;
  low_sample_warnings: Array<{
    dimension: string;
    label: string;
    count: number;
  }>;
}

export interface ExperimentalMetrics {
  __warning__: string;
  annualization: number;
  sharpe_ratio: string | null;
  sortino_ratio: string | null;
  calmar_ratio: string | null;
  max_drawdown: string | null;
  max_drawdown_duration: number | null;
}

// --- Benchmark prices ---

export interface PricePoint {
  ts: string | null;
  close: string | null;
  adjusted_close: string | null;
}

export interface PricesResponse {
  symbol: string;
  timeframe: string;
  count: number;
  prices: PricePoint[];
}

export interface PerformanceReport {
  window: string;
  recommendation_metrics: {
    tier_1_core: CoreMetrics;
    tier_2_conditional: {
      confidence_buckets: BucketRow[];
      per_asset: AssetRow[];
      per_month: Array<{ month: string; count: number; hit_rate: string | null; expectancy: string | null }>;
      by_trend_regime: RegimeRow[];
      by_volatility_regime: RegimeRow[];
      by_drawdown_regime: RegimeRow[];
      confidence_regime_matrix: {
        trend: MatrixCell[];
        volatility: MatrixCell[];
        drawdown: MatrixCell[];
      };
      insights: Insights;
    };
  };
  experimental_metrics: ExperimentalMetrics;
}

// ---------------------------------------------------------------------------
// Dashboard + PnL + StockEngine (Phase-5 backend shapes)
// ---------------------------------------------------------------------------

export interface DashboardAlert {
  code: string;
  severity: 'info' | 'warning' | 'critical';
  message: string;
}

export interface DashboardRegime {
  as_of_date: string;
  benchmark_symbol: string;
  market_trend: string;
  vol_regime: string;
  breadth_regime: string | null;
  sma50_over_sma200: boolean;
  realized_vol_20d: string;
  atr_pctile_1y: string;
}

export interface DashboardTopBuy {
  symbol: string;
  sector: string;
  composite_score: string | null;
  confidence: string | null;
}

export interface DashboardBlockedAlphaItem {
  symbol: string;
  composite_score: string | null;
  rejection_reason: string | null;
}

export interface DashboardPortfolioPosition {
  symbol: string;
  quantity: string;
  avg_cost: string;
  mark: string | null;
  market_value: string;
  weight: string;
  unrealized_pnl: string;
  unrealized_pct: string | null;
}

export interface DashboardPortfolio {
  portfolio_id: string;
  nav: string;
  cash: string;
  invested: string;
  open_positions_count: number;
  top_positions: DashboardPortfolioPosition[];
  sector_exposure: Record<string, string>;
}

export interface DashboardSummary {
  as_of_date: string | null;
  regime: DashboardRegime | null;
  candidates: {
    total_evaluated: number;
    accepted_total: number;
    accepted_buys: number;
    rejected_total: number;
    reasons: Record<string, number>;
  };
  blocked_alpha: {
    min_score: string;
    count: number;
    top: DashboardBlockedAlphaItem[];
  };
  top_buys: DashboardTopBuy[];
  portfolio: DashboardPortfolio | null;
  alerts: DashboardAlert[];
}

export interface PnlSummary {
  as_of_date: string;
  portfolio_id: string;
  starting_cash: string;
  cash: string;
  invested: string;
  nav: string;
  cumulative_pnl: string;
  daily_pnl: string | null;
  realized_pnl: string;
  unrealized_pnl: string;
  open_positions: number;
  closed_trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  win_rate: string | null;
  avg_win: string | null;
  avg_loss: string | null;
}

export interface PnlBySymbolItem {
  asset_id: string;
  symbol: string | null;
  status: 'open' | 'closed';
  quantity: string | null;
  avg_cost: string | null;
  mark: string | null;
  realized_pnl: string;
  unrealized_pnl: string;
  total_pnl: string;
  holding_days: number | null;
  entry_composite_score: string | null;
  entry_confidence: string | null;
  entry_market_trend: string | null;
  entry_vol_regime: string | null;
}

export interface PnlBySymbolResponse {
  portfolio_id: string;
  count: number;
  items: PnlBySymbolItem[];
}

export interface PnlBucket {
  bucket: string;
  trade_count: number;
  wins: number;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  total_pnl: string | null;
  avg_pnl_per_trade: string | null;
}

export interface PnlByScoreBucketResponse {
  portfolio_id: string;
  buckets: PnlBucket[];
}

export interface PnlRegimeStat {
  market_trend: string;
  vol_regime: string;
  trade_count: number;
  realized_pnl: string | null;
  unrealized_pnl: string | null;
  total_pnl: string | null;
  avg_pnl_per_trade: string | null;
}

export interface PnlByRegimeResponse {
  portfolio_id: string;
  regimes: PnlRegimeStat[];
}

export interface StockCandidate {
  id: string;
  as_of_date: string;
  asset_id: string;
  symbol: string | null;
  model_version: string;
  engine: string;
  status: 'accepted' | 'rejected';
  action: string | null;
  rejection_reason: string | null;
  composite_score: string | null;
  confidence: string | null;
  factor_breakdown: Record<string, unknown>;
  regime_snapshot: Record<string, unknown>;
  generated_at: string | null;
}

export interface StockCandidatesResponse {
  as_of_date: string | null;
  count: number;
  candidates: StockCandidate[];
}

export interface RejectionSummaryResponse {
  as_of_date: string | null;
  total_evaluated: number;
  accepted: number;
  rejected: number;
  reasons: Record<string, number>;
}

export interface OpsJob {
  name: string;
  cron: string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
  last_status: 'success' | 'error' | 'running' | null;
  last_duration_seconds: string | null;
  last_error: string | null;
}

export interface OpsStatusResponse {
  scheduler_alive: boolean;
  checked_at: string;
  jobs: OpsJob[];
  counts: Record<string, number>;
  latest: Record<string, string | null>;
}

export interface WatchlistItem {
  symbol: string;
  added_at: string | null;
  last_close: string | null;
  change_pct: string | null;
}

export interface WatchlistResponse {
  count: number;
  items: WatchlistItem[];
}

export interface AppSettings {
  benchmark_symbol: string;
  default_portfolio_name: string;
  data_refresh_enabled: boolean;
  tiingo_api_key_override_present: boolean;
  tiingo_api_key_override_masked: string;
}

// ---------------------------------------------------------------------------
// News Intelligence
// ---------------------------------------------------------------------------

export interface NewsItem {
  id: string;
  source: string;
  url: string;
  title: string;
  summary: string | null;
  published_at: string;
  category: string;
  sentiment: 'positive' | 'neutral' | 'negative';
  sentiment_score: string;
  impact_level: 'low' | 'medium' | 'high';
  impact_score: number;
  symbols: string[];
}

export interface NewsSymbolSummary {
  symbol: string;
  window_days: number;
  article_count: number;
  avg_sentiment: string | null;
  sentiment_label: 'positive' | 'neutral' | 'negative' | 'unknown';
  dominant_category: string | null;
  category_counts: Record<string, number>;
  max_impact_score: number;
  latest: NewsItem | null;
}

export interface NewsSymbolResponse {
  symbol: string;
  summary: NewsSymbolSummary;
  count: number;
  items: NewsItem[];
}

export interface NewsSummaryBatchResponse {
  days: number;
  count: number;
  summaries: Record<string, NewsSymbolSummary>;
}

export interface NewsMarketSummary {
  window_days: number;
  total_articles: number;
  category_counts: Record<string, number>;
  sentiment_counts: Record<string, number>;
  top_headlines: NewsItem[];
}

// ---------------------------------------------------------------------------
// Intelligence Console (Phase 2)
// ---------------------------------------------------------------------------

export interface DecisionReviewAvB {
  accepted_count: number;
  accepted_avg_return_pct: string | null;
  accepted_win_rate: string | null;
  blocked_count: number;
  blocked_avg_return_pct: string | null;
  blocked_win_rate: string | null;
  win_rate_delta: string | null;
}

export interface DecisionReviewBucket {
  bucket: string;
  trade_count: number;
  wins: number;
  avg_pnl_per_trade: string | null;
  win_rate: string | null;
}

export interface DecisionReviewReason {
  reason: string;
  rejected_count: number;
  simulated_count: number;
  simulated_avg_return: string | null;
  simulated_win_rate: string | null;
}

export interface DecisionReviewMissed {
  symbol: string | null;
  as_of_date: string;
  rejection_reason: string;
  return_pct: string;
  composite_score: string;
}

export interface DecisionReview {
  sample_notes: string[];
  accepted_vs_blocked: DecisionReviewAvB | null;
  bucket_performance: DecisionReviewBucket[];
  rejection_quality: DecisionReviewReason[];
  missed_opportunities: DecisionReviewMissed[];
}

export interface PortfolioIntelTopPos {
  symbol: string | null;
  weight: string;
  unrealized_pnl: string;
  unrealized_pct: string | null;
}

export interface PortfolioIntel {
  nav: string;
  cash: string;
  invested: string;
  cash_pct: string | null;
  invested_pct: string | null;
  open_positions: number;
  top_positions: PortfolioIntelTopPos[];
  top1_weight: string | null;
  top2_weight_sum: string | null;
  sector_exposure: Array<{ sector: string; weight: string }>;
  regime_mix: Array<{ market_trend: string; vol_regime: string; count: number }>;
  avg_slippage_bps: string | null;
  max_slippage_bps: string | null;
  flags: string[];
  notes: string[];
}

export interface NewsBucketStat {
  key: string;
  trade_count: number;
  avg_return_pct: string | null;
  wins: number;
  losses: number;
}

export interface NewsAnalysis {
  trades_analyzed: number;
  alignment_pct: string | null;
  sample_notes: string[];
  by_sentiment: NewsBucketStat[];
  by_category: NewsBucketStat[];
}

export interface TuningSuggestion {
  code: string;
  severity: 'info' | 'warn' | 'critical';
  message: string;
  reasoning: string;
}

export interface IntelligenceSummary {
  decision_review: DecisionReview;
  portfolio: PortfolioIntel;
  news: NewsAnalysis;
  tuning_advice: {
    count: number;
    suggestions: TuningSuggestion[];
  };
}

export interface BriefingNarrative {
  as_of_date: string | null;
  narrative: string;
  regime: { market_trend: string; vol_regime: string } | null;
  portfolio_flags: string[];
  tuning_top: Array<{ code: string; severity: string; message: string }>;
  delta: {
    nav: string | null;
    nav_pct: string | null;
    positions: number | null;
    candidates: number | null;
    accepted_buys: number | null;
    regime_changed: boolean;
    prev_regime: { market_trend: string; vol_regime: string } | null;
  };
}

// --- Decision UX (v1) -------------------------------------------------------

export type ActionKind = 'BUY' | 'EXIT' | 'TRIM' | 'HOLD' | 'WATCH' | 'RESOLVE_ALERT';
export type ActionStatus = 'pending' | 'acted' | 'dismissed' | 'expired' | 'blocked';
export type ActionTier = 'CRT' | 'HIGH' | 'NRM';

export interface FactorTop {
  key: string;
  contribution: number;
  value: number | null;
}

export interface ActionDependencies {
  requires_cash?: number | null;
  conflicts_with?: string[];
  blocks_on?: string[];
}

export interface ActionImpact {
  position_delta_pct?: number;
  portfolio_weight_after?: number;
  notional_usd?: number;
}

export interface ActionItem {
  id: string;
  as_of_date: string | null;
  kind: ActionKind;
  symbol: string;
  sector: string | null;
  asset_id: string;
  candidate_id: string | null;
  priority: string;
  priority_tier: ActionTier;
  urgency: string;
  confidence: string | null;
  composite_score: string | null;
  rationale_short: string;
  factor_top: FactorTop[] | null;
  impact_estimate: ActionImpact | null;
  decay_at: string | null;
  dependencies: ActionDependencies;
  origin: string;
  status: ActionStatus;
  acted_trade_id: string | null;
  acted_at: string | null;
  dismissed_at: string | null;
  dismiss_reason: string | null;
  created_at: string | null;
}

export interface ActionsListResponse {
  actions: ActionItem[];
  count: number;
  status: ActionStatus;
}

export interface ActResponse {
  action_id: string;
  trade_id: string;
  fill_price: string;
  fill_ts: string;
  cash_after: string;
}
