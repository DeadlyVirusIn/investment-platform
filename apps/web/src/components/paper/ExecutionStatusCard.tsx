// Phase EXEC-VISIBILITY — clear "signals ready vs next-bar pending"
// banner. Resolves the operator confusion where a fresh signal date
// (e.g. 05/04 ready, pending=14) was being read as "system ignored
// 05/04 data" when in fact it correctly held those orders for the
// next-bar fill on 05/05.
//
// Wires the three new endpoints:
//   /api/performance/paper/pending-fills
//   /api/performance/paper/daily-suggestions
//   /api/performance/options/strategy-suggestions

import {
  usePendingFills, useDailySuggestions, useOptionsStrategySuggestions,
  fmtMMDD,
} from "@/lib/paper/execution-status";
import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";


export default function ExecutionStatusCard() {
  const pending = usePendingFills();
  const sugs = useDailySuggestions();
  const optSugs = useOptionsStrategySuggestions();

  const loading = (
    pending.isLoading || sugs.isLoading || optSugs.isLoading
  );
  if (loading) {
    return (
      <div className="u-card-tight" data-test="execution-status-card">
        <div className="flex items-center justify-between">
          <Label>Execution Status</Label>
          <span className="u-caption-2">loading…</span>
        </div>
      </div>
    );
  }

  const signalDate = sugs.data?.as_of_date ?? null;
  const pendingCount = pending.data?.count ?? 0;
  const optionsSignalCount = optSugs.data?.count ?? 0;
  const optionsAsOf = optSugs.data?.as_of_date ?? null;

  // Server-computed next-bar target — always authoritative.
  const nextBarTarget = pending.data?.next_expected_bar_date
    ?? pending.data?.items[0]?.next_expected_bar_date
    ?? null;
  // Latest price_bar timestamp from any pending item — for clarity
  // about what date the system has on file already.
  const latestPriceBarTs = pending.data?.items
    .map(i => i.latest_price_bar_ts)
    .filter((s): s is string => !!s)
    .sort()
    .reverse()[0] ?? null;

  // Tone: warning when there are pending fills (fine — system is
  // doing the right thing, not stuck), success when nothing pending,
  // neutral when no signals yet.
  const tone: "success" | "warning" | "neutral" =
    pendingCount > 0 ? "warning"
    : (signalDate ? "success" : "neutral");

  const headline =
    pendingCount > 0
      ? (signalDate && nextBarTarget
          ? `${fmtMMDD(signalDate)} signals generated; waiting for `
            + `${fmtMMDD(nextBarTarget)} bar to fill.`
          : `Signals generated; waiting for next-bar data to fill.`)
      : (signalDate
          ? `${fmtMMDD(signalDate)} signals processed; no pending fills.`
          : "No signals on file yet for today.");

  const reason =
    pendingCount > 0
      ? "Held by next-bar guard — execution refuses same-bar fills."
      : (signalDate
          ? "All signals either filled or skipped by gates; "
            + "no orders are waiting on data."
          : "Daily pipeline has not produced suggestions yet.");

  return (
    <div className="u-card-tight" data-test="execution-status-card">
      <div className="flex items-center justify-between mb-2">
        <Label>Execution Status</Label>
        <span className={cn(
          "u-chip",
          tone === "success" ? "u-chip-success"
          : tone === "warning" ? "u-chip-warning"
          : "u-chip-neutral",
        )}>
          <span className={cn(
            "u-dot",
            tone === "success" ? "u-dot-success"
            : tone === "warning" ? "u-dot-warning"
            : "u-dot-neutral",
          )} />
          <span className="ml-1">
            {tone === "warning"
              ? "Holding for next bar"
              : tone === "success" ? "Signals processed"
              : "Idle"}
          </span>
        </span>
      </div>

      <div className="u-caption text-fg" data-test="exec-headline">
        {headline}
      </div>

      <div className="mt-3 grid grid-cols-2 md:grid-cols-5 gap-y-2 gap-x-4">
        <Cell
          label="Signals (stock)"
          value={signalDate ? `${fmtMMDD(signalDate)} ready` : "—"}
          test="cell-signals"
        />
        <Cell
          label="Latest price bar"
          value={
            latestPriceBarTs ? fmtMMDD(latestPriceBarTs) : "—"
          }
          test="cell-latest-bar"
        />
        <Cell
          label="Options sigs"
          value={
            optionsSignalCount > 0
              ? `${optionsSignalCount}${optionsAsOf
                  ? ` · ${fmtMMDD(optionsAsOf)}` : ""}`
              : "—"
          }
          test="cell-options"
        />
        <Cell
          label="Pending fills"
          value={String(pendingCount)}
          tone={pendingCount > 0 ? "warning" : "neutral"}
          test="cell-pending"
        />
        <Cell
          label="Live fills today"
          value="0"
          subtitle={
            pendingCount > 0
              ? "by design — next-bar guard"
              : "no orders waiting"
          }
          test="cell-live"
        />
      </div>

      <div className="mt-3 u-caption-2 text-fg-3" data-test="exec-reason">
        Reason: {reason}
      </div>

      {pendingCount > 0 && nextBarTarget && (
        <div className="mt-1 u-caption-2 text-fg-3"
             data-test="exec-next-bar">
          Waiting for {fmtMMDD(nextBarTarget)} next bar — orders fill
          on the first chain/price bar with date strictly after
          submitted_at::date. Same-bar fills are forbidden.
        </div>
      )}
    </div>
  );
}


function Cell({
  label, value, subtitle, tone = "neutral", test,
}: {
  label: string;
  value: string;
  subtitle?: string;
  tone?: "neutral" | "warning";
  test?: string;
}) {
  return (
    <div className="min-w-0" data-test={test}>
      <div className="u-caption-2 text-fg-3">{label}</div>
      <div className={cn(
        "u-mono-sm font-semibold",
        tone === "warning" ? "text-warning" : "text-fg",
      )}>
        {value}
      </div>
      {subtitle && (
        <div className="u-caption-2 text-fg-3 truncate">{subtitle}</div>
      )}
    </div>
  );
}
