// Phase G1 — Options Portfolio dashboard (read-only). Aggregates open
// options paper positions: capital at risk, max profit, open count, net
// greeks, concentration. Honest empty state (current live DB has 0 open
// positions). No execution / lifecycle / mutation.

import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import { useOptionsPortfolio, type OptionsPortfolio } from '../lib/optionsPortfolio';

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
    </ArthosPage>
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
