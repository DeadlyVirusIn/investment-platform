// CompanyTitle — beginner-safe identity for an asset (Phase 2).
//
// Renders "Royalty Pharma (RPRX)" so a first-time investor knows what they're
// looking at without Googling the ticker. Name comes from the engine payload
// (pass `name`) or, when the surface only has a symbol, from the cached
// /assets name map. NEVER fabricates: when no name is known it falls back to
// the ticker alone.

import { useAssetNames, cleanCompanyName } from '../lib/companyMeta';

export function CompanyTitle({
  symbol,
  name,
  className,
  style,
  tickerClassName = 'font-mono ink-muted',
  tickerStyle,
  showTickerWhenNamed = true,
}: {
  symbol: string | null | undefined;
  /** Name from the payload; when omitted we resolve via the /assets map. */
  name?: string | null;
  className?: string;
  style?: React.CSSProperties;
  tickerClassName?: string;
  tickerStyle?: React.CSSProperties;
  /** When false and a name resolves, render just the name (no "(TICKER)"). */
  showTickerWhenNamed?: boolean;
}) {
  const map = useAssetNames();
  const sym = symbol ?? '';
  const raw = (name ?? (sym ? map[sym.toUpperCase()] : null)) || null;
  const resolved = cleanCompanyName(raw);

  if (!sym) return <span className={className} style={style}>—</span>;

  // No name known → ticker only (honest fallback, never fabricated).
  if (!resolved) {
    return <span className={`font-mono ${className ?? ''}`.trim()} style={style}>{sym}</span>;
  }

  if (!showTickerWhenNamed) {
    return <span className={className} style={style}>{resolved}</span>;
  }

  return (
    <span className={className} style={style}>
      {resolved} <span className={tickerClassName} style={tickerStyle}>({sym})</span>
    </span>
  );
}
