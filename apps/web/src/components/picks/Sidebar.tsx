// Sidebar — Copilot briefing on desktop.
// 5 sections: posture, what to do now, what to avoid, watchlist, risk notes.
// Derived honestly from picks data — no fake content.

import type { Pick } from "@/lib/picks/api";
import type { Briefing } from "@/lib/picks/copilot";


export interface SidebarProps {
  picks: Pick[];
  briefing: Briefing;
  onPickClick: (pickId: string) => void;
}


function fmtRelTime(iso: string | null): string {
  if (!iso) return "—";
  const ms = Date.now() - Date.parse(iso);
  const hours = ms / 3_600_000;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m ago`;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}


export default function Sidebar({ picks, briefing, onPickClick }: SidebarProps) {
  // What to do now
  const todoNow: string[] = [];
  if (briefing.highConfidenceTrims > 0) {
    todoNow.push(`Review ${briefing.highConfidenceTrims} high-confidence trim${briefing.highConfidenceTrims === 1 ? "" : "s"}.`);
  }
  const sellCount = picks.filter(p => (p.adjusted_action ?? p.action) === "sell").length;
  if (sellCount > 0) {
    todoNow.push(`Address ${sellCount} sell signal${sellCount === 1 ? "" : "s"} before adding new exposure.`);
  }
  const buyCount = picks.filter(p => (p.adjusted_action ?? p.action) === "buy").length;
  if (buyCount > 0 && sellCount === 0) {
    todoNow.push(`Review ${buyCount} buy idea${buyCount === 1 ? "" : "s"}, starting with highest confidence.`);
  }
  if (todoNow.length === 0) {
    todoNow.push("Review the highest-confidence pick first.");
  }

  // What to avoid
  const toAvoid: string[] = [];
  if (briefing.posture === "defensive" || briefing.posture === "cautious") {
    toAvoid.push("Adding new long exposure today.");
  }
  if (briefing.staleCount > 0) {
    toAvoid.push(`Acting on ${briefing.staleCount} stale signal${briefing.staleCount === 1 ? "" : "s"} — re-run the engine first.`);
  }
  if (briefing.thinDataCount > 0) {
    toAvoid.push(`Sizing up on ${briefing.thinDataCount} thin-data name${briefing.thinDataCount === 1 ? "" : "s"}.`);
  }
  if (toAvoid.length === 0) {
    toAvoid.push("Nothing flagged — no major risks today.");
  }

  // Watchlist
  const watchlist = picks
    .filter(p => (p.adjusted_action ?? p.action) === "hold")
    .slice(0, 4);

  // Risk notes
  const riskNotes = picks.filter(p =>
    p.stale_data ||
    !p.enough_data ||
    (p.adjusted_action ?? p.action) === "sell"
  ).slice(0, 4);

  return (
    <aside className="picks-sidebar" data-test="picks-sidebar">
      <header className="picks-sidebar-header">
        <h3 className="picks-sidebar-title">Copilot briefing</h3>
        <span className="picks-sidebar-sub">{fmtRelTime(briefing.freshestAtIso)}</span>
      </header>

      {/* Posture */}
      <section className="picks-sidebar-section" data-section="posture">
        <h4 className="picks-sidebar-h">
          <span className="picks-sidebar-icon" aria-hidden="true">◆</span>
          Today's posture
        </h4>
        <div className="picks-sidebar-posture-row">
          <span className="picks-sidebar-posture-chip" data-posture={briefing.posture}>
            <span className="picks-sidebar-posture-dot" />
            {briefing.postureLabel}
          </span>
        </div>
        <p className="picks-sidebar-posture-text">{briefing.body}</p>
      </section>

      {/* What to do now */}
      <section className="picks-sidebar-section" data-section="todo">
        <h4 className="picks-sidebar-h">
          <span className="picks-sidebar-icon" aria-hidden="true">→</span>
          What to do now
        </h4>
        <ul className="picks-sidebar-todo">
          {todoNow.map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      </section>

      {/* What to avoid */}
      <section className="picks-sidebar-section" data-section="avoid">
        <h4 className="picks-sidebar-h">
          <span className="picks-sidebar-icon" aria-hidden="true">⊘</span>
          What to avoid
        </h4>
        <ul className="picks-sidebar-avoid">
          {toAvoid.map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      </section>

      {/* Watchlist */}
      <section className="picks-sidebar-section" data-section="watch">
        <h4 className="picks-sidebar-h">
          <span className="picks-sidebar-icon" aria-hidden="true">◎</span>
          Watchlist
        </h4>
        {watchlist.length === 0 ? (
          <p className="picks-sidebar-empty">No watchlist holds today.</p>
        ) : (
          <ul className="picks-sidebar-list">
            {watchlist.map(p => (
              <li key={p.id}>
                <button type="button" className="picks-sidebar-row" onClick={() => onPickClick(p.id)}>
                  <span className="picks-sidebar-action" data-action="hold">hold</span>
                  <span className="picks-sidebar-symbol">{p.symbol ?? "—"}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Risk notes */}
      <section className="picks-sidebar-section" data-section="risk">
        <h4 className="picks-sidebar-h">
          <span className="picks-sidebar-icon" aria-hidden="true">!</span>
          Risk notes
        </h4>
        {riskNotes.length === 0 ? (
          <p className="picks-sidebar-empty">No active risk alerts.</p>
        ) : (
          <ul className="picks-sidebar-list">
            {riskNotes.map(p => {
              const action = p.adjusted_action ?? p.action;
              const reason = p.stale_data
                ? "Stale signal"
                : !p.enough_data
                  ? "Thin data"
                  : "Sell signal";
              return (
                <li key={p.id}>
                  <button type="button" className="picks-sidebar-row" onClick={() => onPickClick(p.id)}>
                    <span className="picks-sidebar-action" data-action={action}>{action}</span>
                    <span className="picks-sidebar-symbol">{p.symbol ?? "—"}</span>
                    <span className="picks-sidebar-reason">{reason}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </aside>
  );
}
