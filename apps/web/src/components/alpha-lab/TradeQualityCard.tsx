// Phase B — Trade Quality card. Pre-ML diagnostic.
// Read-only. Renders /api/performance/paper/trade-quality output.
//
// CRITICAL framing: this is NOT a trading signal. The component
// shouts "pre-ML diagnostic" in the header so an operator never
// confuses the score with an expected return or recommendation.

import { useState } from "react";
import { cn } from "@/lib/cn";
import {
  useTradeQuality,
  type TradeQualityGrade,
  type TradeQualityItem,
  type TradeQualityThesis,
  type TradeQualityCompleteness,
} from "@/lib/alphaLab/hooks";


const GRADE_TONE: Record<TradeQualityGrade, string> = {
  A: "text-success",
  B: "text-success",
  C: "text-fg",
  D: "text-warning",
  F: "text-danger",
};

const THESIS_LABEL: Record<TradeQualityThesis, string> = {
  open_positive: "Open · positive",
  open_negative: "Open · negative",
  stopped_out: "Stopped out",
  take_profit: "Take-profit",
  max_hold: "Max-hold",
  closed_other: "Closed · other",
  pending_next_bar: "Pending next bar",
  insufficient_data: "Insufficient data",
};

const COMPLETENESS_LABEL: Record<TradeQualityCompleteness, string> = {
  full: "full",
  partial: "partial",
  low: "low",
};

const COMPLETENESS_TONE: Record<TradeQualityCompleteness, string> = {
  full: "text-fg-3",
  partial: "text-warning",
  low: "text-danger",
};


export default function TradeQualityCard() {
  const q = useTradeQuality(50);
  const [expanded, setExpanded] = useState<string | null>(null);

  if (q.isLoading) {
    return (
      <Shell>
        <p className="u-caption italic">Loading quality scores…</p>
      </Shell>
    );
  }
  if (q.error || !q.data) {
    return (
      <Shell>
        <p className="u-caption text-danger">
          Trade-quality endpoint unreachable. This card is
          read-only — execution is unaffected.
        </p>
      </Shell>
    );
  }
  const d = q.data;
  if (d.n_items === 0) {
    return (
      <Shell n={0} avg={null}>
        <p className="u-caption">
          No eligible paper trades to score yet.
        </p>
      </Shell>
    );
  }

  return (
    <Shell n={d.n_items} avg={d.average_score}>
      {/* Distribution strips */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <DistBlock
          label="Grade"
          rows={(["A", "B", "C", "D", "F"] as const).map((g) => ({
            key: g,
            value: d.grade_distribution[g] ?? 0,
            tone: GRADE_TONE[g],
          }))}
        />
        <DistBlock
          label="Thesis"
          rows={Object.entries(d.thesis_distribution).map(
            ([k, v]) => ({
              key: THESIS_LABEL[k as TradeQualityThesis] ?? k,
              value: v ?? 0,
            }),
          )}
        />
        <DistBlock
          label="Data completeness"
          rows={(["full", "partial", "low"] as const).map((c) => ({
            key: COMPLETENESS_LABEL[c],
            value: d.completeness_distribution[c] ?? 0,
            tone: COMPLETENESS_TONE[c],
          }))}
        />
      </div>

      <table
        className="u-table"
        data-test="trade-quality-table"
      >
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Portfolio</th>
            <th>Status</th>
            <th>Thesis</th>
            <th className="text-right">Score</th>
            <th className="text-right">Grade</th>
            <th>Completeness</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {d.items.map((it) => (
            <Row
              key={it.trade_id}
              it={it}
              expanded={expanded === it.trade_id}
              onToggle={() => setExpanded(
                expanded === it.trade_id ? null : it.trade_id,
              )}
            />
          ))}
        </tbody>
      </table>
    </Shell>
  );
}


function Shell({
  n, avg, children,
}: {
  n?: number;
  avg?: number | null;
  children: React.ReactNode;
}) {
  return (
    <section
      data-test="trade-quality-card"
      className="rounded-md border border-zinc-700 bg-zinc-900/40 p-4"
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-zinc-100">
            Trade Quality
          </h2>
          <div className="mt-0.5 text-[10px] uppercase tracking-wide text-zinc-500">
            source: GET /performance/paper/trade-quality
          </div>
        </div>
        <span className="rounded border border-amber-700/60 bg-amber-900/20 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-300">
          pre-ML diagnostic · not a trading signal
        </span>
      </header>
      {n !== undefined && (
        <div className="mb-3 grid grid-cols-2 md:grid-cols-3 gap-3">
          <Cell label="Items scored" value={String(n)} />
          <Cell
            label="Average score"
            value={avg != null ? avg.toFixed(1) : "—"}
          />
          <Cell
            label="Grade scale"
            value="A 85+ · B 70+ · C 55+ · D 40+"
            small
          />
        </div>
      )}
      {children}
      <p className="mt-3 text-[11px] text-zinc-500">
        Score components: Entry (20) + Return (30) + Hold (15) +
        Exit/Status (25) + Completeness (10) = 100. Inputs come
        verbatim from <code>paper_trade</code>,{" "}
        <code>paper_position</code>, and the latest{" "}
        <code>price_bar</code>; nothing is fabricated. Missing
        data drops both the relevant component and the
        completeness flag — never replaced with an invented value.
      </p>
    </section>
  );
}


function Cell({
  label, value, small = false,
}: {
  label: string; value: string; small?: boolean;
}) {
  return (
    <div className="rounded border border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className={cn(
        small ? "text-xs" : "text-lg",
        "font-semibold mt-0.5 text-zinc-100",
      )}>
        {value}
      </div>
    </div>
  );
}


function DistBlock({
  label, rows,
}: {
  label: string;
  rows: Array<{ key: string; value: number; tone?: string }>;
}) {
  return (
    <div className="rounded border border-zinc-800 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
        {label}
      </div>
      <div className="space-y-0.5">
        {rows.map((r) => (
          <div
            key={r.key}
            className="flex items-baseline justify-between text-xs"
          >
            <span className={r.tone ?? "text-fg-3"}>{r.key}</span>
            <span className="tabular-nums text-zinc-100 font-semibold">
              {r.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}


function Row({
  it, expanded, onToggle,
}: {
  it: TradeQualityItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr>
        <td className="u-mono">{it.symbol}</td>
        <td className="u-caption-2 text-fg-3">
          {it.portfolio_name}
        </td>
        <td>
          <span className={cn(
            "u-chip",
            it.is_open ? "u-chip-neutral" : "u-chip-success",
          )}>
            {it.is_open ? "open" : "closed"}
          </span>
        </td>
        <td className="u-caption-2">
          {THESIS_LABEL[it.thesis] ?? it.thesis}
        </td>
        <td className="text-right u-mono">{it.score}</td>
        <td className={cn(
          "text-right u-mono font-semibold",
          GRADE_TONE[it.grade],
        )}>
          {it.grade}
        </td>
        <td className={cn(
          "u-caption-2",
          COMPLETENESS_TONE[it.completeness],
        )}>
          {COMPLETENESS_LABEL[it.completeness]}
        </td>
        <td>
          <button
            type="button"
            onClick={onToggle}
            className="text-xs text-fg-3 hover:text-fg"
          >
            {expanded ? "hide" : "why"}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8} className="bg-zinc-950/40 px-4 py-3">
            <ul className="space-y-1 text-xs text-zinc-300">
              {it.reasons.map((r, i) => (
                <li key={i}>· {r}</li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}
