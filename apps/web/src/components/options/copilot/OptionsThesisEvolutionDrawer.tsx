// OptionsThesisEvolutionDrawer — per-trade narrative drawer.
//
// Reads /api/options/journal/trade/{id}/evolution and renders:
//   * trade snapshot
//   * originating candidates (why AI proposed)
//   * lifecycle event chain (chronological)
//
// Read-only. Honest empty sections when nothing recorded yet.

import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import { fmtUSD } from "@/components/ui/primitives";


export interface ThesisEvolutionProps {
  open: boolean;
  tradeId: number | null;
  onClose: () => void;
}


interface EvolutionPayload {
  trade: {
    trade_id: number;
    underlying: string;
    strategy_name: string;
    status: string;
    opened_at: string | null;
    closed_at: string | null;
    entry_credit_dollars: number | null;
    realized_pnl_dollars: number | null;
    max_loss_dollars: number | null;
    max_profit_dollars: number | null;
    breakeven_lower: number | null;
    breakeven_upper: number | null;
    proposal_hash: string | null;
  };
  originating_candidates: Array<{
    candidate_id: number;
    rule_id: string;
    bias: string;
    composite_score: number | null;
    why_emitted: string;
    triggering_rule: string;
    run_date: string | null;
    strategy_fit_reason: string | null;
    earliest_event_type: string | null;
    earliest_event_date: string | null;
    event_days_away: number | null;
  }>;
  lifecycle_events: Array<{
    event_id: number;
    event_at_utc: string;
    event_type: string;
    triggered_by: string;
    payload: Record<string, unknown>;
  }>;
  summary: {
    candidates_seen: number;
    lifecycle_steps: number;
    current_status: string;
  };
}


export default function OptionsThesisEvolutionDrawer({
  open, tradeId, onClose,
}: ThesisEvolutionProps) {
  const [data, setData] = useState<EvolutionPayload | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || tradeId == null) return;
    let cancelled = false;
    setLoading(true);
    setData(null);
    fetch(`/api/options/journal/trade/${tradeId}/evolution`)
      .then(r => r.ok ? r.json() : null)
      .then(j => { if (!cancelled) { setData(j); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, tradeId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="opt-edu-overlay" onClick={onClose}>
      <aside
        className={cn("opt-edu-drawer opt-evolution-drawer")}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Thesis evolution"
      >
        <header className="opt-edu-header">
          <div>
            <div className="opt-edu-eyebrow">AI Strategist · thesis evolution</div>
            <h3 className="opt-edu-title">
              {data ? `${data.trade.strategy_name.replace(/_/g, " ")} on ${data.trade.underlying}`
                    : "Thesis evolution"}
            </h3>
            {data && (
              <div className="opt-edu-strategy">
                Trade #{data.trade.trade_id} · status {data.trade.status}
              </div>
            )}
          </div>
          <button type="button" className="opt-edu-close"
                  onClick={onClose}>×</button>
        </header>

        {loading && (
          <p className="opt-caption-muted">Loading evolution…</p>
        )}

        {!loading && data && (
          <>
            {/* Trade snapshot */}
            <section className="opt-edu-section">
              <h4 className="opt-edu-heading">Trade snapshot</h4>
              <div className="opt-evolution-snapshot">
                <Cell label="Opened" value={data.trade.opened_at?.slice(0, 16) ?? "—"} />
                <Cell label="Closed" value={data.trade.closed_at?.slice(0, 16) ?? "—"} />
                <Cell label="Entry credit"
                      value={data.trade.entry_credit_dollars != null
                        ? fmtUSD(data.trade.entry_credit_dollars) : "—"} />
                <Cell label="Realized P&L"
                      value={data.trade.realized_pnl_dollars != null
                        ? fmtUSD(data.trade.realized_pnl_dollars) : "—"} />
                <Cell label="Max profit"
                      value={fmtUSD(data.trade.max_profit_dollars ?? 0)} />
                <Cell label="Max loss"
                      value={fmtUSD(data.trade.max_loss_dollars ?? 0)} />
              </div>
            </section>

            {/* Originating candidates */}
            <section className="opt-edu-section">
              <h4 className="opt-edu-heading">
                Originating candidates ({data.summary.candidates_seen})
              </h4>
              {data.originating_candidates.length === 0 ? (
                <span className="opt-caption-muted">
                  No originating strategy candidate found. Trade may
                  predate the candidate generator.
                </span>
              ) : (
                <ul className="opt-evolution-candidates">
                  {data.originating_candidates.map(c => (
                    <li key={c.candidate_id}>
                      <div className="opt-evolution-cand-head">
                        <strong>
                          {c.rule_id.replace(/_/g, " ").toLowerCase()
                            .replace(/\b\w/g, x => x.toUpperCase())}
                        </strong>
                        <span className="opt-caption-muted">
                          {c.run_date} · composite{" "}
                          {c.composite_score != null
                            ? c.composite_score.toFixed(3) : "—"}
                        </span>
                      </div>
                      <p className="opt-edu-paragraph">{c.why_emitted}</p>
                      {c.strategy_fit_reason && (
                        <p className="opt-caption-muted">
                          {c.strategy_fit_reason}
                        </p>
                      )}
                      {c.earliest_event_type && (
                        <p className="opt-caption-muted">
                          Catalyst at entry: {c.earliest_event_type}{" "}
                          on {c.earliest_event_date}
                          {c.event_days_away != null
                            ? ` (T-${c.event_days_away}d)` : ""}.
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Lifecycle chain */}
            <section className="opt-edu-section">
              <h4 className="opt-edu-heading">
                Lifecycle ({data.summary.lifecycle_steps})
              </h4>
              {data.lifecycle_events.length === 0 ? (
                <span className="opt-caption-muted">
                  No lifecycle events yet — trade has not progressed
                  through PROPOSED/FILLED/CLOSED/etc.
                </span>
              ) : (
                <ul className="opt-evolution-lifecycle">
                  {data.lifecycle_events.map(e => (
                    <li key={e.event_id}>
                      <span className="opt-evolution-step-time">
                        {e.event_at_utc.slice(0, 16)}
                      </span>
                      <span className="opt-evolution-step-type">
                        {e.event_type.replace(/_/g, " ")}
                      </span>
                      <span className="opt-caption-muted">
                        via {e.triggered_by.toLowerCase()}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <footer className="opt-edu-footer">
              <span>
                Current status: <code>{data.summary.current_status}</code>
              </span>
            </footer>
          </>
        )}
      </aside>
    </div>
  );
}


function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="opt-evolution-snapshot-cell">
      <span className="opt-evolution-snapshot-label">{label}</span>
      <span className="opt-evolution-snapshot-value">{value}</span>
    </div>
  );
}
