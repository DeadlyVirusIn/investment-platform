// Portfolio intelligence API — wires multiple existing endpoints
// into a unified shape for the command bar, positions table, and
// strategy modules. All endpoints are read-only and existing.
// Honest data only — undefined fields stay undefined; never faked.

export interface CommandBarData {
  totalNav: number | null;
  openPnl: number | null;
  realizedPnl: number | null;
  totalReturnPct: number | null;
  monthlyPremium: number | null;
  activeStrategies: number | null;
  portfolioRiskLabel: string | null;
  cashAvailable: number | null;
  posture: string | null;
  freshAt: string | null;
  // ---- Canonical paper-portfolio fields (Phase 13k data-truth fix) ----
  // These mirror /api/paper/summary so the Overview snapshot agrees
  // with PortfolioTerminal byte-for-byte. Numbers above the line that
  // overlap with these (totalNav, cashAvailable, openPnl,
  // totalReturnPct) are now ALSO sourced from /api/paper/summary —
  // /api/dashboard/summary is no longer the canonical source for
  // portfolio numerics. Dashboard summary stays canonical only for
  // posture / regime / risk-label / monthly premium fields that
  // paper-summary does not expose.
  moneyInvested: number | null;       // mark-to-market sum of open positions
  openPositionsCount: number | null;
  dailyPnl: number | null;
  unrealizedPnl: number | null;       // alias of openPnl from paper-summary
}


export interface PositionRow {
  position_id: string;
  symbol: string;
  portfolio_name: string | null;
  quantity: number;
  avg_cost: number | null;
  is_open: boolean;
  opened_at: string | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  return_pct: number | null;
  source: string | null;
}


export interface StrategyRow {
  rule_id: string;
  name: string;
  summary: string;
  observations_count?: number;
  qualified_count?: number;
  win_rate?: number | null;
  avg_premium?: number | null;
}


function asNum(v: unknown): number | null {
  if (v == null) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const n = parseFloat(v);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}


async function safeFetch<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!res.ok) return null;
    return await res.json() as T;
  } catch {
    return null;
  }
}


// Phase 13k data-truth fix —
// CANONICAL portfolio numbers (NAV, cash, total return %, daily P&L,
// money invested, open positions count, unrealized P&L, freshAt) come
// from /api/paper/summary. That endpoint aggregates across every paper
// portfolio the user owns; PortfolioTerminal already reads it via
// usePaperSummary. Reading it here too guarantees Overview and
// Portfolio show the same numbers.
//
// /api/dashboard/summary returns ONE portfolio (the snapshotted "lead"
// portfolio used by older dashboards). Until 13k it was the source of
// Overview's NAV / cash — that meant Overview displayed $10,501 / $48
// while Portfolio displayed $117,585 / $537. Same user, same minute,
// different scopes. Fixed.
//
// Dashboard summary is still queried — it remains canonical for
// posture / regime / risk-label fields that paper-summary doesn't
// expose. Options endpoints (risk-summary, performance-summary) stay
// canonical for monthly premium + active strategies.
export async function fetchCommandBar(): Promise<CommandBarData> {
  const [paper, dash, exec, opsRisk, opsPerf] = await Promise.all([
    safeFetch<Record<string, unknown>>("/api/paper/summary"),
    safeFetch<Record<string, unknown>>("/api/dashboard/summary"),
    safeFetch<Record<string, unknown>>("/api/paper/executed/summary"),
    safeFetch<Record<string, unknown>>("/api/options/risk-summary"),
    safeFetch<Record<string, unknown>>("/api/options/performance-summary"),
  ]);

  const dashPort = (dash?.portfolio as Record<string, unknown> | undefined) ?? {};
  const dashPnl = (dashPort.pnl as Record<string, unknown> | undefined)
    ?? (dash?.pnl as Record<string, unknown> | undefined)
    ?? {};
  const dashRegime = (dash?.regime as Record<string, unknown> | undefined) ?? {};

  const opsPerfTotals = (opsPerf?.totals as Record<string, unknown> | undefined) ?? {};
  const opsRiskOpen = (opsRisk?.open_positions as Record<string, unknown> | undefined) ?? {};

  // Canonical numerics from paper-summary (aggregate across all paper
  // portfolios). asNum nulls out NaN / undefined / non-finite values.
  const paperEquity         = asNum(paper?.equity);
  const paperCash           = asNum(paper?.cash);
  const paperPositionsValue = asNum(paper?.positions_value);
  const paperUnrealized     = asNum(paper?.unrealized_pnl);
  const paperReturnPct      = asNum(paper?.total_return_pct);
  const paperDailyPnl       = asNum(paper?.daily_pnl);
  const paperOpenPositions  = asNum(paper?.open_positions_count);
  const paperFreshAt        = paper?.as_of_date as string | undefined;

  // ---- Dev-mode source map + drift check (Phase 13k) ----
  // Logs which endpoint provided each numeric the first time the
  // command bar is fetched in a session. Warns loudly if the older
  // dashboard.summary numerics diverge from paper-summary by more
  // than 1% — the exact regression class this fix addresses.
  if (import.meta.env.DEV && !__commandBarLogged) {
    __commandBarLogged = true;
    /* eslint-disable no-console */
    console.info(
      "[CommandBar] canonical source = /api/paper/summary",
      {
        nav: paperEquity, cash: paperCash, returnPct: paperReturnPct,
        positions: paperOpenPositions, freshAt: paperFreshAt,
      },
    );
    const dashNav = asNum(dashPort.market_value)
      ?? asNum(dashPort.total_nav) ?? asNum(dash?.nav);
    if (paperEquity != null && dashNav != null) {
      const driftPct = Math.abs(paperEquity - dashNav)
        / Math.max(1, paperEquity) * 100;
      if (driftPct > 1) {
        console.warn(
          `[CommandBar] NAV drift ${driftPct.toFixed(1)}% between `
          + `/api/paper/summary (=${paperEquity}) and `
          + `/api/dashboard/summary (=${dashNav}). `
          + "paper-summary is canonical; dashboard-summary is one "
          + "portfolio's snapshot.",
        );
      }
    }
    /* eslint-enable no-console */
  }

  return {
    totalNav: paperEquity
      // Fallbacks ONLY if paper-summary unavailable; preserves old
      // single-portfolio behavior in degraded mode.
      ?? asNum(dashPort.market_value)
      ?? asNum(dashPort.total_nav)
      ?? asNum(dash?.nav)
      ?? null,
    openPnl: paperUnrealized
      ?? asNum(dashPnl.unrealized_pnl)
      ?? asNum(dashPnl.open_pnl)
      ?? null,
    realizedPnl: asNum(dashPnl.realized_pnl) ?? null,
    totalReturnPct: paperReturnPct
      ?? asNum(dashPnl.total_return_pct)
      ?? asNum(dashPort.total_return_pct)
      ?? null,
    monthlyPremium: asNum(opsPerfTotals.premium_collected_30d)
      ?? asNum(opsPerfTotals.monthly_premium)
      ?? asNum(opsPerf?.monthly_premium)
      ?? null,
    activeStrategies: asNum(opsRisk?.active_strategies)
      ?? asNum(opsRiskOpen.distinct_strategies)
      ?? asNum(exec?.open_positions)
      ?? null,
    portfolioRiskLabel: (dashPort.risk_label as string | undefined)
      ?? (dashRegime.vol_regime as string | undefined)
      ?? null,
    cashAvailable: paperCash
      ?? asNum((dashPort.cash as Record<string, unknown> | undefined)?.available)
      ?? asNum((dashPort.cash as Record<string, unknown> | undefined)?.cash_available)
      ?? asNum(dashPort.cash)
      ?? null,
    posture: (dashPort.posture as string | undefined)
      ?? (dashRegime.market_trend as string | undefined)
      ?? null,
    freshAt: paperFreshAt
      ?? (dash?.as_of_date as string | undefined)
      ?? (dash?.generated_at as string | undefined)
      ?? null,
    // ---- Canonical paper-summary additions (Phase 13k) ----
    moneyInvested: paperPositionsValue ?? null,
    openPositionsCount: paperOpenPositions ?? null,
    dailyPnl: paperDailyPnl ?? null,
    unrealizedPnl: paperUnrealized ?? null,
  };
}

// Module-scoped flag so dev-mode source log fires once per page load
// instead of on every refetch (TanStack default 60s interval).
let __commandBarLogged = false;


export async function fetchOpenPositions(): Promise<PositionRow[]> {
  const data = await safeFetch<{ positions?: Array<Record<string, unknown>> }>(
    "/api/paper/executed/positions?is_open=true",
  );
  const rows = data?.positions ?? [];
  return rows.map(r => ({
    position_id: String(r.position_id ?? r.id ?? ""),
    symbol: String(r.symbol ?? "—"),
    portfolio_name: (r.portfolio_name as string | null) ?? null,
    quantity: asNum(r.quantity) ?? 0,
    avg_cost: asNum(r.avg_cost),
    is_open: Boolean(r.is_open),
    opened_at: (r.opened_at as string | null) ?? null,
    market_value: asNum(r.market_value),
    unrealized_pnl: asNum(r.unrealized_pnl),
    return_pct: asNum(r.return_pct),
    source: (r.source as string | null) ?? null,
  }));
}


export async function fetchStrategies(): Promise<StrategyRow[]> {
  const data = await safeFetch<{
    strategies?: Array<Record<string, unknown>>;
  }>("/api/options/strategies");
  const rows = data?.strategies ?? [];
  return rows.map(r => ({
    rule_id: String(r.rule_id ?? r.id ?? ""),
    name: String(r.name ?? r.rule_id ?? "Strategy"),
    summary: String(r.summary ?? r.description ?? ""),
    observations_count: asNum(r.observations_count) ?? undefined,
    qualified_count: asNum(r.qualified_count) ?? undefined,
    win_rate: asNum(r.win_rate),
    avg_premium: asNum(r.avg_premium),
  }));
}


// Premium income — best-effort. Endpoint may not exist; component
// renders a friendly empty state when null is returned.
export interface PremiumPoint { month: string; amount: number; }


export async function fetchPremiumIncome(): Promise<PremiumPoint[] | null> {
  const data = await safeFetch<{
    monthly?: Array<Record<string, unknown>>;
    by_month?: Array<Record<string, unknown>>;
  }>("/api/options/performance-summary");
  if (!data) return null;
  const arr = data.monthly ?? data.by_month;
  if (!arr || !Array.isArray(arr) || arr.length === 0) return null;
  return arr
    .map(r => {
      const month = String(r.month ?? r.period ?? r.label ?? "");
      const amount = asNum(r.premium ?? r.amount ?? r.total) ?? 0;
      return { month, amount };
    })
    .filter(p => p.month);
}


export function fmtCurrency(n: number | null, opts?: { compact?: boolean }): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  if (opts?.compact && abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (opts?.compact && abs >= 10_000) return `$${(n / 1000).toFixed(1)}k`;
  if (abs >= 1000) return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `$${n.toFixed(2)}`;
}


export function fmtPct(n: number | null): string {
  if (n == null) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}


export function fmtSigned(n: number | null): string {
  if (n == null) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${fmtCurrency(n)}`;
}


// ============================================================
// Equity curve — /api/performance/equity-curve
// ============================================================

export interface EquityPoint { date: string; equity: number; }

export async function fetchEquityCurve(): Promise<EquityPoint[]> {
  const data = await safeFetch<{ points?: Array<{ date: string; equity: string | number }> }>(
    "/api/performance/equity-curve",
  );
  const pts = data?.points ?? [];
  return pts
    .map(p => ({ date: p.date, equity: typeof p.equity === "string" ? parseFloat(p.equity) : p.equity }))
    .filter(p => !Number.isNaN(p.equity));
}


// ============================================================
// Trade lifecycle — /api/options/paper-trades
// Maps backend states into normalized lifecycle buckets.
// ============================================================

export type LifecycleState =
  | "open" | "closed" | "assigned" | "expired"
  | "rolled" | "exercised" | "pending";


export interface LifecycleTrade {
  trade_id: number;
  underlying: string;
  strategy_name: string | null;
  contract: string | null;            // e.g. "170C 15 Jan 27"
  side: string | null;                // bought / sold
  state: LifecycleState;
  raw_status: string;
  opened_at: string | null;
  closed_at: string | null;
  premium_collected: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  days_open: number | null;
}


function mapState(raw: unknown): LifecycleState {
  const s = String(raw ?? "").toLowerCase().trim();
  if (s.includes("assign")) return "assigned";
  if (s.includes("expire")) return "expired";
  if (s.includes("roll"))   return "rolled";
  if (s.includes("exerc"))  return "exercised";
  if (s.includes("pend") || s.includes("submit") || s.includes("queue")) return "pending";
  if (s.includes("clos") || s.includes("settled") || s.includes("done")) return "closed";
  return "open";
}


export async function fetchLifecycleTrades(): Promise<LifecycleTrade[]> {
  const data = await safeFetch<{ trades?: Array<Record<string, unknown>> }>(
    "/api/options/paper-trades?limit=200",
  );
  const rows = data?.trades ?? [];
  return rows.map(r => {
    const opened = (r.opened_at as string | null)
      ?? (r.entry_ts as string | null)
      ?? (r.created_at as string | null)
      ?? null;
    const closed = (r.closed_at as string | null)
      ?? (r.exit_ts as string | null)
      ?? null;
    let daysOpen: number | null = null;
    if (opened) {
      const start = Date.parse(opened);
      const end = closed ? Date.parse(closed) : Date.now();
      if (!Number.isNaN(start) && !Number.isNaN(end)) {
        daysOpen = Math.max(0, Math.round((end - start) / 86_400_000));
      }
    }
    return {
      trade_id: Number(r.trade_id ?? r.id ?? 0),
      underlying: String(r.underlying ?? r.symbol ?? "—"),
      strategy_name: (r.strategy_name as string | null)
        ?? (r.strategy as string | null) ?? null,
      contract: (r.contract as string | null)
        ?? (r.option_symbol as string | null) ?? null,
      side: (r.side as string | null) ?? null,
      state: mapState(r.status ?? r.state ?? r.lifecycle),
      raw_status: String(r.status ?? r.state ?? "open"),
      opened_at: opened,
      closed_at: closed,
      premium_collected: asNum(r.premium_collected ?? r.premium ?? r.credit),
      realized_pnl: asNum(r.realized_pnl ?? r.realized),
      unrealized_pnl: asNum(r.unrealized_pnl ?? r.mark_pnl),
      days_open: daysOpen,
    };
  });
}


// ============================================================
// Health rail derivations from the position snapshot
// ============================================================

export interface HealthRailData {
  largestWinner: { symbol: string; pnl: number } | null;
  largestLoser:  { symbol: string; pnl: number } | null;
  largestPosition: { symbol: string; mv: number } | null;
  premiumToday: number | null;
  staleCount: number;
  totalOpen: number;
}


export function deriveHealthRail(positions: PositionRow[], lifecycle: LifecycleTrade[]): HealthRailData {
  const withPnl = positions.filter(p => p.unrealized_pnl != null);
  const sortedDesc = [...withPnl].sort((a, b) => (b.unrealized_pnl ?? 0) - (a.unrealized_pnl ?? 0));
  const winner = sortedDesc[0]?.unrealized_pnl != null && sortedDesc[0].unrealized_pnl > 0
    ? { symbol: sortedDesc[0].symbol, pnl: sortedDesc[0].unrealized_pnl }
    : null;
  const loser = sortedDesc[sortedDesc.length - 1]?.unrealized_pnl != null
    && (sortedDesc[sortedDesc.length - 1].unrealized_pnl ?? 0) < 0
    ? { symbol: sortedDesc[sortedDesc.length - 1].symbol, pnl: sortedDesc[sortedDesc.length - 1].unrealized_pnl ?? 0 }
    : null;

  const withMv = positions.filter(p => p.market_value != null);
  const sortedMv = [...withMv].sort((a, b) => (b.market_value ?? 0) - (a.market_value ?? 0));
  const largestPosition = sortedMv[0]?.market_value != null
    ? { symbol: sortedMv[0].symbol, mv: sortedMv[0].market_value ?? 0 }
    : null;

  const today = new Date(); today.setHours(0, 0, 0, 0);
  const todayMs = today.getTime();
  const premiumToday = lifecycle
    .filter(t => t.opened_at && Date.parse(t.opened_at) >= todayMs)
    .reduce((sum, t) => sum + (t.premium_collected ?? 0), 0) || null;

  return {
    largestWinner: winner,
    largestLoser: loser,
    largestPosition,
    premiumToday,
    staleCount: 0,
    totalOpen: positions.length,
  };
}


// ============================================================
// Provider seam — pluggable data providers (Phase 8 prep)
// Future-ready hooks for Polygon / Tradier / Firecrawl / Benzinga.
// All adapters MUST return a uniform shape so swap is transparent.
// ============================================================

export interface PriceProvider { name: string; fetchQuote(symbol: string): Promise<{ price: number } | null>; }
export interface NewsProvider  { name: string; fetchNews(symbol: string): Promise<Array<{ title: string; url: string; ts: string }>>; }
export interface CalendarProvider { name: string; fetchEarnings(window: number): Promise<Array<{ symbol: string; date: string; }>>; }


// Default providers are NOT registered. Wire concrete implementations
// (e.g. PolygonPriceProvider) later. Components should accept a
// provider via prop or read from a future `providers` context — never
// inline a vendor URL in a component.
export const PROVIDER_REGISTRY: {
  prices: PriceProvider | null;
  news:   NewsProvider | null;
  calendar: CalendarProvider | null;
} = {
  prices: null,
  news:   null,
  calendar: null,
};
