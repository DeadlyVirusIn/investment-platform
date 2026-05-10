// Market events / catalysts adapter.
//
// Frontend contract — NOT YET IMPLEMENTED on backend. Component
// gracefully shows a "not connected" empty state when the endpoint
// returns 404 / 501 / network error.
//
// Expected backend endpoint contracts:
//
//   GET /api/market/events?symbols=AAPL,MSFT,NVDA
//   {
//     "symbols": {
//       "AAPL": {
//         "earnings": [{ "date", "type", "estimate_eps", "actual_eps", "status" }],
//         "news":     [{ "title", "source", "published_at", "url", "sentiment", "summary" }],
//         "filings":  [{ "form", "filed_at", "title", "url" }],
//         "options_expirations": [{ "expiration", "open_interest_context" }]
//       }
//     },
//     "generated_at": "2026-05-10T..."
//   }
//
//   GET /api/asset/{symbol}/events  → same shape, single symbol
//
// Recommended providers (wired through PROVIDER_REGISTRY in api.ts):
//   - Polygon (news, earnings)
//   - Benzinga (news, sentiment)
//   - SEC EDGAR (filings)
//   - ThetaData / Tradier (options expirations)


export interface EarningsEvent {
  date: string;                          // ISO date
  type: "BMO" | "AMC" | "Pending" | string;
  estimate_eps: number | null;
  actual_eps: number | null;
  status: "upcoming" | "reported" | string;
}


export interface NewsItem {
  title: string;
  source: string;
  published_at: string;                  // ISO datetime
  url: string;
  sentiment: "positive" | "negative" | "neutral" | null;
  summary: string | null;
}


export interface FilingItem {
  form: string;                          // e.g. "10-Q", "8-K"
  filed_at: string;                      // ISO datetime
  title: string | null;
  url: string;
}


export interface OptionsExpiration {
  expiration: string;                    // ISO date
  open_interest_context: string | null;
}


export interface SymbolEvents {
  earnings: EarningsEvent[];
  news: NewsItem[];
  filings: FilingItem[];
  options_expirations: OptionsExpiration[];
}


export interface MarketEventsResponse {
  symbols: Record<string, SymbolEvents>;
  generated_at: string;
}


export type EventsState =
  | { status: "loading" }
  | { status: "ready"; data: MarketEventsResponse }
  | { status: "empty" }                   // no data yet
  | { status: "not-connected" };          // backend missing


async function tryFetchJson<T>(url: string): Promise<T | "not-found" | "error"> {
  try {
    const res = await fetch(url, { headers: { "Accept": "application/json" } });
    if (res.status === 404 || res.status === 501) return "not-found";
    if (!res.ok) return "error";
    return await res.json() as T;
  } catch {
    return "error";
  }
}


/**
 * Fetch market events for a list of symbols.
 * Returns one of four states; component renders accordingly.
 */
export async function fetchMarketEvents(symbols: string[]): Promise<EventsState> {
  if (symbols.length === 0) return { status: "empty" };
  const unique = Array.from(new Set(symbols.filter(Boolean))).slice(0, 25);
  if (unique.length === 0) return { status: "empty" };
  const url = `/api/market/events?symbols=${encodeURIComponent(unique.join(","))}`;
  const result = await tryFetchJson<MarketEventsResponse>(url);
  if (result === "not-found") return { status: "not-connected" };
  if (result === "error") return { status: "not-connected" };
  // Treat structurally-valid empty as "empty"
  if (!result.symbols || Object.keys(result.symbols).length === 0) {
    return { status: "empty" };
  }
  return { status: "ready", data: result };
}


/**
 * Fetch events for a single symbol — used by the research cockpit.
 */
export async function fetchSymbolEvents(symbol: string): Promise<EventsState> {
  if (!symbol) return { status: "empty" };
  const url = `/api/asset/${encodeURIComponent(symbol)}/events`;
  const result = await tryFetchJson<{ events: SymbolEvents; generated_at: string }>(url);
  if (result === "not-found" || result === "error") return { status: "not-connected" };
  if (!result.events) return { status: "empty" };
  return {
    status: "ready",
    data: { symbols: { [symbol]: result.events }, generated_at: result.generated_at },
  };
}


// ============================================================
// Per-card badges — derive a compact label from a SymbolEvents
// ============================================================

export interface EventBadge { text: string; tone: "good" | "warn" | "info" | "bad"; }


export function deriveBadge(events: SymbolEvents | undefined): EventBadge | null {
  if (!events) return null;

  // 1) Upcoming earnings within 7 days
  const upcoming = events.earnings.find(e => e.status === "upcoming");
  if (upcoming) {
    const days = Math.round((Date.parse(upcoming.date) - Date.now()) / 86_400_000);
    if (days >= 0 && days <= 14) {
      return { text: `Earnings in ${days}d`, tone: "info" };
    }
  }

  // 2) Recent filing within 7 days
  const recentFiling = events.filings.find(f => {
    const days = (Date.now() - Date.parse(f.filed_at)) / 86_400_000;
    return days >= 0 && days <= 7;
  });
  if (recentFiling) {
    return { text: `${recentFiling.form} filed`, tone: "info" };
  }

  // 3) News spike — 3+ items in last 24h
  const last24h = events.news.filter(n => {
    const ms = Date.now() - Date.parse(n.published_at);
    return ms >= 0 && ms <= 86_400_000;
  });
  if (last24h.length >= 3) {
    const negCount = last24h.filter(n => n.sentiment === "negative").length;
    return {
      text: "News spike",
      tone: negCount > last24h.length / 2 ? "bad" : "good",
    };
  }

  return null;
}
