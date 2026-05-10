// PicksPage — main landing.
//
// Header shows full breakdown across all 4 actions + a beginner-
// friendly status line.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import PickBox from "@/components/picks/PickBox";
import PickModal from "@/components/picks/PickModal";
import {
  fetchPicks, fetchLatestPrices, type Pick, type LatestPrice, type PickAction,
} from "@/lib/picks/api";


function buildStatusLine(counts: Record<PickAction, number>): string {
  const total = counts.buy + counts.sell + counts.trim + counts.hold;
  if (total === 0) {
    return "No suggestions available right now.";
  }
  if (counts.buy === 0 && counts.sell === 0) {
    return `No new Buy or Sell ideas today. AI is mostly saying ${
      counts.trim > counts.hold ? "Trim — risk has grown on existing positions" : "Hold — keep watching, don't add yet"
    }.`;
  }
  if (counts.buy > 0 && counts.sell === 0) {
    return `${counts.buy} new Buy ${counts.buy === 1 ? "idea" : "ideas"} today. ${counts.trim + counts.hold} positions to keep watching.`;
  }
  if (counts.sell > 0 && counts.buy === 0) {
    return `${counts.sell} Sell ${counts.sell === 1 ? "signal" : "signals"} today. AI sees risk increasing.`;
  }
  return `${counts.buy} Buy · ${counts.sell} Sell · ${counts.trim} Trim · ${counts.hold} Hold — sorted by confidence.`;
}


export default function PicksPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [priceMap, setPriceMap] = useState<Record<string, LatestPrice | null | undefined>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openPickId, setOpenPickId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPicks(30)
      .then(rows => {
        if (cancelled) return;
        setPicks(rows);
        setLoading(false);

        const symbols = rows.map(r => r.symbol).filter((s): s is string => !!s);
        const initialMap: Record<string, undefined> = {};
        symbols.forEach(s => { initialMap[s] = undefined; });
        setPriceMap(initialMap);

        if (symbols.length > 0) {
          fetchLatestPrices(symbols).then(map => {
            if (!cancelled) setPriceMap(map);
          });
        }
      })
      .catch(err => {
        if (cancelled) return;
        setError(err?.message ?? "Failed to load suggestions.");
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const openPick = useMemo(
    () => picks.find(p => p.id === openPickId) ?? null,
    [picks, openPickId],
  );

  const openPrice = openPick?.symbol ? priceMap[openPick.symbol] ?? null : null;

  // Sort: BUY → SELL → TRIM → HOLD, then confidence desc within
  const visiblePicks = useMemo(() => {
    const actionOrder: Record<PickAction, number> = { buy: 0, sell: 1, trim: 2, hold: 3 };
    return [...picks].sort((a, b) => {
      const ao = a.adjusted_action ?? a.action;
      const bo = b.adjusted_action ?? b.action;
      const orderA = actionOrder[ao] ?? 9;
      const orderB = actionOrder[bo] ?? 9;
      if (orderA !== orderB) return orderA - orderB;
      const ca = parseFloat(a.adjusted_confidence ?? a.confidence ?? "0");
      const cb = parseFloat(b.adjusted_confidence ?? b.confidence ?? "0");
      return cb - ca;
    });
  }, [picks]);

  const counts = useMemo(() => {
    const c: Record<PickAction, number> = { buy: 0, sell: 0, trim: 0, hold: 0 };
    for (const p of visiblePicks) {
      const a = p.adjusted_action ?? p.action;
      c[a] = (c[a] ?? 0) + 1;
    }
    return c;
  }, [visiblePicks]);

  const statusLine = buildStatusLine(counts);

  return (
    <div className="picks-root" data-test="picks-root">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">AI suggestions</h1>
            <p className="picks-subtitle">
              {loading ? "Loading…" : `${visiblePicks.length} ${visiblePicks.length === 1 ? "suggestion" : "suggestions"} from your AI engine`}
            </p>
            {!loading && visiblePicks.length > 0 && (
              <div className="picks-counts" data-test="picks-counts">
                <span className="picks-count-pill" data-action="buy">
                  <strong>{counts.buy}</strong> Buy
                </span>
                <span className="picks-count-pill" data-action="hold">
                  <strong>{counts.hold}</strong> Hold
                </span>
                <span className="picks-count-pill" data-action="trim">
                  <strong>{counts.trim}</strong> Trim
                </span>
                <span className="picks-count-pill" data-action="sell">
                  <strong>{counts.sell}</strong> Sell
                </span>
              </div>
            )}
          </div>
          <nav className="picks-archive-nav" data-test="picks-archive-nav">
            <span style={{ color: "var(--picks-ink-recede)" }}>archive</span>
            <Link to="/overview?view=working">working</Link>
            <Link to="/overview?view=conviction">conviction</Link>
            <Link to="/overview?view=copilot">copilot</Link>
            <Link to="/overview?view=living">living</Link>
            <Link to="/overview?view=stream">stream</Link>
            <Link to="/overview?view=legacy">legacy</Link>
          </nav>
        </header>

        {!loading && visiblePicks.length > 0 && (
          <div className="picks-status" data-test="picks-status">
            {statusLine}
          </div>
        )}

        {loading && (
          <div className="picks-loading" data-test="picks-loading">
            Loading AI suggestions…
          </div>
        )}

        {error && (
          <div className="picks-error" data-test="picks-error">
            {error}
          </div>
        )}

        {!loading && !error && visiblePicks.length === 0 && (
          <div className="picks-empty" data-test="picks-empty">
            No AI suggestions available right now. The recommendation engine may
            still be running. Check back shortly.
          </div>
        )}

        {!loading && !error && visiblePicks.length > 0 && (
          <div className="picks-grid" data-test="picks-grid">
            {visiblePicks.map(pick => (
              <PickBox
                key={pick.id}
                pick={pick}
                price={pick.symbol ? priceMap[pick.symbol] : null}
                onClick={setOpenPickId}
              />
            ))}
          </div>
        )}
      </div>

      <PickModal
        pick={openPick}
        priceCache={openPrice}
        onClose={() => setOpenPickId(null)}
      />
    </div>
  );
}
