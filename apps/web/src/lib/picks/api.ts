// Picks API client.
//
// Fetches /recommendations + normalizes action values across
// engine vocabulary (Buy/Sell/Trim/Hold/Watch/Accumulate/etc.).

export type PickAction = "buy" | "sell" | "trim" | "hold";


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


/** Optional pricing/risk fields the engine MAY include in rationale. */
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
  /** Normalized action (lowercase, mapped to 4-action set). */
  action: PickAction;
  /** Original raw action string from engine (for technical details). */
  raw_action: string;
  confidence: string | null;
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
  /** Same normalization as `action`. */
  adjusted_action: PickAction | null;
  raw_adjusted_action: string | null;
  adjusted_confidence: string | null;
  risk: PickRiskFields;
}


export interface PicksResponse {
  recommendations: Array<Record<string, unknown>>;
  count: number;
}


/**
 * Robust action normalization. Maps the engine's many
 * vocabularies to the 4-action UI set: buy / sell / trim / hold.
 *
 * - buy / long / bullish / accumulate / strong-buy → buy
 * - sell / short / bearish / avoid → sell
 * - trim / reduce / take-profit / lighten → trim
 * - hold / neutral / watch / monitor → hold
 *
 * Unknown values default to "hold" + a console.warn (dev visibility).
 */
export function normalizeAction(raw: unknown): PickAction {
  if (raw == null) return "hold";
  const s = String(raw).trim().toLowerCase().replace(/[\s_-]+/g, "");
  if (["buy", "long", "bullish", "accumulate", "strongbuy", "add", "open"].includes(s)) return "buy";
  if (["sell", "short", "bearish", "avoid", "exit", "strongsell"].includes(s)) return "sell";
  if (["trim", "reduce", "takeprofit", "lighten", "scaleback"].includes(s)) return "trim";
  if (["hold", "neutral", "watch", "monitor", "wait", "stable"].includes(s)) return "hold";

  if (typeof console !== "undefined") {
    console.warn(`[picks] unknown action value: '${raw}', defaulting to hold`);
  }
  return "hold";
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


function extractRisk(rec: Record<string, unknown>): PickRiskFields {
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


export async function fetchPicks(limit: number = 30): Promise<Pick[]> {
  const url = `/api/recommendations?latest=true&sort_by=confidence&order=desc&limit=${limit}`;
  const res = await fetch(url, {
    headers: { "Accept": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`fetchPicks failed: ${res.status} ${res.statusText}`);
  }
  const data = await res.json() as PicksResponse;

  const rows = data.recommendations ?? [];

  // DEV: log distinct action values so we can see what backend actually returns
  if (typeof console !== "undefined") {
    const distinct = Array.from(new Set(rows.map(r => String(r.action ?? "")))).filter(Boolean);
    if (distinct.length > 0) {
      console.info("[picks] distinct action values from API:", distinct);
    }
    const distinctAdj = Array.from(new Set(
      rows.map(r => String(r.adjusted_action ?? "")).filter(s => s && s !== "null"),
    ));
    if (distinctAdj.length > 0) {
      console.info("[picks] distinct adjusted_action values:", distinctAdj);
    }
  }

  return rows.map(rec => {
    const rawAction = rec.action as unknown;
    const rawAdjusted = rec.adjusted_action as unknown;
    return {
      ...(rec as object),
      action: normalizeAction(rawAction),
      raw_action: String(rawAction ?? "").trim(),
      adjusted_action: rawAdjusted != null ? normalizeAction(rawAdjusted) : null,
      raw_adjusted_action: rawAdjusted != null ? String(rawAdjusted).trim() : null,
      risk: extractRisk(rec),
    } as unknown as Pick;
  });
}


export interface LatestPrice {
  symbol: string;
  close: number;
  ts: string;
}


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


export async function fetchLatestPrices(
  symbols: ReadonlyArray<string>,
): Promise<Record<string, LatestPrice | null>> {
  const unique = Array.from(new Set(symbols.filter(Boolean)));
  const results = await Promise.all(unique.map(s => fetchLatestPrice(s)));
  const map: Record<string, LatestPrice | null> = {};
  unique.forEach((s, i) => { map[s] = results[i]; });
  return map;
}


export function fmtConfidencePct(conf: string | null): string {
  if (!conf) return "—";
  const n = parseFloat(conf);
  if (Number.isNaN(n)) return "—";
  const pct = n > 1 ? n : n * 100;
  return `${Math.round(pct)}%`;
}


export function confidenceLabel(conf: string | null): "High" | "Medium" | "Low" | "—" {
  if (!conf) return "—";
  const n = parseFloat(conf);
  if (Number.isNaN(n)) return "—";
  const pct = n > 1 ? n : n * 100;
  if (pct >= 70) return "High";
  if (pct >= 50) return "Medium";
  return "Low";
}


export function confidenceFraction(conf: string | null): number | null {
  if (!conf) return null;
  const n = parseFloat(conf);
  if (Number.isNaN(n)) return null;
  const frac = n > 1 ? n / 100 : n;
  return Math.max(0, Math.min(1, frac));
}


/** Human-readable per-action title shown in card + modal. */
export function actionTitle(action: PickAction): string {
  switch (action) {
    case "buy":  return "Potential opportunity";
    case "sell": return "Avoid or exit";
    case "trim": return "Consider reducing";
    case "hold": return "Keep watching";
  }
}


/** Plain-English "what to do" sentence per action. */
export function actionGuidance(action: PickAction): string {
  switch (action) {
    case "buy":  return "AI sees an entry opportunity. Review the thesis before acting.";
    case "sell": return "AI suggests exiting. Risk outweighs reward.";
    case "trim": return "AI suggests reducing exposure. Take some profit or de-risk.";
    case "hold": return "Keep watching but don't add more yet.";
  }
}
