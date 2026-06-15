// V2 Rail disclosure sheet — mobile-only slide-down panel exposing
// the cells hidden in the collapsed rail.
//
// Collapsed visible (per decision 2):
//   NAV · Health · Market tape · NOW
//
// Expanded sheet (this component) adds:
//   Today P&L · Total Return · Regime · Engine · NEXT
//
// Same hooks as the legacy rail components; React Query dedupes so
// there is no extra network traffic. No business / API / anomaly /
// engine logic is touched.

import { useEffect, useRef } from 'react';
import {
  useCanonicalStockPortfolio, useCurrentState,
} from '@/lib/operator/hooks';
import { fmtPct } from '@/components/ui/primitives';

export function V2RailDisclosure({ onClose }: { onClose: () => void }) {
  // Phase A/B — rail portfolio metrics read the canonical portfolio.
  const { data: summary } = useCanonicalStockPortfolio();
  const { data: state } = useCurrentState();
  const ref = useRef<HTMLDivElement>(null);

  // Esc + outside-tap dismiss.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const onClick = (e: MouseEvent) => {
      if (!ref.current) return;
      if (!ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener('keydown', onKey);
    // Defer click listener so the open click itself does not dismiss.
    const t = window.setTimeout(() => {
      document.addEventListener('mousedown', onClick);
    }, 0);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
      window.clearTimeout(t);
    };
  }, [onClose]);

  const pnl = summary?.daily_pnl ?? null;
  const pnlText = pnl == null
    ? '—'
    : `${pnl > 0 ? '+' : pnl < 0 ? '−' : ''}$${Math.abs(pnl).toFixed(2)}`;

  const regime = state?.stress_regime ? 'Stress'
    : state?.directional_regime ? 'Directional' : 'Neutral';
  const engine = state?.fire
    ? `Engine ${state.engine} firing`
    : state?.engine && state.engine !== 'none'
      ? `Engine ${state.engine} idle`
      : 'No engine armed';

  const next = state?.fire
    ? 'Monitor target exit'
    : state?.stress_regime
      ? 'Await oversold setup (P15)'
      : state?.directional_regime
        ? 'Await credit + rates alignment'
        : 'Await regime qualification';

  return (
    <div className="v2-rail-disclosure-sheet" ref={ref} role="region"
         aria-label="Rail detail">
      <Row label="Today P&L" value={pnlText} />
      <Row label="Total Return" value={fmtPct(summary?.total_return_pct)} />
      <Row label="Regime" value={regime} />
      <Row label="Engine" value={engine} />
      <div className="v2-rail-disclosure-divider" aria-hidden="true" />
      <Row label="Next" value={next} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="v2-rail-disclosure-row">
      <span className="v2-rail-disclosure-label">{label}</span>
      <span className="v2-rail-disclosure-value">{value}</span>
    </div>
  );
}
