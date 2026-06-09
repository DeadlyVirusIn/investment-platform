// Phase G1 — Options Portfolio dashboard (read-only). Aggregates open
// options paper positions: capital at risk, max profit, open count, net
// greeks, concentration. Honest empty state (current live DB has 0 open
// positions). No execution / lifecycle / mutation.

import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import {
  useOptionsPortfolio, useOptionsAdvisory, useOptionsPortfolioDetail,
  type OptionsPortfolio, type AdvisoryPosition,
  type OptionsDetailPosition, type OptionsLeg,
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

const signedUsd = (n: number | null | undefined): string =>
  n == null ? '—'
    : `${n >= 0 ? '+' : '−'}$${Math.abs(n).toLocaleString(undefined, {
        minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const money2 = (n: number | null | undefined): string =>
  n == null ? '—' : `$${n.toFixed(2)}`;
const pct1 = (n: number | null | undefined): string =>
  n == null ? '—' : `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(1)}%`;
const pnlColor = (n: number | null | undefined): string =>
  n == null ? 'var(--ink-primary)'
    : n > 0 ? 'var(--brand)' : n < 0 ? 'var(--destructive)' : 'var(--ink-primary)';

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
        {l.bid != null && l.ask != null ? `${l.bid.toFixed(2)}/${l.ask.toFixed(2)}` : '—'}
        {l.open_interest != null ? ` · OI ${l.open_interest.toLocaleString()}` : ''}
        {l.spread != null ? ` · sp ${l.spread.toFixed(2)}` : ''}
        {l.quote_age_seconds != null ? ` · ${l.quote_age_seconds}s` : ''}
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
