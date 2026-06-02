// Options Visibility — V2-native, read-only "are options alive?" surface.
//
// Single backend source: GET /api/options/pipeline-status. No trading,
// no paper-open, no strategy builder, no mutations — this surface only
// observes. Honest by contract: null/unknown render as "--", never
// fabricated. Visual template: pages/Observability.tsx.

import { ArthosPage } from '../chrome/ArthosChrome';
import { PageHeader } from '../components/ui/PageHeader';
import { SurfaceCard } from '../components/ui/SurfaceCard';
import {
  useOptionsVisibility,
  type OptionsPipelineStatus,
} from '../lib/optionsVisibility';

// ── tone → color (theme-aware via tokens + mid-tone amber) ──
type Tone = 'good' | 'warn' | 'bad' | 'muted';

const AMBER = 'oklch(0.70 0.14 75)';

function toneColor(tone: Tone): string {
  if (tone === 'good') return 'var(--brand)';
  if (tone === 'warn') return AMBER;
  if (tone === 'bad') return 'var(--destructive)';
  return 'var(--muted-foreground)';
}

const TONE_FOR: Record<string, Tone> = {
  active: 'good', fresh: 'good', healthy: 'good', ok: 'good',
  on: 'good', enabled: 'good', yes: 'good',
  starting: 'warn', degraded: 'warn', stale: 'warn', warning: 'warn',
  dormant: 'muted', unscheduled: 'warn',
  off: 'muted', disabled: 'muted', no: 'muted', unknown: 'muted',
  failed: 'bad', error: 'bad',
};

function StatusPill({ status, tone }: { status: string | null | undefined; tone?: Tone }) {
  const label = status ?? 'unknown';
  const t = tone ?? TONE_FOR[String(label).toLowerCase()] ?? 'muted';
  const color = toneColor(t);
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full"
      style={{
        fontSize: 11,
        fontWeight: 600,
        textTransform: 'capitalize',
        color,
        backgroundColor: `color-mix(in oklch, ${color} 14%, transparent)`,
        border: `1px solid color-mix(in oklch, ${color} 28%, transparent)`,
      }}
    >
      <span
        aria-hidden
        className="inline-block rounded-full"
        style={{ width: 6, height: 6, backgroundColor: color }}
      />
      {label}
    </span>
  );
}

// ── time helpers (honest "--" for null/invalid) ──
function relAge(iso: string | null): string {
  if (!iso) return '--';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '--';
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function absTime(iso: string | null): string {
  if (!iso) return '--';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '--';
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function fmtBool(v: boolean | null | undefined): string {
  if (v == null) return '--';
  return v ? 'on' : 'off';
}

// ── chain freshness: derive a status from snapshot age ──
function chainFreshness(iso: string | null): { label: string; tone: Tone } {
  if (!iso) return { label: 'no data', tone: 'muted' };
  const ageH = (Date.now() - new Date(iso).getTime()) / 3_600_000;
  if (Number.isNaN(ageH)) return { label: 'no data', tone: 'muted' };
  if (ageH <= 24) return { label: 'fresh', tone: 'good' };
  if (ageH <= 96) return { label: 'degraded', tone: 'warn' };
  return { label: 'stale', tone: 'warn' };
}

// ── small presentational helpers (mirror Observability) ──
function StatCard({
  label, value, sub, tone,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: Tone;
}) {
  return (
    <SurfaceCard variant="default" className="p-4">
      <p
        className="font-semibold uppercase mb-1.5"
        style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}
      >
        {label}
      </p>
      <p
        className="font-display ink-primary leading-none"
        style={{ fontSize: 22, color: tone ? toneColor(tone) : undefined }}
      >
        {value}
      </p>
      {sub != null && (
        <p className="ink-muted mt-1.5" style={{ fontSize: 12 }}>{sub}</p>
      )}
    </SurfaceCard>
  );
}

function SectionTitle({ n, title }: { n: string; title: string }) {
  return (
    <div className="flex items-baseline gap-3 mb-4 mt-10">
      <span className="font-mono ink-muted" style={{ fontSize: 12 }}>{n}</span>
      <h2 className="font-display ink-primary" style={{ fontSize: 22, lineHeight: 1.2 }}>
        {title}
      </h2>
    </div>
  );
}

function num(n: number | null | undefined): React.ReactNode {
  return n == null ? '--' : n.toLocaleString();
}

export function OptionsVisibility() {
  const { data, isLoading, isError, error, dataUpdatedAt } = useOptionsVisibility();

  return (
    <ArthosPage topBarEyebrow="Options">
      <PageHeader
        eyebrow="System"
        title={<>Options Diagnostics.</>}
        description="Is the options subsystem alive — provider, chain, candidates, engine status. Read-only; nothing here trades, opens, or executes."
      />

      {isLoading && (
        <SurfaceCard variant="muted" className="p-6">
          <p className="ink-muted" style={{ fontSize: 14 }}>Loading options snapshot…</p>
        </SurfaceCard>
      )}

      {isError && (
        <SurfaceCard variant="default" className="p-6">
          <p style={{ fontSize: 14, color: 'var(--destructive)', fontWeight: 600 }}>
            Could not load the options pipeline status.
          </p>
          <pre
            className="mt-2 whitespace-pre-wrap break-words"
            style={{ fontSize: 12, color: 'var(--muted-foreground)' }}
          >
            {String((error as Error)?.message ?? 'Unknown error')}
          </pre>
        </SurfaceCard>
      )}

      {data && <Body data={data} dataUpdatedAt={dataUpdatedAt} />}
    </ArthosPage>
  );
}

function Body({ data, dataUpdatedAt }: { data: OptionsPipelineStatus; dataUpdatedAt: number }) {
  const fresh = chainFreshness(data.options_chain_snapshot_max_ts);
  const cu = data.candidate_universe;
  const ingest = data.latest_ingest_run;

  return (
    <>
      {/* ── Engine state hero ── */}
      <SurfaceCard variant="highlight" className="mb-4">
        <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-5">
          <div>
            <p
              className="font-semibold uppercase mb-2"
              style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}
            >
              Options engine
            </p>
            <div className="flex items-baseline gap-3">
              <span
                className="font-display leading-none"
                style={{ fontSize: 32, color: toneColor(TONE_FOR[data.engine_state] ?? 'muted'), textTransform: 'capitalize' }}
              >
                {data.engine_state}
              </span>
              <StatusPill status={data.options_paper_only ? 'paper-only' : 'LIVE'} tone={data.options_paper_only ? 'good' : 'bad'} />
            </div>
            <p className="ink-muted mt-2" style={{ fontSize: 12.5, maxWidth: 560 }}>
              {data.engine_state_sentence}
            </p>
          </div>
          <div className="text-left sm:text-right">
            <p
              className="font-semibold uppercase mb-1.5"
              style={{ fontSize: 10, letterSpacing: '0.14em', color: 'var(--muted-foreground)' }}
            >
              Latest chain snapshot
            </p>
            <p className="font-display ink-primary leading-none" style={{ fontSize: 26 }}>
              {relAge(data.options_chain_snapshot_max_ts)}
            </p>
            <p className="ink-muted mt-1" style={{ fontSize: 12 }}>
              {absTime(data.options_chain_snapshot_max_ts)}
            </p>
            <p className="mt-2"><StatusPill status={fresh.label} tone={fresh.tone} /></p>
          </div>
        </div>
      </SurfaceCard>

      {/* ── 01. Options engine status ── */}
      <SectionTitle n="01" title="Engine status" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Provider"
          value={<span style={{ fontSize: 15 }}>{data.chain_provider ?? '--'}</span>}
          sub="options data source"
        />
        <StatCard
          label="Provider version"
          value={
            <span className="font-mono" style={{ fontSize: 13 }}>
              {data.chain_provider_version ?? '--'}
            </span>
          }
          sub="from latest snapshot"
        />
        <StatCard
          label="Latest snapshot"
          value={<span style={{ fontSize: 15 }}>{relAge(data.options_chain_snapshot_max_ts)}</span>}
          sub={absTime(data.options_chain_snapshot_max_ts)}
        />
        <StatCard
          label="Chain status"
          value={<StatusPill status={fresh.label} tone={fresh.tone} />}
          sub={`${num(data.options_chain_snapshot_count)} rows total`}
        />
        <StatCard
          label="Paper only"
          value={<StatusPill status={fmtBool(data.options_paper_only)} tone={data.options_paper_only ? 'good' : 'bad'} />}
          sub="live orders disabled"
        />
        <StatCard
          label="Shadow eval"
          value={<StatusPill status={fmtBool(data.options_shadow_eval_enabled)} />}
          sub="research persistence"
        />
        <StatCard
          label="Options enabled"
          value={<StatusPill status={fmtBool(data.options_enabled)} />}
          sub={`${num(data.scheduler_jobs_count)} scheduled jobs`}
        />
        <StatCard
          label="Features / candidates"
          value={<span style={{ fontSize: 15 }}>{num(data.options_feature_daily_count)} · {num(cu.total)}</span>}
          sub={`${num(data.options_shadow_decision_count)} shadow decisions`}
        />
      </div>

      {/* ── 02. Chain freshness ── */}
      <SectionTitle n="02" title="Chain freshness" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Latest ingest run"
          value={<span style={{ fontSize: 15 }}>{relAge(ingest?.started_at ?? null)}</span>}
          sub={absTime(ingest?.started_at ?? null)}
        />
        <StatCard
          label="Rows inserted"
          value={num(ingest?.rows_inserted)}
          tone={(ingest?.rows_inserted ?? 0) > 0 ? 'good' : 'muted'}
          sub={ingest?.classification ?? '--'}
        />
        <StatCard
          label="Rows filtered"
          value={num(ingest?.rows_filtered_out)}
          sub={`${num(ingest?.n_symbols_ok)} symbols ok`}
        />
        <StatCard
          label="Snapshot age"
          value={<span style={{ fontSize: 15 }}>{relAge(data.options_chain_snapshot_max_ts)}</span>}
          tone={fresh.tone}
          sub={fresh.label}
        />
      </div>

      {/* ── 03. Chain health (SPY/QQQ) ── */}
      <SectionTitle n="03" title="Chain health" />
      {data.chain_health.length === 0 ? (
        <SurfaceCard variant="muted" className="p-5">
          <p className="ink-muted" style={{ fontSize: 13.5 }}>No SPY/QQQ chain rows ingested yet.</p>
        </SurfaceCard>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {data.chain_health.map((c) => {
            const ok = c.rows > 0 && c.valid_bid_ask === c.rows;
            const partial = c.valid_bid_ask > 0 && c.valid_bid_ask < c.rows;
            return (
              <SurfaceCard key={c.symbol} variant="default" className="p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-display ink-primary" style={{ fontSize: 18 }}>{c.symbol}</span>
                  <StatusPill
                    status={ok ? 'bid>0 · ask>bid' : partial ? 'partial' : 'no valid quotes'}
                    tone={ok ? 'good' : partial ? 'warn' : 'muted'}
                  />
                </div>
                <div className="flex flex-wrap gap-x-6 gap-y-1" style={{ fontSize: 12.5 }}>
                  <span className="ink-muted">rows <span className="ink-primary">{num(c.rows)}</span></span>
                  <span className="ink-muted">valid bid/ask <span className="ink-primary">{num(c.valid_bid_ask)}</span></span>
                  <span className="ink-muted">latest <span className="ink-primary">{relAge(c.latest_snapshot_at)}</span></span>
                </div>
              </SurfaceCard>
            );
          })}
        </div>
      )}

      {/* ── 04. Candidate readiness ── */}
      <SectionTitle n="04" title="Candidate readiness" />
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Candidate universe" value={num(cu.total)} sub="emitted candidates" />
        <StatCard
          label="Engine-compatible"
          value={num(cu.engine_compatible)}
          tone={cu.engine_compatible > 0 ? 'good' : 'muted'}
          sub="defined-risk supported"
        />
        <StatCard
          label="Engine-incompatible"
          value={num(cu.engine_incompatible)}
          tone={cu.engine_incompatible > 0 ? 'warn' : 'good'}
          sub="structure not yet supported"
        />
      </div>
      {cu.by_structure.length > 0 && (
        <SurfaceCard variant="default" className="p-0 overflow-x-auto mt-3">
          <table className="w-full" style={{ fontSize: 12.5, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {['Structure', 'Candidates', 'Engine-compatible'].map((h) => (
                  <th
                    key={h}
                    className="text-left font-semibold uppercase ink-muted px-3 py-2.5 whitespace-nowrap"
                    style={{ fontSize: 10, letterSpacing: '0.1em' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cu.by_structure.map((s) => (
                <tr key={s.structure} style={{ borderBottom: '1px solid var(--border)' }}>
                  <td className="px-3 py-2.5 font-mono ink-primary">{s.structure}</td>
                  <td className="px-3 py-2.5 ink-primary tabular-nums">{num(s.count)}</td>
                  <td className="px-3 py-2.5">
                    <StatusPill status={s.engine_compatible ? 'yes' : 'no'} tone={s.engine_compatible ? 'good' : 'muted'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </SurfaceCard>
      )}

      {/* ── 05. Supported strategies ── */}
      <SectionTitle n="05" title="Engine-supported strategies" />
      <div className="flex flex-wrap gap-2">
        {data.supported_strategies.length === 0
          ? <p className="ink-muted" style={{ fontSize: 13 }}>--</p>
          : data.supported_strategies.map((s) => (
            <span
              key={s}
              className="font-mono inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
              style={{
                fontSize: 12.5,
                color: 'var(--brand)',
                backgroundColor: 'color-mix(in oklch, var(--brand) 12%, transparent)',
                border: '1px solid color-mix(in oklch, var(--brand) 26%, transparent)',
              }}
            >
              {s}
            </span>
          ))}
      </div>
      <p className="ink-muted mt-2" style={{ fontSize: 11.5 }}>
        Defined-risk only · paper · no order entry, no strategy builder on this surface.
      </p>

      {/* ── 06. Safety ── */}
      <SectionTitle n="06" title="Safety" />
      <div className="grid grid-cols-3 gap-3">
        <StatCard
          label="OPTIONS_ENABLED"
          value={<StatusPill status={fmtBool(data.options_enabled)} />}
          sub="read endpoints + ingest gate"
        />
        <StatCard
          label="OPTIONS_PAPER_ONLY"
          value={<StatusPill status={fmtBool(data.options_paper_only)} tone={data.options_paper_only ? 'good' : 'bad'} />}
          sub="live-order kill switch"
        />
        <StatCard
          label="OPTIONS_SHADOW_EVAL_ENABLED"
          value={<StatusPill status={fmtBool(data.options_shadow_eval_enabled)} />}
          sub="research persistence"
        />
      </div>

      {/* ── footer ── */}
      <p className="ink-muted mt-8" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
        Read-only surface — observes only, never trades or opens positions. Snapshot fetched {relAge(new Date(dataUpdatedAt).toISOString())} · auto-refreshes every 60s.
        Values shown as “--” are genuinely unavailable, never fabricated.
      </p>
    </>
  );
}
