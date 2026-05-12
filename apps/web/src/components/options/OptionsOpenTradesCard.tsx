// Phase Opt-A — Open Paper Options Trades card.
//
// Reads /api/options/paper-trades. Filters to non-closed states.
// PaperTradeHeader carries strategy-level fields only; per-leg
// expiry lives in the detail endpoint and is omitted here for v1.
// (When operator wants per-card DTE chip, fetch details lazily.)

import { useOptionsPaperTrades } from "@/lib/options/hooks";


function fmt(v: string | null | undefined): string {
  if (v == null || v === "") return "—";
  // Accept either a numeric string or display it raw.
  const n = parseFloat(v);
  if (Number.isNaN(n)) return String(v);
  const sign = n >= 0 ? "+" : "";
  return `${sign}$${n.toFixed(2)}`;
}


export default function OptionsOpenTradesCard() {
  const { data, isLoading } = useOptionsPaperTrades({});
  const trades = (data?.trades ?? []).filter(
    t => t.status !== "CLOSED" && t.status !== "EXPIRED",
  );

  return (
    <section className="u-card opt-card" data-test="options-open-trades">
      <header className="opt-card-header">
        <span className="opt-card-eyebrow">Open paper options trades</span>
        <span className="opt-card-meta">
          {isLoading ? "loading…" : `${trades.length} open`}
        </span>
      </header>

      {!isLoading && trades.length === 0 && (
        <div className="opt-empty">
          <p className="opt-empty-headline">No open options paper trades.</p>
          <p className="opt-empty-body">
            Paper exec runner is manual only — no automated execution
            scheduled. When daily exec is wired (Phase Opt-B), filled
            trades appear here with breakeven, days-to-expiry, and
            unrealized P&amp;L.
          </p>
        </div>
      )}

      {!isLoading && trades.length > 0 && (
        <ul className="opt-trade-list">
          {trades.map(t => (
            <li
              key={t.id}
              className="opt-trade-row"
              data-status={t.status}
            >
              <span className="opt-trade-symbol">{t.underlying}</span>
              <span className="opt-trade-strategy">{t.strategy_name}</span>
              <span className="opt-trade-status">{t.status.toLowerCase()}</span>
              <span className="opt-trade-dte">
                {t.opened_at
                  ? new Date(t.opened_at).toLocaleDateString()
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
