// Catalyst types mirror backend `CatalystSummary.to_dict()`.

export type TradePolicy =
  | "neutral"
  | "reduce_size"
  | "require_confirmation"
  | "block_new_entry"
  | "watch_only";

export interface CatalystHeadline {
  title: string;
  source: string;
  url: string | null;
  published_at: string | null;
  sentiment: number | null;
  relevance: number | null;
}

export interface CatalystEvent {
  kind: string;
  date: string;
  title: string;
  confirmed: boolean;
}

export interface CatalystSummary {
  symbol: string;
  as_of: string;
  next_event: CatalystEvent | null;
  days_to_earnings: number | null;
  has_earnings_soon: boolean;
  headlines: CatalystHeadline[];
  catalyst_score: number;
  event_risk_score: number;
  trade_policy: TradePolicy;
  short_reason: string;
  data_confidence: number;
  providers_used: string[];
  partial: boolean;
}
