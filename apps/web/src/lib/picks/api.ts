// Picks API client.
//
// Fetches /recommendations (latest, sorted by confidence desc) +
// lazy-loads latest price per symbol when the modal opens.

export type PickAction = "buy" | "sell" | "hold";


export interface PickEvidence {
  factor_key: string;
  family: string | null;
  weight: string | null;
  value: unknown;
  threshold: unknown;
  direction: string | null;
  score: unknown;
  narrative: string;
}


export interface Pick {
  id: string;
  asset_id: string;
  symbol: string | null;
  action: PickAction;
  confidence: string | null;          // string of decimal "0.82"
  confidence_label: string | null;    // "high" | "medium" | "low" maybe
  enough_data: boolean;
  stale_data: boolean;
  engine_version: string | null;
  thesis: string | null;
  tags: string[];
  composite_score: number | string | null;
  family_scores: Record<string, number | string>;
  generated_at: string | null;
  evidence: PickEvidence[];
  policy: Record<string, unknown> | null;
  adjusted_action: PickAction | null;
  adjusted_confidence: string | null;
}


export interface PicksResponse {
  recommendations: Pick[];
  count: number;
}


/**
 * Fetch latest recommendations sorted by confidence desc.
 * Returns at most `limit` (default 30).
 */
export async function fetchPicks(limit: number = 30): Promise<Pick[]> {
  const url = `/api/recommendations?latest=true&sort_by=confidence&order=desc&limit=${limit}`;
  const res = await fetch(url, {
    headers: { "Accept": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`fetchPicks failed: ${res.status} ${res.statusText}`);
  }
  const data = await res.json() as PicksResponse;
  return data.recommendations ?? [];
}


export interface LatestPrice {
  symbol: string;
  close: number;
  ts: string;            // ISO
}


/**
 * Latest close for a symbol. Best-effort — returns null if endpoint
 * empty or fails. Used by PickModal to show "Latest: $X" line.
 */
export async function fetchLatestPrice(symbol: string): Promise<LatestPrice | null> {
  try {
    const url = `/api/asset/${encodeURIComponent(symbol)}/prices?limit=1`;
    const res = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!res.ok) return null;
    const data = await res.json() as {
      prices: Array<{ ts: string; close: string | number }>;
    };
    const last = data.prices?.[0];
    if (!last) return null;
    return {
      symbol,
      close: typeof last.close === "string" ? parseFloat(last.close) : last.close,
      ts: last.ts,
    };
  } catch {
    return null;
  }
}


/**
 * Format a confidence string ("0.82") into a percent label ("82%").
 * Returns "—" on null/invalid.
 */
export function fmtConfidencePct(conf: string | null): string {
  if (!conf) return "—";
  const n = parseFloat(conf);
  if (Number.isNaN(n)) return "—";
  // backend may use 0-1 OR 0-100 conviction — handle both
  const pct = n > 1 ? n : n * 100;
  return `${Math.round(pct)}%`;
}


/** Confidence label from numeric. "High" >=70, "Medium" >=50, "Low" else. */
export function confidenceLabel(conf: string | null): "High" | "Medium" | "Low" | "—" {
  if (!conf) return "—";
  const n = parseFloat(conf);
  if (Number.isNaN(n)) return "—";
  const pct = n > 1 ? n : n * 100;
  if (pct >= 70) return "High";
  if (pct >= 50) return "Medium";
  return "Low";
}
