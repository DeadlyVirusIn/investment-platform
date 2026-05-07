// Phase EXEC-VISIBILITY (revised) — operator-facing execution-status
// banner. Replaces the previous one-line "{date} signals generated;
// waiting for {date} bar to fill" copy that conflated three separate
// pieces of state:
//   * the signal batch date (already generated and on file),
//   * the bar required for next-bar fill, and
//   * the latest market data date the system has ingested.
//
// We now surface them as five labeled rows so an operator never reads
// "05/04 signals generated; waiting for 05/05 bar" as "the system
// failed to process 05/04". The row order is fixed:
//
//   1. Signal batch        — date the daily pipeline produced + status.
//   2. Required next bar   — bar needed to fill held orders + availability.
//   3. Current data        — the latest price_bar date on file (today
//                            vs not-ready-yet shown explicitly).
//   4. Pending fills       — count of orders held by the next-bar guard.
//   5. Next action         — what the operator should do, or wait for.
//
// NO execution logic changes. NO scheduler changes. NO new endpoint
// fields. Wires the same three read-only endpoints as before:
//   /api/performance/paper/pending-fills
//   /api/performance/paper/daily-suggestions
//   /api/performance/options/strategy-suggestions

import {
  usePendingFills, useDailySuggestions, useOptionsStrategySuggestions,
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

  // ----------------------------------------------------------------
  // Server-supplied fields
  // ----------------------------------------------------------------
  const signalDate = sugs.data?.as_of_date ?? null;
  const pendingCount = pending.data?.count ?? 0;
  const optionsSignalCount = optSugs.data?.count ?? 0;
  const optionsAsOf = optSugs.data?.as_of_date ?? null;

  // Server-computed next-bar target — always authoritative.
  const nextBarTarget = pending.data?.next_expected_bar_date
    ?? pending.data?.items[0]?.next_expected_bar_date
    ?? null;
  // Latest price_bar timestamp from any pending item — what the
  // system has on file already. Use ISO date prefix only.
  const latestPriceBarTs = pending.data?.items
    .map(i => i.latest_price_bar_ts)
    .filter((s): s is string => !!s)
    .sort()
    .reverse()[0] ?? null;
  const latestDate = latestPriceBarTs
    ? latestPriceBarTs.slice(0, 10)
    : null;

  // ----------------------------------------------------------------
  // Derived booleans
  // ----------------------------------------------------------------
  // The required next bar is "available" once the system has
  // ingested a price_bar dated >= the target. Lexicographic ISO
  // string comparison is safe here.
  const requiredBarAvailable = !!(
    nextBarTarget && latestDate && latestDate >= nextBarTarget
  );

  // Calendar today (UTC) — used only to hint at "today's bar
  // hasn't ingested yet" when the latest on file is older. NEVER
  // used in execution / fill logic.
  const todayIso = new Date().toISOString().slice(0, 10);

  // ----------------------------------------------------------------
  // Status-chip tone
  // ----------------------------------------------------------------
  const tone: "success" | "warning" | "neutral" =
    pendingCount > 0 ? "warning"
    : (signalDate ? "success" : "neutral");

  const chipText =
    tone === "warning"
      ? (requiredBarAvailable
          ? "Ready for paper cycle"
          : "Holding for next bar")
      : tone === "success"
        ? "Signals processed"
        : "Idle";

  // ----------------------------------------------------------------
  // Row values
  // ----------------------------------------------------------------
  const signalBatchValue = signalDate
    ? `${signalDate} — generated`
    : "no signals on file";

  const requiredBarValue = nextBarTarget
    ? (requiredBarAvailable
        ? `${nextBarTarget} — available`
        : `${nextBarTarget} — waiting for ingestion`)
    : "—";
  const requiredBarTone: "neutral" | "warning" =
    nextBarTarget && !requiredBarAvailable ? "warning" : "neutral";

  // Current data row: distinguish "latest is today" from "today's
  // bar not ingested yet" so the operator never reads a blank or
  // ambiguous "May 6 not ready" line.
  const currentDataValue = !latestDate
    ? "—"
    : latestDate >= todayIso
      ? `${latestDate} — latest available`
      : `${todayIso} — not ingested yet`;
  const currentDataSubtitle = (latestDate && latestDate < todayIso)
    ? `latest on file: ${latestDate}`
    : undefined;

  const pendingFillsValue = pendingCount === 0
    ? "0 — no orders waiting"
    : `${pendingCount} held by next-bar guard`;

  // ----------------------------------------------------------------
  // Action hint — never implies the next-bar guard is broken.
  // ----------------------------------------------------------------
  const actionHint = pendingCount === 0
    ? (signalDate
        ? "No action — all signals filled or skipped by gates."
        : "Waiting for the daily pipeline to produce suggestions.")
    : requiredBarAvailable
      ? "Run post-ingest paper cycle to process pending fills."
      : "Waiting for next daily bar ingestion.";

  return (
    <div className="u-card-tight" data-test="execution-status-card">
      <div className="flex items-center justify-between mb-3">
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
          <span className="ml-1">{chipText}</span>
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-y-2 gap-x-4">
        <LabeledRow
          label="Signal batch"
          value={signalBatchValue}
          test="exec-row-signal-batch"
        />
        <LabeledRow
          label="Required next bar"
          value={requiredBarValue}
          tone={requiredBarTone}
          test="exec-row-required-bar"
        />
        <LabeledRow
          label="Current data"
          value={currentDataValue}
          subtitle={currentDataSubtitle}
          test="exec-row-current-data"
        />
        <LabeledRow
          label="Pending fills"
          value={pendingFillsValue}
          tone={pendingCount > 0 ? "warning" : "neutral"}
          test="exec-row-pending"
        />
      </div>

      {optionsSignalCount > 0 && (
        <div
          className="mt-3 u-caption-2 text-fg-3"
          data-test="exec-options-line"
        >
          Options signals on file: {optionsSignalCount}
          {optionsAsOf ? ` · ${optionsAsOf}` : ""}
        </div>
      )}

      <div
        className="mt-3 u-caption text-fg"
        data-test="exec-next-action"
      >
        Next action: {actionHint}
      </div>

      {pendingCount > 0 && (
        <div
          className="mt-2 u-caption-2 text-fg-3"
          data-test="exec-post-ingest-hint"
        >
          Post-ingest one-shot:{" "}
          <code className="u-mono-sm">
            python -m scripts.run_post_ingest_paper_cycle --commit
          </code>{" "}
          (default safe; exploratory/options require explicit env
          opt-ins).
        </div>
      )}
    </div>
  );
}


function LabeledRow({
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
        <div className="u-caption-2 text-fg-3 truncate">
          {subtitle}
        </div>
      )}
    </div>
  );
}
