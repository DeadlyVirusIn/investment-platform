// Phase D — Exit Analytics card. Read-only.
//
// Renders /api/performance/paper/exit-analytics output. Honours
// the small-sample-size caveat verbatim (server-supplied) so the
// operator never reads a tiny-sample win-rate as predictive.
// NEVER fabricates a denominator: when n_closed=0 the win rate
// is shown as "—" with the explicit "no_closed_outcomes_yet"
// message.

import { useState } from "react";
import { cn } from "@/lib/cn";
import { fmtUSD, toneForNumber } from "@/components/ui/primitives";
import {
  useExitAnalytics,
  type ExitCategory,
  type ExitCategoryRow,
  type ExitTrade,
} from "@/lib/alphaLab/hooks";


const CATEGORY_LABEL: Record<ExitCategory, string> = {
  take_profit: "Take-profit",
  stop_loss: "Stop-loss",
  max_hold: "Max-hold",
  other: "Other",
};


export default function ExitAnalyticsCard() {
  const [includeReplay, setIncludeReplay] = useState(false);
  const q = useExitAnalytics(includeReplay);

  return (
    <section
      data-test="exit-analytics-card"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">
            Exit Analytics
          </h2>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
            source: GET /performance/paper/exit-analytics
          </div>
        </div>
        <label className="flex items-center gap-2 u-caption-2 cursor-pointer">
          <input
            type="checkbox"
            checked={includeReplay}
            onChange={(e) => setIncludeReplay(e.target.checked)}
          />
          <span>Include replay-recovered rows</span>
        </label>
      </header>

      {q.isLoading && (
        <p className="u-caption italic">Loading exit analytics…</p>
      )}
      {q.error && (
        <p className="u-caption text-danger">
          Endpoint unreachable. This card is read-only —
          execution is unaffected.
        </p>
      )}
      {q.data && <Body data={q.data} />}
    </section>
  );
}


function Body({
  data,
}: {
  data: NonNullable<ReturnType<typeof useExitAnalytics>["data"]>;
}) {
  if (data.n_closed === 0) {
    return (
      <div className="u-card-tight">
        <p className="u-caption">
          No closed trades yet. Exit analytics activate after the
          exit-cycle runner closes eligible positions.
        </p>
      </div>
    );
  }

  return (
    <>
      {data.small_sample_warning && (
        <div
          className="mb-3 rounded border border-amber-700/60 bg-amber-900/20 px-3 py-2 text-[12px] text-amber-300"
          data-test="exit-analytics-small-sample"
        >
          {data.small_sample_warning} Threshold: ≥ {data.small_sample_threshold} closed trades.
        </div>
      )}

      {/* Headline strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell
          label="Closed"
          value={String(data.n_closed)}
          sub={`${data.n_winners}W · ${data.n_losers}L`}
        />
        <Cell
          label="Win rate"
          value={data.win_rate != null
            ? `${(data.win_rate * 100).toFixed(0)}%`
            : "—"}
          tone={(data.win_rate ?? 0) >= 0.5 ? "pos"
            : (data.win_rate ?? 0) < 0.4 ? "neg" : "neutral"}
        />
        <Cell
          label="Realized P&L"
          value={fmtUSD(data.realized_pnl_total)}
          tone={toneForNumber(data.realized_pnl_total)}
        />
        <Cell
          label="Avg hold"
          value={data.avg_hold_days != null
            ? `${data.avg_hold_days.toFixed(1)}d`
            : "—"}
        />
      </div>

      {/* Avg win / Avg loss / TP / SL strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Cell
          label="Avg win"
          value={data.avg_win_dollars != null
            ? fmtUSD(data.avg_win_dollars) : "—"}
          tone="pos"
        />
        <Cell
          label="Avg loss"
          value={data.avg_loss_dollars != null
            ? fmtUSD(data.avg_loss_dollars) : "—"}
          tone="neg"
        />
        <Cell
          label="TP count"
          value={String(data.tp_sl_effectiveness.tp_count)}
          sub={data.tp_sl_effectiveness.tp_avg_pnl != null
            ? `avg ${fmtUSD(data.tp_sl_effectiveness.tp_avg_pnl)}`
            : ""}
        />
        <Cell
          label="SL count"
          value={String(data.tp_sl_effectiveness.sl_count)}
          sub={data.tp_sl_effectiveness.sl_avg_pnl != null
            ? `avg ${fmtUSD(data.tp_sl_effectiveness.sl_avg_pnl)}`
            : ""}
          warn={data.tp_sl_effectiveness.sl_count > 0
            && data.tp_sl_effectiveness.tp_count === 0}
        />
      </div>

      {/* By-category breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <CategoryTable rows={data.by_category} />
        <RawBreakdown rows={data.exit_reason_raw_breakdown} />
      </div>

      {/* Best / worst */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <ExtremeBlock label="Best exit"
                      tone="pos"
                      trade={data.best_exit} />
        <ExtremeBlock label="Worst exit"
                      tone="neg"
                      trade={data.worst_exit} />
      </div>

      {/* Trades table */}
      <table className="u-table" data-test="exit-analytics-trades">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Exit</th>
            <th>Category</th>
            <th className="text-right">Realized</th>
            <th className="text-right">Held</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {data.trades.map((t) => (
            <TradeRow key={t.trade_id} t={t} />
          ))}
        </tbody>
      </table>

      <p className="u-caption-2 mt-3">{data.notice}</p>
    </>
  );
}


function Cell({
  label, value, sub, tone = "neutral", warn = false,
}: {
  label: string; value: string; sub?: string;
  tone?: "pos" | "neg" | "neutral";
  warn?: boolean;
}) {
  const cls = warn
    ? "text-warning"
    : tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div className="u-card-tight">
      <div className="u-caption-2 text-fg-3">{label}</div>
      <div className={cn("u-mono-md font-semibold mt-0.5", cls)}>
        {value}
      </div>
      {sub && (
        <div className="u-caption-2 text-fg-3 mt-1">{sub}</div>
      )}
    </div>
  );
}


function CategoryTable({ rows }: { rows: ExitCategoryRow[] }) {
  return (
    <div className="u-card-tight">
      <div className="u-label mb-2">By category</div>
      <table className="u-table">
        <thead>
          <tr>
            <th>Category</th>
            <th className="text-right">N</th>
            <th className="text-right">Win rate</th>
            <th className="text-right">Avg P&L</th>
            <th className="text-right">Total P&L</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.category}>
              <td>{CATEGORY_LABEL[r.category] ?? r.category}</td>
              <td className="text-right u-mono">{r.n}</td>
              <td className="text-right u-mono">
                {r.win_rate != null
                  ? `${(r.win_rate * 100).toFixed(0)}%`
                  : "—"}
              </td>
              <td className={cn(
                "text-right u-mono",
                toneForNumber(r.avg_pnl ?? 0) === "pos"
                  ? "text-success"
                  : toneForNumber(r.avg_pnl ?? 0) === "neg"
                  ? "text-danger" : "text-fg",
              )}>
                {r.avg_pnl != null ? fmtUSD(r.avg_pnl) : "—"}
              </td>
              <td className={cn(
                "text-right u-mono",
                toneForNumber(r.total_pnl) === "pos"
                  ? "text-success"
                  : toneForNumber(r.total_pnl) === "neg"
                  ? "text-danger" : "text-fg",
              )}>
                {fmtUSD(r.total_pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


function RawBreakdown({
  rows,
}: { rows: Array<{ reason: string; n: number }> }) {
  return (
    <div className="u-card-tight">
      <div className="u-label mb-2">Exit reason (raw)</div>
      {rows.length === 0
        ? <p className="u-caption italic">no rows</p>
        : (
          <ul className="space-y-1 text-xs">
            {rows.map((r) => (
              <li key={r.reason}
                  className="flex items-baseline justify-between gap-2">
                <span className="text-fg-3 truncate" title={r.reason}>
                  {r.reason}
                </span>
                <span className="u-mono">{r.n}</span>
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}


function ExtremeBlock({
  label, tone, trade,
}: {
  label: string; tone: "pos" | "neg";
  trade: ExitTrade | null;
}) {
  return (
    <div className="u-card-tight">
      <div className="u-label mb-2">{label}</div>
      {!trade
        ? <p className="u-caption italic">none</p>
        : (
          <>
            <div className="flex items-baseline justify-between mb-1">
              <span className="u-mono font-semibold">
                {trade.symbol}
              </span>
              <span className={cn(
                "u-mono-sm font-semibold",
                tone === "pos" ? "text-success" : "text-danger",
              )}>
                {fmtUSD(trade.realized_pnl)}
              </span>
            </div>
            <div className="u-caption-2 text-fg-3">
              {CATEGORY_LABEL[trade.category]} ·{" "}
              {trade.held_days != null ? `${trade.held_days}d` : "—"}{" "}
              · {trade.exit_ts?.slice(0, 10) ?? "—"}
            </div>
            {trade.reason && (
              <div className="u-caption-2 text-fg-3 mt-1 truncate"
                   title={trade.reason}>
                {trade.reason}
              </div>
            )}
          </>
        )}
    </div>
  );
}


function TradeRow({ t }: { t: ExitTrade }) {
  const tone = toneForNumber(t.realized_pnl);
  return (
    <tr>
      <td className="u-mono">{t.symbol}</td>
      <td className="u-caption-2">{t.exit_ts?.slice(0, 10) ?? "—"}</td>
      <td>
        <span className="u-chip u-chip-neutral">
          {CATEGORY_LABEL[t.category]}
        </span>
      </td>
      <td className={cn(
        "text-right u-mono",
        tone === "pos" ? "text-success"
        : tone === "neg" ? "text-danger" : "text-fg",
      )}>
        {fmtUSD(t.realized_pnl)}
      </td>
      <td className="text-right u-mono">
        {t.held_days != null ? `${t.held_days}d` : "—"}
      </td>
      <td className="u-caption-2 text-fg-3 truncate" title={t.reason ?? ""}>
        {t.reason ?? "—"}
      </td>
    </tr>
  );
}
