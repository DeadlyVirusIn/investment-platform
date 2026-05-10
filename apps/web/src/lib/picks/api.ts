// Picks API client.
//
// Fetches /recommendations (latest, sorted by confidence desc),
// extracts optional pricing/risk fields from rationale JSON,
// and lazy-loads latest price per symbol.

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


/** Optional pricing/risk fields the engine MAY include in rationale.
 *  All hidden by the modal when absent. No fake data. */
export interface PickRiskFields {
  target_price?: number | null;
  stop_loss?: number | null;
  entry_price?: number | null;
  risk_text?: string | null;
  invalidation_text?: string | null;
  what_changed_text?: string | null;
  next_watch_text?: string | null;
}


export interface Pick {
  id: string;
  asset_id: string;
  symbol: string | null;
  action: PickAction;
  confidence: string | null;          // string of decimal "0.82"
  confidence_label: string | null;
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
  /** Extracted from rationale JSON (best-effort; all optional) */
  risk: PickRiskFields;
}


export interface PicksResponse {
  recommendations: Array<Omit<Pick, "risk"> & { rationale?: string | Record<string, unknown> }>;
  count: number;
}


function asNumber(v: unknown): number | null {
  if (v == null) return null;
  if (typeof v === "number") return v;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}


function asString(v: unknown): string | null {
  if (v == null) return null;
  if (typeof v === "string" && v.trim().length > 0) return v;
  return null;
}


/** Pull pricing + risk fields from rationale JSON if present. */
function extractRisk(rec: Record<string, unknown>): PickRiskFields {
  // The /recommendations response already parses some rationale fields
  // (thesis, family_scores, etc.) and exposes them at top level. Optional
  // pricing fields are NOT yet exposed by the API but the schema allows
  // them. We look in two places: top-level adjustments + nested policy.
  const policy = (rec.policy as Record<string, unknown> | null) ?? {};
  const get = (k: string): unknown =>
    rec[k] ?? policy[k] ?? (rec[`adjusted_${k}` as keyof typeof rec] as unknown);
  return {
    target_price: asNumber(get("target_price")),
    stop_loss: asNumber(get("stop_loss")),
    entry_price: asNumber(get("entry_price")),
    risk_text: asString(get("risk")) ?? asString(get("risk_text")),
    invalidation_text: asString(get("invalidation")) ?? asString(get("invalidation_text")),
    what_changed_text: asString(get("what_changed")) ?? asString(get("what_changed_text")),
    next_watch_text: asString(get("next_watch")) ?? asString(get("next_watch_text")),
  };
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
  return (data.recommendations ?? []).map(rec => ({
    ...rec,
    risk: extractRisk(rec as unknown as Record<string, unknown>),
  })) as Pick[];
}


export interface LatestPrice {
  symbol: string;
  close: number;
  ts: string;            // ISO
}


/**
 * Latest close for a symbol. Best-effort — returns null if endpoint
 * empty or fails. Used by PickModal + prefetched batch on PicksPage.
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


/** Batch-fetch latest price for many symbols in parallel. */
export async function fetchLatestPrices(
  symbols: ReadonlyArray<string>,
): Promise<Record<string, LatestPrice | null>> {
  const unique = Array.from(new Set(symbols.filter(Boolean)));
  const results = await Promise.all(unique.map(s => fetchLatestPrice(s)));
  const map: Record<string, LatestPrice | null> = {};
  unique.forEach((s, i) => { map[s] = results[i]; });
  return map;
}


/**
 * Format a confidence string ("0.82") into a percent label ("82%").
 * Returns "—" on null/invalid.
 */
export function fmtConfidencePct(conf: string | null): string {
  if (!conf) return "—";
  const n = parseFloat(conf);
  if (Number.isNaN(n)) return "—";
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


/** Returns 0-1 normalized confidence for the meter. Null on invalid. */
export function confidenceFraction(conf: string | null): number | null {
  if (!conf) return null;
  const n = parseFloat(conf);
  if (Number.isNaN(n)) return null;
  const frac = n > 1 ? n / 100 : n;
  return Math.max(0, Math.min(1, frac));
}
