// ReviewerProof — Sprint 2 "Reviewer Proof".
//
// A logged-OUT-only proof surface for investors / Innovation Fund reviewers /
// curious visitors, so they can judge ArthOS's honest paper record, safety
// posture, and "show-the-working" differentiation WITHOUT signing up.
//
// Renders only when signed out (the canonical endpoint returns the curated
// "Replay Recovery" demo book to anonymous callers; once signed in, the
// user's own book + ProofPulse take over). Every number is real, read-only,
// and clearly labelled paper-only. No returns promise, no beat-the-market,
// no win-rate until the sample-size gate is met.

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { SurfaceCard } from './ui/SurfaceCard';
import { useSession } from '../state/SessionContext';
import {
  useCanonicalStockPortfolio,
  useClosedRecommendations,
  useTodaysRecommendations,
} from '@/lib/operator/hooks';

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

export function ReviewerProof() {
  const { authenticated, loading } = useSession();
  const [showHow, setShowHow] = useState(false);
  const { data: book } = useCanonicalStockPortfolio();
  const { data: closed } = useClosedRecommendations(book?.portfolio_id ?? null);
  const { data: recsData } = useTodaysRecommendations();

  // Signed-out only — signed-in users get the personal ProofPulse instead.
  if (loading || authenticated) return null;

  const realized = book?.realized_pnl ?? null;
  const ret = book?.total_return_pct ?? null;
  const openN = book?.open_positions_count ?? null;
  const asOf = shortDate(book?.as_of);
  const closedN = closed?.count ?? 0;
  const scored = (closed?.items ?? []).filter((i) => i.realized_pnl != null);
  const winRate = scored.length >= WIN_RATE_MIN_CLOSED
    ? Math.round((scored.filter((i) => (i.realized_pnl ?? 0) > 0).length / scored.length) * 100)
    : null;

  // Latest idea date = daily-refresh signal (the engine, not the book snapshot).
  const recs = recsData?.recommendations ?? [];
  const latestIdea = shortDate(
    recs.map((r) => r.generated_at).filter(Boolean).sort().slice(-1)[0] ?? null,
  );
  const heroSymbol = recs.find((r) => (r.adjusted_action ?? r.action) === 'Buy')?.symbol
    ?? recs[0]?.symbol ?? null;

  return (
    <SurfaceCard variant="highlight" className="p-6 mb-8">
      <p className="font-semibold uppercase" style={{
        fontSize: 11, letterSpacing: '0.14em', color: 'var(--brand)', marginBottom: 6,
      }}>The honest record</p>

      <p className="ink-primary" style={{ fontSize: 15, lineHeight: 1.55, marginBottom: 6 }}>
        Today's idea is at the top of this page. ArthOS <strong>tracks every idea it makes to
        the end on paper</strong> — so here's the record so far. It's the history of how past
        ideas resolved, <strong>not a prediction of today's call</strong>.
      </p>
      <p className="ink-muted" style={{ fontSize: 12.5, lineHeight: 1.5, marginBottom: 16 }}>
        Paper-only — practice money, <strong>not a live brokerage account</strong>. Not financial
        advice. Past paper results don't predict future real returns.
      </p>

      {/* Demo record metrics */}
      <div className="flex items-center justify-between gap-3 mb-2">
        <p className="font-semibold uppercase" style={{
          fontSize: 10, letterSpacing: '0.1em', color: 'var(--muted-foreground)',
        }}>Recovered paper demo record</p>
        {asOf && <span className="ink-fainter tabular-nums" style={{ fontSize: 11 }}>as of {asOf}</span>}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
        <Metric label="Realized (paper)" value={realized != null ? money(realized) : '—'}
          tone={realized != null ? (realized >= 0 ? 'pos' : 'neg') : 'muted'} />
        <Metric label="Total return" value={ret != null ? pct(ret) : '—'}
          tone={ret != null ? (ret >= 0 ? 'pos' : 'neg') : 'muted'} />
        <Metric label="Ideas closed" value={String(closedN)} />
        <Metric label="Open now" value={openN != null ? String(openN) : '—'} />
      </div>
      <p className="ink-fainter" style={{ fontSize: 11.5, lineHeight: 1.5, marginBottom: 18 }}>
        {winRate != null
          ? <>{winRate}% of closed ideas finished green (paper).</>
          : <>Accuracy publishes once {WIN_RATE_MIN_CLOSED}+ ideas have closed — we don't show a win-rate on a tiny sample.</>}
        {latestIdea && <> · Ideas refreshed daily; latest <strong>{latestIdea}</strong>.</>}
      </p>

      {/* How to read this — collapsed by default so the card stays light on
          first run; one tap expands the beginner glossary. */}
      <div className="rounded-lg mb-5" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
        <button type="button" onClick={() => setShowHow((v) => !v)}
          className="w-full flex items-center justify-between gap-2 p-4 text-left">
          <span className="font-semibold uppercase" style={{
            fontSize: 10, letterSpacing: '0.12em', color: 'var(--muted-foreground)',
          }}>How to read this</span>
          <span aria-hidden style={{ fontSize: 11, color: 'var(--muted-foreground)' }}>
            {showHow ? '▲' : '▼'}
          </span>
        </button>
        {showHow && (
          <ul className="space-y-1.5 px-4 pb-4">
            <Explain term="Paper P/L">practice-money profit/loss — nothing real is at stake.</Explain>
            <Explain term="Entry / Target / Exit">where an idea suggests starting, where it's aiming, and the level that would prove it wrong.</Explain>
            <Explain term="Why ArthOS shows its reasoning">you learn how an investor weighs risk — the thinking matters more than the call.</Explain>
            <Explain term="What it does not promise">no returns, no real trading, no "beat the market." It's a learning tool.</Explain>
          </ul>
        )}
      </div>

      {/* Reviewer CTAs */}
      <div className="flex flex-wrap items-center gap-2.5">
        {heroSymbol && (
          <Link to={`/today/pick/${heroSymbol}`}
            className="inline-flex items-center px-4 h-10 rounded-full"
            style={{ fontSize: 13, fontWeight: 600, backgroundColor: 'var(--brand)', color: 'var(--brand-foreground)' }}>
            Try today's idea →
          </Link>
        )}
        <Link to="/account?mode=signup"
          className="inline-flex items-center px-4 h-10 rounded-full"
          style={{ fontSize: 13, fontWeight: 600, border: '1px solid var(--border)', color: 'var(--foreground)' }}>
          Create a free practice account
        </Link>
      </div>
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
      <p className="tabular-nums" style={{ fontSize: 18, fontWeight: 600, color, lineHeight: 1.1 }}>{value}</p>
    </div>
  );
}

function Explain({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <li className="flex gap-2" style={{ fontSize: 12.5, lineHeight: 1.5 }}>
      <span aria-hidden style={{ color: 'var(--brand)' }}>•</span>
      <span className="ink-muted"><strong className="ink-primary">{term}</strong> — {children}</span>
    </li>
  );
}
