// Phase G1 — Options Portfolio dashboard (read-only). Aggregates open
// options paper positions: capital at risk, max profit, open count, net
// greeks, concentration. Honest empty state (current live DB has 0 open
// positions). No execution / lifecycle / mutation.

import { ArthosPage } from '../chrome/ArthosChrome';
import { PracticeTabs } from './components/PracticeTabs';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { useState } from 'react';
import {
  useOptionsPortfolio, useOptionsAdvisory, useOptionsPortfolioDetail,
  useOptionsTradeHistory, useOptionsClosedAnalytics,
  useOptionsPromotionAudit,
  type OptionsPortfolio, type AdvisoryPosition,
  type OptionsDetailPosition, type OptionsLeg,
  type OptionsTradeHistoryItem, type OptionsClosedAnalytics,
  type OptionsPromotionAudit,
} from '../lib/optionsPortfolio';

const AMBER = 'oklch(0.70 0.14 75)';

function usd(n: number | null | undefined): string {
  if (n == null) return '—';
  return `$${Math.round(n).toLocaleString()}`;
}

function greek(n: number | null | undefined): string {
  if (n == null) return '—';
  return (n >= 0 ? '+' : '') + n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <SurfaceCard variant="default" className="p-4">
      <p className="font-semibold uppercase mb-1.5" style={{
        fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>{label}</p>
      <p className="font-display leading-none tabular-nums" style={{ fontSize: 22, color: color || 'var(--ink-primary)' }}>
        {value}
      </p>
      {sub && <p className="ink-muted mt-1.5" style={{ fontSize: 11.5 }}>{sub}</p>}
    </SurfaceCard>
  );
}

export function OptionsPortfolio() {
  const { data, isLoading, isError } = useOptionsPortfolio();

  return (
    <ArthosPage topBarEyebrow="Options portfolio">
      <PageHeader
        eyebrow="Holdings"
        title={<>Options portfolio.</>}
        description="Open options positions — capital at risk, net greeks, and concentration. Read-only; nothing here trades or closes."
      />

      <PracticeTabs />

      {isLoading && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-muted" style={{ fontSize: 14 }}>Loading the options book…</p>
        </SurfaceCard>
      )}
      {isError && (
        <SurfaceCard variant="default" className="p-6">
          <p style={{ fontSize: 14, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load the options portfolio.
          </p>
        </SurfaceCard>
      )}

      {data && (data.status === 'empty' || data.open_count === 0) && (
        <SurfaceCard variant="muted" className="p-7">
          <p className="ink-primary" style={{ fontSize: 15 }}>No open options positions.</p>
          <p className="ink-muted mt-2" style={{ fontSize: 13 }}>
            When the paper engine opens a defined-risk options trade, its risk and
            greeks appear here.
          </p>
        </SurfaceCard>
      )}

      {data && data.status === 'live' && data.open_count > 0 && (
        <Dashboard data={data} />
      )}

      <AdvisorySection />
      <DetailSection />
      <TradeHistorySection />
      <ClosedAnalyticsSection />
      <PromotionAuditSection />
    </ArthosPage>
  );
}

function sigColor(level: string | undefined): string {
  switch (level) {
    case 'strong': case 'consider': return 'var(--brand)';
    case 'urgent': case 'high': return 'var(--destructive)';
    case 'manage': case 'warn': return AMBER;
    default: return 'var(--muted-foreground)';
  }
}

function AdvisorySection() {
  const { data } = useOptionsAdvisory();
  if (!data || data.status !== 'live' || data.open_count === 0) return null;
  return (
    <section className="mt-6">
      <p className="font-semibold uppercase mb-1" style={{
        fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>Lifecycle advisory</p>
      <p className="ink-fainter mb-3" style={{ fontSize: 12 }}>
        Advisory only — nothing here trades, closes, or rolls.
      </p>
      <div className="space-y-3">
        {data.positions.map((p) => <AdvisoryCard key={p.trade_id} p={p} />)}
      </div>
    </section>
  );
}

function AdvisoryCard({ p }: { p: AdvisoryPosition }) {
  const asOf = p.value_as_of
    ? new Date(p.value_as_of).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null;
  const Line = ({ s }: { s: { level: string; reason: string } | null }) =>
    s ? <p style={{ fontSize: 13, color: sigColor(s.level), marginTop: 4 }}>{s.reason}</p> : null;
  return (
    <SurfaceCard variant="default" className="p-5">
      <div className="flex items-baseline justify-between gap-3 mb-1">
        <span className="font-mono ink-primary" style={{ fontSize: 14 }}>{p.underlying}</span>
        <span className="ink-muted" style={{ fontSize: 12 }}>
          {p.strategy.replace(/_/g, ' ').toLowerCase()}{p.dte != null ? ` · ${p.dte}d` : ''}
        </span>
      </div>
      <Line s={p.take_profit} />
      <Line s={p.dte_management} />
      <Line s={p.loss_risk} />
      {p.assignment_risk && (
        <p style={{ fontSize: 13, color: sigColor(p.assignment_risk.level), marginTop: 4 }}>
          Assignment risk: {p.assignment_risk.reason}
        </p>
      )}
      {p.potential_roll_preview && (
        <p className="ink-muted" style={{ fontSize: 12.5, marginTop: 6 }}>
          Potential roll preview → {p.potential_roll_preview.to_expiry} ·
          {' '}strike {p.potential_roll_preview.short_strike}
          <span className="ink-fainter"> (informational only)</span>
        </p>
      )}
      <p className="ink-fainter" style={{ fontSize: 11, marginTop: 8 }}>
        {p.value_source ? `value: ${p.value_source}${asOf ? ` · ${asOf}` : ''}` : 'current value unavailable'}
      </p>
    </SurfaceCard>
  );
}

function Dashboard({ data }: { data: OptionsPortfolio }) {
  const asOf = data.greeks_as_of
    ? new Date(data.greeks_as_of).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null;
  const greekSub = data.greeks_source
    ? `${data.greeks_source} greeks${asOf ? ` · ${asOf}` : ''}`
    : 'greeks unavailable';

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <StatCard label="Capital at risk" value={usd(data.capital_at_risk)} sub="most you can lose" color={AMBER} />
        <StatCard label="Max profit" value={usd(data.max_profit)} sub="defined-risk" color="var(--brand)" />
        <StatCard label="Open positions" value={String(data.open_count)} />
        <StatCard label="Net delta" value={greek(data.net_delta)} sub={greekSub} />
        <StatCard label="Net theta" value={greek(data.net_theta)} sub="per day" />
        <StatCard label="Net vega" value={greek(data.net_vega)} sub="per 1 vol pt" />
      </div>

      {data.concentration.length > 0 && (
        <section>
          <p className="font-semibold uppercase mb-3" style={{
            fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
          }}>Concentration by underlying</p>
          <SurfaceCard variant="default" className="p-5">
            <ul className="space-y-3">
              {data.concentration.map((c) => (
                <li key={c.underlying}>
                  <div className="flex items-baseline justify-between gap-3 mb-1">
                    <span className="font-mono ink-primary" style={{ fontSize: 13 }}>{c.underlying}</span>
                    <span className="tabular-nums" style={{ fontSize: 12.5, color: c.high ? AMBER : 'var(--muted-foreground)' }}>
                      {Math.round(c.pct * 100)}% · {usd(c.capital_at_risk)}
                      {c.high && <span style={{ marginLeft: 6, fontWeight: 600 }}>⚠ High</span>}
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full" style={{ background: 'color-mix(in oklch, var(--foreground) 8%, transparent)' }}>
                    <div className="h-full rounded-full" style={{
                      width: `${Math.min(100, Math.round(c.pct * 100))}%`,
                      background: c.high ? AMBER : 'var(--brand)',
                    }} />
                  </div>
                </li>
              ))}
            </ul>
          </SurfaceCard>
        </section>
      )}

      <section>
        <p className="font-semibold uppercase mb-3" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
        }}>Open positions</p>
        <SurfaceCard variant="default" className="p-5">
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {data.positions.map((p) => (
              <li key={p.trade_id} className="py-3 grid grid-cols-[80px_1fr_auto] items-baseline gap-3">
                <span className="font-mono ink-primary" style={{ fontSize: 13 }}>{p.underlying}</span>
                <span className="ink-muted truncate" style={{ fontSize: 12.5 }}>
                  {p.strategy.replace(/_/g, ' ').toLowerCase()}{p.dte != null ? ` · ${p.dte}d` : ''}
                </span>
                <span className="tabular-nums ink-muted" style={{ fontSize: 12 }}>
                  risk {usd(p.capital_at_risk)} · Δ {greek(p.net_delta)}
                </span>
              </li>
            ))}
          </ul>
        </SurfaceCard>
      </section>
    </div>
  );
}

// ── Phase G2 — position detail / explainability ────────────────────────────

// P1.2B — the API serializes Postgres numeric columns as JSON strings
// (e.g. entry_credit_dollars: "10.0000") while the interfaces say number;
// "10.0000".toFixed crashed TradeHistoryRow. Coerce safely at the DISPLAY
// layer only: number/numeric-string -> number, anything else -> null ("—").
// Calculations are untouched; real negative values render normally.
const asNum = (v: unknown): number | null => {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
};

const signedUsd = (v: number | string | null | undefined): string => {
  const n = asNum(v);
  return n == null ? '—'
    : `${n >= 0 ? '+' : '−'}$${Math.abs(n).toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};
const money2 = (v: number | string | null | undefined): string => {
  const n = asNum(v);
  return n == null ? '—' : `$${n.toFixed(2)}`;
};
const pct1 = (v: number | string | null | undefined): string => {
  const n = asNum(v);
  return n == null ? '—' : `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(1)}%`;
};
const pnlColor = (v: number | string | null | undefined): string => {
  const n = asNum(v);
  return n == null ? 'var(--ink-primary)'
    : n > 0 ? 'var(--brand)' : n < 0 ? 'var(--destructive)' : 'var(--ink-primary)';
};

function DetailSection() {
  const { data, isLoading, isError } = useOptionsPortfolioDetail();
  if (isLoading) {
    return (
      <section className="mt-6">
        <SurfaceCard variant="muted" className="p-5">
          <p className="ink-muted" style={{ fontSize: 13 }}>Loading position detail…</p>
        </SurfaceCard>
      </section>
    );
  }
  if (isError) {
    return (
      <section className="mt-6">
        <SurfaceCard variant="default" className="p-5">
          <p style={{ fontSize: 13, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load position detail.
          </p>
        </SurfaceCard>
      </section>
    );
  }
  if (!data || data.status !== 'live' || data.positions.length === 0) return null;
  const pf = data.portfolio;

  return (
    <section className="mt-8">
      <p className="font-semibold uppercase mb-3" style={{
        fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>Position detail</p>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        <StatCard label="Cash" value={usd(pf.cash)} />
        <StatCard label="Reserved capital" value={usd(pf.reserved_capital)} sub="held at risk" />
        <StatCard label="Buying power" value={usd(pf.buying_power)} sub="free cash" />
        <StatCard label="Total risk / max loss" value={usd(pf.capital_at_risk)} color={AMBER} />
        <StatCard label="Unrealized P&L" value={signedUsd(pf.unrealized_pnl)} color={pnlColor(pf.unrealized_pnl)} />
        <StatCard label="Realized P&L" value={pf.realized_pnl != null ? signedUsd(pf.realized_pnl) : '—'} />
        <StatCard label="Max profit" value={usd(pf.max_profit)} color="var(--brand)" />
        <StatCard label="Open positions" value={String(pf.open_positions)} />
      </div>

      <div className="space-y-3">
        {data.positions.map((p) => <PositionDetailCard key={p.trade_id} p={p} />)}
      </div>
    </section>
  );
}

function Mini({ label, v, color }: { label: string; v: string; color?: string }) {
  return (
    <div className="min-w-0">
      <p className="ink-fainter" style={{ fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase' }}>{label}</p>
      <p className="tabular-nums" style={{ fontSize: 14, color: color ?? 'var(--ink-primary)' }}>{v}</p>
    </div>
  );
}

// P6D.34B — true quote freshness. effective_age_seconds is computed by the
// backend ((now − snapshot_at) + stored age); the stored quote_age_seconds is
// ingest-time (~0) and misleading on its own.
const fmtAge = (s: number | null | undefined): string => {
  if (s == null) return '—';
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${(s / 3600).toFixed(1)}h`;
  return `${(s / 86400).toFixed(1)}d`;
};

function FreshnessBanner({ p }: { p: OptionsDetailPosition }) {
  const age = p.max_effective_age_seconds;
  const asOf = p.quotes_as_of
    ? new Date(p.quotes_as_of).toLocaleString(undefined, {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null;
  if (age == null) {
    return (
      <p className="ink-fainter" style={{ fontSize: 11.5, marginBottom: 12 }}>
        Quote freshness unavailable.
      </p>
    );
  }
  // fresh < 15min · stale 15min–24h · old > 24h
  if (age < 900) {
    return (
      <p className="ink-fainter" style={{ fontSize: 11.5, marginBottom: 12 }}>
        Quotes as of {asOf ?? '—'} · Age: {fmtAge(age)} · fresh
      </p>
    );
  }
  const old = age >= 86400;
  return (
    <p style={{
      fontSize: 11.5, marginBottom: 12, fontWeight: 600,
      color: old ? 'var(--destructive)' : AMBER,
    }}>
      {old ? 'Quotes are from a previous session' : 'Quotes are stale'}
      {' — as of '}{asOf ?? '—'} · Age: {fmtAge(age)}.
      {' '}Marks and P&L reflect that time, not now.
    </p>
  );
}

function LegRow({ l }: { l: OptionsLeg }) {
  const exp = l.expiry
    ? new Date(l.expiry).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
  const kind = l.option_type === 'PUT' ? 'P' : l.option_type === 'CALL' ? 'C' : '';
  return (
    <li className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-1 items-baseline py-1.5"
      style={{ borderTop: '1px solid var(--border)' }}>
      <span style={{ fontSize: 12.5 }}>
        <span style={{ color: l.side === 'SELL' ? AMBER : 'var(--brand)', fontWeight: 600 }}>{l.side}</span>{' '}
        <span className="font-mono ink-primary">{l.strike}{kind}</span>
        <span className="ink-fainter"> ×{l.qty}</span>
      </span>
      <span className="tabular-nums ink-muted" style={{ fontSize: 12 }}>
        entry {money2(l.entry_fill_price)} · mid {money2(l.mid)}
      </span>
      <span className="tabular-nums ink-fainter" style={{ fontSize: 11.5 }}>
        {asNum(l.bid) != null && asNum(l.ask) != null
          ? `${asNum(l.bid)!.toFixed(2)}/${asNum(l.ask)!.toFixed(2)}` : '—'}
        {asNum(l.open_interest) != null ? ` · OI ${asNum(l.open_interest)!.toLocaleString()}` : ''}
        {asNum(l.spread) != null ? ` · sp ${asNum(l.spread)!.toFixed(2)}` : ''}
        {/* true age (effective), not the misleading ingest-time stored age */}
        {l.effective_age_seconds != null
          ? ` · ${fmtAge(l.effective_age_seconds)}`
          : l.quote_age_seconds != null ? ` · ${l.quote_age_seconds}s` : ''}
      </span>
      <span className="tabular-nums" style={{ fontSize: 12, color: pnlColor(l.leg_pnl), textAlign: 'right' }}>
        {signedUsd(l.leg_pnl)} · exp {exp}
      </span>
    </li>
  );
}

function PositionDetailCard({ p }: { p: OptionsDetailPosition }) {
  const opened = p.opened_at
    ? new Date(p.opened_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
  return (
    <SurfaceCard variant="default" className="p-5">
      <div className="flex items-baseline justify-between gap-3 mb-3 flex-wrap">
        <div className="flex items-baseline gap-2.5 flex-wrap min-w-0">
          <span className="font-mono ink-primary" style={{ fontSize: 15 }}>{p.underlying}</span>
          <span className="ink-muted" style={{ fontSize: 12.5 }}>{p.strategy.replace(/_/g, ' ').toLowerCase()}</span>
          <span className="ink-fainter" style={{ fontSize: 11.5 }}>
            · {p.status} · {p.dte != null ? `${p.dte} DTE` : '—'} · opened {opened}
          </span>
        </div>
        <span className="tabular-nums" style={{ fontSize: 14, color: pnlColor(p.unrealized_pnl), fontWeight: 600 }}>
          {signedUsd(p.unrealized_pnl)}{p.unrealized_pnl_pct != null ? ` · ${pct1(p.unrealized_pnl_pct)}` : ''}
        </span>
      </div>

      <FreshnessBanner p={p} />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-5 gap-y-3 mb-4">
        <Mini label="Entry credit" v={money2(p.entry_credit)} />
        <Mini label="Cost to close" v={money2(p.current_cost_to_close)} />
        <Mini label="Captured" v={pct1(p.captured_pct)} color={pnlColor(p.captured_pct)} />
        <Mini label="Reserved" v={usd(p.reserved_capital)} />
        <Mini label="Max profit" v={money2(p.max_profit)} color="var(--brand)" />
        <Mini label="Max loss" v={money2(p.max_loss)} color={AMBER} />
      </div>

      <div className="mb-4 p-3 rounded-lg" style={{ background: 'color-mix(in oklch, var(--foreground) 4%, transparent)' }}>
        <p style={{ fontSize: 13, color: 'var(--ink-primary)', fontWeight: 600 }}>
          Plan: {p.lifecycle.action}
          <span className="ink-muted" style={{ fontWeight: 400 }}> — {p.lifecycle.reason}</span>
        </p>
        <p className="ink-fainter" style={{ fontSize: 11.5, marginTop: 3 }}>
          Take profit at {p.lifecycle.tp_threshold_pct}% captured · manage at {p.lifecycle.dte_management_days} DTE
        </p>
      </div>

      {p.setup && (
        <div className="mb-4">
          <p className="ink-muted" style={{ fontSize: 13 }}>{p.setup.summary}</p>
          <p className="ink-fainter" style={{ fontSize: 12, marginTop: 3, lineHeight: 1.6 }}>
            {p.setup.max_profit} {p.setup.max_loss} {p.setup.profit_when} {p.setup.risk_when}
          </p>
        </div>
      )}

      <p className="font-semibold uppercase mb-1" style={{
        fontSize: 10, letterSpacing: '0.12em', color: 'var(--muted-foreground)',
      }}>Legs{!p.priced && <span className="ink-fainter"> · quotes unavailable</span>}</p>
      <ul>
        {p.legs.map((l) => <LegRow key={l.option_symbol} l={l} />)}
      </ul>
    </SurfaceCard>
  );
}

// ── Trade history (Phase 1) — read-only, every trade (open + closed) ────────

const shortDate = (s: string | null | undefined): string =>
  s ? new Date(s).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';

const shortHash = (h: string | null | undefined): string =>
  h ? `${h.slice(0, 8)}…` : '—';

function isOpenStatus(status: string): boolean {
  return ['PROPOSED', 'OPEN', 'EXPIRING'].includes(status.toUpperCase());
}

type HistoryFilter = 'all' | 'open' | 'closed';

function TradeHistorySection() {
  const [filter, setFilter] = useState<HistoryFilter>('all');
  const { data, isLoading, isError } = useOptionsTradeHistory(
    filter === 'all' ? undefined : { status: filter },
  );
  const trades = data?.trades ?? [];

  return (
    <section className="mt-8">
      <div className="flex items-baseline justify-between gap-3 mb-1 flex-wrap">
        <p className="font-semibold uppercase" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
        }}>Trade history</p>
        <div className="flex gap-1" role="group" aria-label="Filter trades by status">
          {(['all', 'open', 'closed'] as HistoryFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className="rounded-md"
              style={{
                fontSize: 11, padding: '3px 10px',
                textTransform: 'capitalize',
                color: filter === f ? 'var(--ink-primary)' : 'var(--muted-foreground)',
                background: filter === f
                  ? 'color-mix(in oklch, var(--foreground) 8%, transparent)'
                  : 'transparent',
                fontWeight: filter === f ? 600 : 400,
              }}
            >{f}</button>
          ))}
        </div>
      </div>
      <p className="ink-fainter mb-3" style={{ fontSize: 12 }}>
        Every options paper trade, open and closed. Read-only — nothing here trades or closes.
      </p>

      {isLoading && (
        <SurfaceCard variant="muted" className="p-5">
          <p className="ink-muted" style={{ fontSize: 13 }}>Loading trade history…</p>
        </SurfaceCard>
      )}
      {isError && (
        <SurfaceCard variant="default" className="p-5">
          <p style={{ fontSize: 13, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load trade history.
          </p>
        </SurfaceCard>
      )}
      {!isLoading && !isError && trades.length === 0 && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-primary" style={{ fontSize: 14 }}>
            {filter === 'all' ? 'No options paper trades yet.'
              : `No ${filter} options paper trades.`}
          </p>
          <p className="ink-muted mt-2" style={{ fontSize: 12.5 }}>
            When the paper engine opens or closes a defined-risk options trade, it appears here.
          </p>
        </SurfaceCard>
      )}

      {!isLoading && !isError && trades.length > 0 && (
        <SurfaceCard variant="default" className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr className="ink-fainter" style={{ textAlign: 'left' }}>
                  {['ID', 'Status', 'Underlying', 'Strategy', 'Opened', 'Closed',
                    'Entry credit', 'Realized P&L', 'Exit reason', 'Proposal'].map((h, i) => (
                    <th key={h} style={{
                      padding: '10px 12px', fontWeight: 600, fontSize: 10,
                      letterSpacing: '0.08em', textTransform: 'uppercase',
                      whiteSpace: 'nowrap',
                      textAlign: (i >= 6 && i <= 7) ? 'right' : 'left',
                      borderBottom: '1px solid var(--border)',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.map((t) => <TradeHistoryRow key={t.id} t={t} />)}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      )}
    </section>
  );
}

function TradeHistoryRow({ t }: { t: OptionsTradeHistoryItem }) {
  const open = isOpenStatus(t.status);
  return (
    <tr style={{ borderTop: '1px solid var(--border)' }}>
      <td className="font-mono ink-muted" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
        #{t.id}
      </td>
      <td style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
        {open ? (
          <span style={{
            fontSize: 10.5, fontWeight: 600, padding: '2px 7px', borderRadius: 5,
            color: 'var(--brand)',
            background: 'color-mix(in oklch, var(--brand) 14%, transparent)',
          }} title="Open — see Position detail above">open</span>
        ) : (
          <span className="ink-muted" style={{ fontSize: 11.5 }}>
            {t.status.toLowerCase()}
          </span>
        )}
      </td>
      <td className="font-mono ink-primary" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
        {t.underlying}
      </td>
      <td className="ink-muted" style={{ padding: '9px 12px' }}>
        {t.strategy_name.replace(/_/g, ' ').toLowerCase()}
      </td>
      <td className="ink-muted tabular-nums" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
        {shortDate(t.opened_at)}
      </td>
      <td className="ink-muted tabular-nums" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
        {shortDate(t.closed_at)}
      </td>
      <td className="tabular-nums" style={{ padding: '9px 12px', textAlign: 'right', whiteSpace: 'nowrap' }}>
        {money2(t.entry_credit_dollars)}
      </td>
      <td className="tabular-nums" style={{
        padding: '9px 12px', textAlign: 'right', whiteSpace: 'nowrap',
        color: pnlColor(t.realized_pnl_dollars), fontWeight: 600,
      }}>
        {open ? '—' : signedUsd(t.realized_pnl_dollars)}
      </td>
      <td className="ink-muted" style={{ padding: '9px 12px' }}>
        {t.release_reason ?? '—'}
      </td>
      <td className="font-mono ink-fainter" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}
        title={t.proposal_hash ?? undefined}>
        {shortHash(t.proposal_hash)}
      </td>
    </tr>
  );
}

// ── Closed-trade analytics (Phase 2) — read-only, display-only ─────────────

const pctRate = (v: number | string | null | undefined): string => {
  const n = asNum(v);
  return n == null ? '—' : `${(n * 100).toFixed(1)}%`;
};
const factor = (v: number | string | null | undefined): string => {
  const n = asNum(v);
  return n == null ? '—' : n.toFixed(2);
};

function ClosedAnalyticsSection() {
  const { data, isLoading, isError } = useOptionsClosedAnalytics();

  return (
    <section className="mt-8">
      <p className="font-semibold uppercase mb-1" style={{
        fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>Closed-trade analytics</p>
      <p className="ink-fainter mb-3" style={{ fontSize: 12 }}>
        Aggregate over closed and released options trades — win/loss, realized
        P&amp;L, expectancy, and profit factor. Read-only.
      </p>

      {isLoading && (
        <SurfaceCard variant="muted" className="p-5">
          <p className="ink-muted" style={{ fontSize: 13 }}>Loading closed-trade analytics…</p>
        </SurfaceCard>
      )}
      {isError && (
        <SurfaceCard variant="default" className="p-5">
          <p style={{ fontSize: 13, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load closed-trade analytics.
          </p>
        </SurfaceCard>
      )}
      {!isLoading && !isError && data && (data.status === 'empty' || data.total_closed === 0) && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-primary" style={{ fontSize: 14 }}>
            No closed options trades yet — analytics populate when the first canary trade closes.
          </p>
        </SurfaceCard>
      )}

      {!isLoading && !isError && data && data.status === 'live' && data.total_closed > 0 && (
        <ClosedAnalyticsBody a={data} />
      )}
    </section>
  );
}

function ClosedAnalyticsBody({ a }: { a: OptionsClosedAnalytics }) {
  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-3">
        <StatCard label="Total closed" value={String(a.total_closed)} />
        <StatCard label="Win rate" value={pctRate(a.win_rate)}
          sub={`${a.wins}W · ${a.losses}L${a.breakeven ? ` · ${a.breakeven}BE` : ''}`} />
        <StatCard label="Wins" value={String(a.wins)} color="var(--brand)" />
        <StatCard label="Losses" value={String(a.losses)} color="var(--destructive)" />
        <StatCard label="Realized P&L" value={signedUsd(a.total_realized)}
          color={pnlColor(a.total_realized)} />
        <StatCard label="Expectancy" value={a.expectancy != null ? signedUsd(a.expectancy) : '—'}
          sub="per trade" color={pnlColor(a.expectancy)} />
        <StatCard label="Profit factor" value={factor(a.profit_factor)}
          sub={a.profit_factor == null ? 'no losses' : 'gross win / loss'} />
        <StatCard label="Avg winner / loser"
          value={`${a.avg_winner != null ? signedUsd(a.avg_winner) : '—'} / ${a.avg_loser != null ? signedUsd(a.avg_loser) : '—'}`} />
      </div>

      {a.by_strategy.length > 0 && (
        <SurfaceCard variant="default" className="p-0 mb-3">
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr className="ink-fainter" style={{ textAlign: 'left' }}>
                  {['Strategy', 'Trades', 'Wins', 'Losses', 'Win rate', 'Realized'].map((h, i) => (
                    <th key={h} style={{
                      padding: '10px 12px', fontWeight: 600, fontSize: 10,
                      letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap',
                      textAlign: i >= 1 ? 'right' : 'left',
                      borderBottom: '1px solid var(--border)',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.by_strategy.map((s) => (
                  <tr key={s.strategy} style={{ borderTop: '1px solid var(--border)' }}>
                    <td className="ink-primary" style={{ padding: '9px 12px' }}>
                      {s.strategy.replace(/_/g, ' ').toLowerCase()}
                    </td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{s.count}</td>
                    <td className="tabular-nums" style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--brand)' }}>{s.wins}</td>
                    <td className="tabular-nums" style={{ padding: '9px 12px', textAlign: 'right', color: 'var(--destructive)' }}>{s.losses}</td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{pctRate(s.win_rate)}</td>
                    <td className="tabular-nums" style={{ padding: '9px 12px', textAlign: 'right', color: pnlColor(s.realized), fontWeight: 600 }}>{signedUsd(s.realized)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      )}

      {a.by_exit_reason.length > 0 && (
        <SurfaceCard variant="default" className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr className="ink-fainter" style={{ textAlign: 'left' }}>
                  {['Exit reason', 'Trades', 'Realized'].map((h, i) => (
                    <th key={h} style={{
                      padding: '10px 12px', fontWeight: 600, fontSize: 10,
                      letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap',
                      textAlign: i >= 1 ? 'right' : 'left',
                      borderBottom: '1px solid var(--border)',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.by_exit_reason.map((r) => (
                  <tr key={r.exit_reason} style={{ borderTop: '1px solid var(--border)' }}>
                    <td className="ink-muted" style={{ padding: '9px 12px' }}>{r.exit_reason}</td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{r.count}</td>
                    <td className="tabular-nums" style={{ padding: '9px 12px', textAlign: 'right', color: pnlColor(r.realized), fontWeight: 600 }}>{signedUsd(r.realized)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      )}
    </>
  );
}

// ── Promotion/rejection audit (Phase 3) — read-only, display-only ───────────

const REASON_LABELS: Record<string, string> = {
  wrong_underlying: 'Outside canary universe',
  wrong_strategy: 'Wrong strategy',
  no_legs: 'Legs not materialized',
  dte_out_of_range: 'DTE out of range',
  confidence_below_gate: 'Confidence below gate',
  unfillable_leg: 'Unfillable leg',
  eligible: 'Eligible',
};

const humanizeReason = (r: string): string =>
  REASON_LABELS[r] ?? r.replace(/_/g, ' ');

const conf2 = (v: number | string | null | undefined): string => {
  const n = asNum(v);
  return n == null ? '—' : n.toFixed(2);
};

function PromotionAuditSection() {
  const { data, isLoading, isError } = useOptionsPromotionAudit();

  return (
    <section className="mt-8">
      <p className="font-semibold uppercase mb-1" style={{
        fontSize: 11, letterSpacing: '0.14em', color: 'var(--muted-foreground)',
      }}>Promotion audit</p>
      <p className="ink-fainter mb-3" style={{ fontSize: 12 }}>
        Why option candidates were promoted or rejected, per run — derived
        from the same gates the canary selector uses. Read-only.
      </p>

      {isLoading && (
        <SurfaceCard variant="muted" className="p-5">
          <p className="ink-muted" style={{ fontSize: 13 }}>Loading promotion audit…</p>
        </SurfaceCard>
      )}
      {isError && (
        <SurfaceCard variant="default" className="p-5">
          <p style={{ fontSize: 13, color: 'var(--destructive)', fontWeight: 600 }}>
            Couldn't load the promotion audit.
          </p>
        </SurfaceCard>
      )}
      {!isLoading && !isError && data && data.status === 'empty' && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-primary" style={{ fontSize: 14 }}>
            No promotion runs or candidates in the window yet.
          </p>
          <p className="ink-muted mt-2" style={{ fontSize: 12.5 }}>
            When the canary promotion cycle runs, each candidate's gate
            outcome appears here.
          </p>
        </SurfaceCard>
      )}

      {!isLoading && !isError && data && data.status === 'live' && (
        <PromotionAuditBody a={data} />
      )}
    </section>
  );
}

function PromotionAuditBody({ a }: { a: OptionsPromotionAudit }) {
  const reasons = Object.entries(a.reason_counts)
    .filter(([r]) => r !== 'eligible')
    .sort((x, y) => y[1] - x[1]);

  return (
    <>
      {/* (b) current rejection pattern — reason summary chips */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <span style={{
          fontSize: 11.5, fontWeight: 600, padding: '3px 10px', borderRadius: 6,
          color: 'var(--brand)',
          background: 'color-mix(in oklch, var(--brand) 14%, transparent)',
        }}>
          Eligible {a.eligible_count}
        </span>
        {reasons.map(([reason, count]) => (
          <span key={reason} style={{
            fontSize: 11.5, padding: '3px 10px', borderRadius: 6,
            color: 'var(--muted-foreground)',
            background: 'color-mix(in oklch, var(--foreground) 6%, transparent)',
          }}>
            {humanizeReason(reason)} <span className="tabular-nums" style={{ fontWeight: 600 }}>{count}</span>
          </span>
        ))}
        {a.gates && (
          <span className="ink-fainter" style={{ fontSize: 11 }}>
            gates: {a.gates.universe} · {a.gates.strategy.replace(/_/g, ' ').toLowerCase()} ·
            {' '}{a.gates.min_dte}–{a.gates.max_dte} DTE · conf ≥ {conf2(a.gates.min_confidence)} ·
            {' '}last {a.gates.days}d
          </span>
        )}
      </div>

      {/* (a) funnel by run_date */}
      {a.runs.length > 0 && (
        <SurfaceCard variant="default" className="p-0 mb-3">
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr className="ink-fainter" style={{ textAlign: 'left' }}>
                  {['Run date', 'Candidates', 'Promoted', 'Filled',
                    'Slot full', 'Capital cap', 'Duplicate', 'Other'].map((h, i) => (
                    <th key={h} style={{
                      padding: '10px 12px', fontWeight: 600, fontSize: 10,
                      letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap',
                      textAlign: i >= 1 ? 'right' : 'left',
                      borderBottom: '1px solid var(--border)',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.runs.map((r) => (
                  <tr key={r.run_date} style={{ borderTop: '1px solid var(--border)' }}>
                    <td className="tabular-nums ink-primary" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                      {shortDate(r.run_date)}
                    </td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{r.candidates_total}</td>
                    <td className="tabular-nums" style={{
                      padding: '9px 12px', textAlign: 'right', fontWeight: 600,
                      color: r.promoted > 0 ? 'var(--brand)' : 'var(--muted-foreground)',
                    }}>{r.promoted}</td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{r.filled}</td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{r.skip_slot_full}</td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{r.skip_over_capital_cap}</td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{r.skip_proposal_duplicate}</td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>{r.skip_other}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      )}

      {/* (c) rejected candidates */}
      {a.rejected.length > 0 && (
        <SurfaceCard variant="default" className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr className="ink-fainter" style={{ textAlign: 'left' }}>
                  {['Run date', 'Underlying', 'Strategy', 'Confidence', 'DTE', 'Reason'].map((h, i) => (
                    <th key={h} style={{
                      padding: '10px 12px', fontWeight: 600, fontSize: 10,
                      letterSpacing: '0.08em', textTransform: 'uppercase', whiteSpace: 'nowrap',
                      textAlign: (i === 3 || i === 4) ? 'right' : 'left',
                      borderBottom: '1px solid var(--border)',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {a.rejected.map((c) => (
                  <tr key={c.candidate_id} style={{ borderTop: '1px solid var(--border)' }}>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                      {shortDate(c.run_date)}
                    </td>
                    <td className="font-mono ink-primary" style={{ padding: '9px 12px', whiteSpace: 'nowrap' }}>
                      {c.underlying}
                    </td>
                    <td className="ink-muted" style={{ padding: '9px 12px' }}>
                      {c.strategy.replace(/_/g, ' ').toLowerCase()}
                    </td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>
                      {conf2(c.confidence)}
                    </td>
                    <td className="tabular-nums ink-muted" style={{ padding: '9px 12px', textAlign: 'right' }}>
                      {c.dte ?? '—'}
                    </td>
                    <td style={{ padding: '9px 12px', color: AMBER }}>
                      {humanizeReason(c.reason)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SurfaceCard>
      )}
    </>
  );
}
