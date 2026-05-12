// Phase Opt-A — Closed Paper Options Trades card.
//
// Reads /api/options/paper-trades. Filters to CLOSED|EXPIRED.
// P&L summary tile gated on N≥10 closed trades per debate
// convergence (premature aggregation = casino UX).

import { useOptionsPaperTrades } from "@/lib/options/hooks";


const PNL_GATE_MIN_CLOSED = 10;


function fmt(v: string | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = parseFloat(v);
  if (Number.isNaN(n)) return String(v);
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}


export default function OptionsClosedTradesCard() {
  const { data, isLoading } = useOptionsPaperTrades({});
  const closed = (data?.trades ?? []).filter(
    t => t.status === "CLOSED" || t.status === "EXPIRED",
  );

  return (
    <section className="u-card opt-card" data-test="options-closed-trades">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Closed paper options trades</span>
        <span className="opt-card-meta">
          {isLoading ? "loading…" : `${closed.length} closed (lifetime)`}
        </span>
      </header>

      {!isLoading && closed.length === 0 && (
        <div className="opt-empty">
          <p className="opt-empty-headline">No closed options trades yet.</p>
          <p className="opt-empty-body">
            Closed ledger populates after the first paper trade exits
            (target hit, stop hit, or expiry). P&amp;L aggregate stats
            unlock at {PNL_GATE_MIN_CLOSED} closed trades.
          </p>
        </div>
      )}

      {!isLoading && closed.length > 0 && closed.length < PNL_GATE_MIN_CLOSED && (
        <div className="opt-empty">
          <p className="opt-empty-headline">
            {closed.length} closed trade{closed.length === 1 ? "" : "s"}.
          </p>
          <p className="opt-empty-body">
            P&amp;L aggregate metrics unlock at {PNL_GATE_MIN_CLOSED}+
            closed trades to avoid drawing conclusions from a tiny
            sample.
          </p>
        </div>
      )}

      {!isLoading && closed.length >= PNL_GATE_MIN_CLOSED && (
        <ul className="opt-trade-list">
          {closed.map(t => (
            <li key={t.id} className="opt-trade-row" data-status={t.status}>
              <span className="opt-trade-symbol">{t.underlying}</span>
              <span className="opt-trade-strategy">{t.strategy_name}</span>
              <span className="opt-trade-status">{t.status.toLowerCase()}</span>
              <span className="opt-trade-dte">
                {t.closed_at
                  ? new Date(t.closed_at).toLocaleDateString()
                  : "—"}
              </span>
              <span className="opt-trade-pnl">
                {fmt(t.realized_pnl_dollars)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
