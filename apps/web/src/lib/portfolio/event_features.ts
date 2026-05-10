// Phase 10 — frontend adapter for /api/event-features.

export interface EventFeatures {
  recent_8k_count_7d: number;
  recent_10q_or_10k_flag: boolean;
  news_count_3d: number;
  negative_news_count_3d: number;
  positive_news_count_3d: number;
  catalyst_freshness_score: number;
  earnings_within_14d: boolean;
  filing_recency_days: number | null;
  high_impact_news_flag: boolean;
  event_risk_score: number;
  event_momentum_score: number;
  tags: string[];
  explainers: string[];
  available: boolean;
  reason: string | null;
}


export interface EventFeaturesResponse {
  symbols: Record<string, EventFeatures>;
  generated_at: string;
  providers?: { sec_edgar?: boolean; polygon?: boolean; benzinga?: boolean };
  notice?: string;
}


export async function fetchEventFeatures(symbols: string[]): Promise<EventFeaturesResponse | null> {
  if (symbols.length === 0) return null;
  const unique = Array.from(new Set(symbols.filter(Boolean))).slice(0, 25);
  if (unique.length === 0) return null;
  const url = `/api/event-features?symbols=${encodeURIComponent(unique.join(","))}`;
  try {
    const res = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!res.ok) return null;
    return await res.json() as EventFeaturesResponse;
  } catch {
    return null;
  }
}
