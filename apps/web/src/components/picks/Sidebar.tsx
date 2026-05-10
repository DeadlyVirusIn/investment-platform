// Sidebar — right-side AI Copilot summary on desktop.
// Sections derived honestly from picks data (no fake news/catalysts).

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
  // What changed today: picks generated within last 24h, sorted desc
  const changedToday = picks
    .filter(p => {
      if (!p.generated_at) return false;
      return (Date.now() - Date.parse(p.generated_at)) < 24 * 3_600_000;
    })
    .sort((a, b) => Date.parse(b.generated_at!) - Date.parse(a.generated_at!))
    .slice(0, 5);

  // Risk alerts: stale + thin data + sell signals
  const riskAlerts = picks.filter(p =>
    p.stale_data ||
    !p.enough_data ||
    (p.adjusted_action ?? p.action) === "sell"
  ).slice(0, 5);

  // Watchlist: hold-tier picks
  const watchlist = picks
    .filter(p => (p.adjusted_action ?? p.action) === "hold")
    .slice(0, 5);

  // What to do next — derived from briefing
  const nextSteps = (() => {
    const steps: string[] = [];
    if (briefing.highConfidenceTrims > 0) {
      steps.push(`Review ${briefing.highConfidenceTrims} high-confidence trim${briefing.highConfidenceTrims === 1 ? "" : "s"} first.`);
    }
    if (briefing.staleCount > 0) {
      steps.push(`${briefing.staleCount} signal${briefing.staleCount === 1 ? " is" : "s are"} stale — re-run engine.`);
    }
    if (briefing.posture === "defensive" || briefing.posture === "cautious") {
      steps.push("Avoid adding new exposure today.");
    }
    if (briefing.highConfidenceHolds > 0) {
      steps.push(`${briefing.highConfidenceHolds} strong hold${briefing.highConfidenceHolds === 1 ? "" : "s"} — protect, don't add.`);
    }
    if (steps.length === 0) {
      steps.push("Review the highest-confidence pick first.");
    }
    return steps;
  })();

  return (
    <aside className="picks-sidebar" data-test="picks-sidebar">
      {/* What changed today */}
      <section className="picks-sidebar-section">
        <h3 className="picks-sidebar-h">What changed today</h3>
        {changedToday.length === 0 ? (
          <p className="picks-sidebar-empty">No new signals in the last 24 hours.</p>
        ) : (
          <ul className="picks-sidebar-list">
            {changedToday.map(p => {
              const action = p.adjusted_action ?? p.action;
              return (
                <li key={p.id}>
                  <button type="button" className="picks-sidebar-row" onClick={() => onPickClick(p.id)}>
                    <span className="picks-sidebar-action" data-action={action}>{action}</span>
                    <span className="picks-sidebar-symbol">{p.symbol ?? "—"}</span>
                    <span className="picks-sidebar-time">{fmtRelTime(p.generated_at)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* What to do next */}
      <section className="picks-sidebar-section">
        <h3 className="picks-sidebar-h">What to do next</h3>
        <ul className="picks-sidebar-todo">
          {nextSteps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </section>

      {/* Watchlist */}
      <section className="picks-sidebar-section">
        <h3 className="picks-sidebar-h">Watchlist</h3>
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

      {/* Risk alerts */}
      <section className="picks-sidebar-section">
        <h3 className="picks-sidebar-h">Risk alerts</h3>
        {riskAlerts.length === 0 ? (
          <p className="picks-sidebar-empty">No active risk alerts.</p>
        ) : (
          <ul className="picks-sidebar-list">
            {riskAlerts.map(p => {
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
