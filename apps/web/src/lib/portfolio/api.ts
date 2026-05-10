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


export async function fetchCommandBar(): Promise<CommandBarData> {
  const [dash, exec, opsRisk, opsPerf] = await Promise.all([
    safeFetch<Record<string, unknown>>("/api/dashboard/summary"),
    safeFetch<Record<string, unknown>>("/api/paper/executed/summary"),
    safeFetch<Record<string, unknown>>("/api/options/risk-summary"),
    safeFetch<Record<string, unknown>>("/api/options/performance-summary"),
  ]);

  const dashPort = (dash?.portfolio as Record<string, unknown> | undefined) ?? {};
  const dashPnl = (dashPort.pnl as Record<string, unknown> | undefined)
    ?? (dash?.pnl as Record<string, unknown> | undefined)
    ?? {};
  const dashCash = (dashPort.cash as Record<string, unknown> | undefined)
    ?? (dash?.cash as Record<string, unknown> | undefined)
    ?? {};
  const dashRegime = (dash?.regime as Record<string, unknown> | undefined) ?? {};

  const opsPerfTotals = (opsPerf?.totals as Record<string, unknown> | undefined) ?? {};
  const opsRiskOpen = (opsRisk?.open_positions as Record<string, unknown> | undefined) ?? {};

  return {
    totalNav: asNum(dashPort.market_value)
      ?? asNum(dashPort.total_nav)
      ?? asNum(dash?.nav)
      ?? null,
    openPnl: asNum(dashPnl.unrealized_pnl) ?? asNum(dashPnl.open_pnl) ?? null,
    realizedPnl: asNum(dashPnl.realized_pnl) ?? null,
    totalReturnPct: asNum(dashPnl.total_return_pct)
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
    cashAvailable: asNum(dashCash.available)
      ?? asNum(dashCash.cash_available)
      ?? asNum(dashPort.cash)
      ?? null,
    posture: (dashPort.posture as string | undefined)
      ?? (dashRegime.market_trend as string | undefined)
      ?? null,
    freshAt: (dash?.as_of_date as string | undefined)
      ?? (dash?.generated_at as string | undefined)
      ?? null,
  };
}


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
