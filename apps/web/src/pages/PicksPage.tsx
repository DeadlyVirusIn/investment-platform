// PicksPage — main landing page (default /overview).
//
// Renders a grid of green BUY / red SELL / neutral HOLD boxes
// from /api/recommendations sorted by confidence desc. Click box
// → modal with target/reason details.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import PickBox from "@/components/picks/PickBox";
import PickModal from "@/components/picks/PickModal";
import { fetchPicks, type Pick } from "@/lib/picks/api";


export default function PicksPage() {
  const [picks, setPicks] = useState<Pick[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openPickId, setOpenPickId] = useState<string | null>(null);

  // Initial fetch
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPicks(30)
      .then(rows => {
        if (cancelled) return;
        setPicks(rows);
        setLoading(false);
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

  // Filter out hold (lowest priority) — show buy + sell first, fall back to hold if nothing else
  const visiblePicks = useMemo(() => {
    const actionOrder: Record<string, number> = { buy: 0, sell: 1, hold: 2 };
    return [...picks].sort((a, b) => {
      const ao = (a.adjusted_action ?? a.action) as "buy" | "sell" | "hold";
      const bo = (b.adjusted_action ?? b.action) as "buy" | "sell" | "hold";
      // First: bring buy + sell ahead of hold
      const orderA = actionOrder[ao] ?? 9;
      const orderB = actionOrder[bo] ?? 9;
      if (orderA !== orderB) return orderA - orderB;
      // Then: confidence desc
      const ca = parseFloat(a.adjusted_confidence ?? a.confidence ?? "0");
      const cb = parseFloat(b.adjusted_confidence ?? b.confidence ?? "0");
      return cb - ca;
    });
  }, [picks]);

  const buyCount = visiblePicks.filter(p => (p.adjusted_action ?? p.action) === "buy").length;
  const sellCount = visiblePicks.filter(p => (p.adjusted_action ?? p.action) === "sell").length;

  return (
    <div className="picks-root" data-test="picks-root">
      <div className="picks-frame">
        <header className="picks-header">
          <div>
            <h1 className="picks-title">AI suggestions</h1>
            <p className="picks-subtitle">
              {loading ? "Loading…" : `${buyCount} buy · ${sellCount} sell · sorted by confidence`}
            </p>
          </div>
          <nav className="picks-archive-nav" data-test="picks-archive-nav">
            <span style={{ color: "var(--picks-ink-recede)" }}>archive</span>
            <Link to="/overview?view=working">working</Link>
            <Link to="/overview?view=conviction">conviction</Link>
            <Link to="/overview?view=copilot">copilot</Link>
            <Link to="/overview?view=living">living</Link>
            <Link to="/overview?view=stream">stream</Link>
          </nav>
        </header>

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
            No AI suggestions available right now. Engine may be running.
          </div>
        )}

        {!loading && !error && visiblePicks.length > 0 && (
          <div className="picks-grid" data-test="picks-grid">
            {visiblePicks.map(pick => (
              <PickBox
                key={pick.id}
                pick={pick}
                onClick={setOpenPickId}
              />
            ))}
          </div>
        )}
      </div>

      <PickModal pick={openPick} onClose={() => setOpenPickId(null)} />
    </div>
  );
}
