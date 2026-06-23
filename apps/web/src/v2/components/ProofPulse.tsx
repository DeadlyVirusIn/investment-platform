// ProofPulse — Sprint 1 "Proof & Pulse".
//
// PROOF: ArthOS's honest paper track record, surfaced high on Discover so a
//   first-time tester sees real, auditable practice results immediately —
//   realized P/L, return %, closed/open counts, and how many ideas ArthOS has
//   tracked to resolution. Paper-only framing, plain English, no return promise.
// PULSE: a one-tap beta-feedback row ("Was this useful?", "Come back tomorrow?",
//   "What confused you?") wired to the EXISTING /feedback/signal endpoint.
//
// Honesty discipline: every number comes from a read-only endpoint of REAL
// stored paper data (canonical portfolio + closed-recommendations). A win-rate
// only shows once enough closed outcomes exist (WIN_RATE_MIN_CLOSED); below
// that we show the count alone and say accuracy isn't published yet. Never
// fabricates, never implies real money or beats-the-market.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { SurfaceCard } from './ui/SurfaceCard';
import { useSession } from '../state/SessionContext';
import { sendSignal, type SignalType } from '@/lib/feedback';
import {
  useCanonicalStockPortfolio,
  useClosedRecommendations,
} from '@/lib/operator/hooks';

// Win-rate publishes only once this many real closed outcomes exist — mirrors
// the existing TrustBanner gate so we never show a 2-trade "100% win rate".
const WIN_RATE_MIN_CLOSED = 10;

function money(n: number): string {
  const sign = n >= 0 ? '+' : '−';
  return `${sign}$${Math.abs(n).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function pct(n: number): string {
  return `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(2)}%`;
}

function shortDate(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isFinite(d.getTime())
    ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : null;
}

export function ProofPulse() {
  const { authenticated } = useSession();
  const { data: book } = useCanonicalStockPortfolio();
  const { data: closed } = useClosedRecommendations(book?.portfolio_id ?? null);

  // Signed-in only — signed-out visitors get the reviewer-facing ReviewerProof.
  if (!authenticated) return null;

  const realized = book?.realized_pnl ?? null;
  const ret = book?.total_return_pct ?? null;
  const openN = book?.open_positions_count ?? null;
  const asOf = shortDate(book?.as_of);
  const positive = (realized ?? 0) >= 0;

  // Closed-outcome stats (real, paper, rec-attributed). Win-rate gated.
  const items = closed?.items ?? [];
  const closedN = closed?.count ?? items.length;
  const scored = items.filter((i) => i.realized_pnl != null);
  const wins = scored.filter((i) => (i.realized_pnl ?? 0) > 0).length;
  const showWinRate = scored.length >= WIN_RATE_MIN_CLOSED;
  const winRate = showWinRate ? Math.round((wins / scored.length) * 100) : null;

  return (
    <SurfaceCard variant="highlight" className="p-5 mb-8">
      <div className="flex items-center justify-between gap-3 mb-1">
        <p className="font-semibold uppercase" style={{
          fontSize: 11, letterSpacing: '0.14em', color: 'var(--brand)',
        }}>Practice portfolio</p>
        {asOf && (
          <span className="ink-fainter tabular-nums" style={{ fontSize: 11 }}>
            as of {asOf}
          </span>
        )}
      </div>

      <p className="ink-muted" style={{ fontSize: 12.5, lineHeight: 1.5, marginBottom: 14 }}>
        Real paper trades in ArthOS's <strong>practice portfolio — no real money at stake.</strong> Every
        idea is tracked to the end and shown here, wins and losses.
      </p>

      {/* Metric row — realized P/L, return %, closed, open */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <Metric
          label="Realized (paper)"
          value={realized != null && closedN > 0 ? money(realized) : '—'}
          tone={realized != null && closedN > 0 ? (positive ? 'pos' : 'neg') : 'muted'}
        />
        <Metric
          label="Total return"
          value={ret != null ? pct(ret) : '—'}
          tone={ret != null ? (ret >= 0 ? 'pos' : 'neg') : 'muted'}
        />
        <Metric label="Ideas closed" value={closedN != null ? String(closedN) : '—'} />
        <Metric label="Open now" value={openN != null ? String(openN) : '—'} />
      </div>

      {/* Outcome-learning visibility */}
      <p className="ink-fainter" style={{ fontSize: 11.5, lineHeight: 1.5, marginBottom: 14 }}>
        {closedN > 0
          ? <>ArthOS tracks what happens after every idea — <strong>{closedN}</strong> closed and scored so far.{' '}
              {winRate != null
                ? <>{winRate}% finished green (paper).</>
                : <>Accuracy publishes once {WIN_RATE_MIN_CLOSED}+ ideas have closed.</>}
            </>
          : <>ArthOS tracks every idea to resolution — outcomes publish as they close.</>}
        {' '}Not financial advice; past paper results don't predict real returns.
      </p>

      <div className="mb-4">
        <Link to="/v2/arth" style={{ fontSize: 12.5, color: 'var(--brand)', fontWeight: 600 }}>
          See the full record →
        </Link>
      </div>

      <Pulse />
    </SurfaceCard>
  );
}

function Metric({ label, value, tone = 'default' }: {
  label: string; value: string; tone?: 'pos' | 'neg' | 'muted' | 'default';
}) {
  const color = tone === 'pos' ? 'var(--brand)'
    : tone === 'neg' ? 'oklch(0.58 0.15 28)'
      : tone === 'muted' ? 'var(--muted-foreground)' : 'var(--foreground)';
  return (
    <div>
      <p className="font-semibold uppercase" style={{
        fontSize: 9.5, letterSpacing: '0.1em', color: 'var(--muted-foreground)', marginBottom: 2,
      }}>{label}</p>
      <p className="tabular-nums" style={{ fontSize: 18, fontWeight: 600, color, lineHeight: 1.1 }}>
        {value}
      </p>
    </div>
  );
}

// Beta pulse — one-tap signals to the existing /feedback/signal endpoint.
function Pulse() {
  const [acked, setAcked] = useState<Set<string>>(new Set());
  const [confused, setConfused] = useState('');
  const [textSent, setTextSent] = useState(false);

  function fire(signal: SignalType, value?: string) {
    sendSignal('discover', signal, value).catch(() => {});
    setAcked((s) => new Set(s).add(signal));
  }

  const usefulAcked = acked.has('trust_useful') || acked.has('trust_not_useful');
  const returnAcked = acked.has('would_use_again') || acked.has('would_not_use_again');

  return (
    <div className="pt-4" style={{ borderTop: '1px solid var(--border)' }}>
      <p className="font-semibold uppercase" style={{
        fontSize: 10, letterSpacing: '0.12em', color: 'var(--muted-foreground)', marginBottom: 10,
      }}>Beta — 10 seconds of feedback?</p>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 mb-3">
        <PulseRow label="Was this useful?" acked={usefulAcked}>
          <Chip onClick={() => fire('trust_useful')}>👍 Yes</Chip>
          <Chip onClick={() => fire('trust_not_useful')}>👎 Not really</Chip>
        </PulseRow>
        <PulseRow label="Come back tomorrow?" acked={returnAcked}>
          <Chip onClick={() => fire('would_use_again')}>Yes</Chip>
          <Chip onClick={() => fire('would_not_use_again')}>Unlikely</Chip>
        </PulseRow>
      </div>

      {textSent ? (
        <p className="ink-muted" style={{ fontSize: 12 }}>Thanks — noted. 🙏</p>
      ) : (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={confused}
            onChange={(e) => setConfused(e.target.value)}
            placeholder="What confused you? (optional)"
            className="flex-1 px-3 py-2 rounded-md"
            style={{
              fontSize: 12.5, border: '1px solid var(--border)',
              backgroundColor: 'var(--background)', color: 'var(--foreground)',
            }}
          />
          <button
            type="button"
            onClick={() => { if (confused.trim()) { fire('feedback_text', confused.trim()); setTextSent(true); } }}
            className="shrink-0 px-3 py-2 rounded-md"
            style={{
              fontSize: 12.5, fontWeight: 600,
              backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)',
            }}
          >Send</button>
        </div>
      )}
    </div>
  );
}

function PulseRow({ label, acked, children }: {
  label: string; acked: boolean; children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="ink-muted" style={{ fontSize: 12.5 }}>{label}</span>
      {acked
        ? <span style={{ fontSize: 12, color: 'var(--brand)', fontWeight: 600 }}>✓ thanks</span>
        : <span className="flex items-center gap-1.5">{children}</span>}
    </div>
  );
}

function Chip({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className="px-2.5 py-1 rounded-full"
      style={{
        fontSize: 12, fontWeight: 500,
        border: '1px solid var(--border)', backgroundColor: 'var(--card)',
        color: 'var(--foreground)',
      }}>
      {children}
    </button>
  );
}
