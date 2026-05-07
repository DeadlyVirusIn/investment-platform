// DECISIONS (Phase UI-INTEL) — 3-column audit workstation.
// COL 1: Timeline with filters
// COL 2: Decision Detail (summary, plain-english reasoning, production inputs,
//        blocking logic, diagnostic snapshot)
// COL 3: Outcome + Pattern Context (realized outcome, attached anomalies,
//        historically similar decisions)

import { useMemo, useState } from "react";
import {
  usePaperTrades, useDecision, useAnomalies, useCurrentState,
} from "@/lib/operator/hooks";
import { usePendingFills } from "@/lib/paper/execution-status";
import {
  Card, Pill, Divider, fmtPct, toneForNumber, Skeleton,
} from "@/components/ui/primitives";
import FactorAttributionMini from "@/components/decisions/FactorAttributionMini";
import type {
  TradeRow, CurrentState, DecisionRow, AnomalyEvent,
} from "@/lib/operator/types";
import { cn } from "@/lib/cn";
// UX-1 — plain-English page intro card.
// UX-1 Commit J — focus guidance + collapsible engineering source.
import { PageGuide, AdvancedDetails } from "@/components/novice";

// Filter set — paper-trading aware. Engine A/B retained for the
// rare legacy row that still carries those engine values; the
// active paper-trading data has engine="paper" and is shown via
// "All" / "Open" / "Live" / "Replay".
type Filter = "all" | "live" | "replay" | "open" | "anom";

// UX-1 — plain-English filter labels. Filter `id` keys are
// preserved (data-test selectors and behavior unchanged).
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all",    label: "All" },
  { id: "live",   label: "Real" },
  { id: "replay", label: "Recovered" },
  { id: "open",   label: "Still open" },
  { id: "anom",   label: "Flagged" },
];

export default function Decisions() {
  const { data: trades } = usePaperTrades();
  const { data: state } = useCurrentState();
  const { data: anomalies } = useAnomalies("open");
  const { data: pending } = usePendingFills();
  const [filter, setFilter] = useState<Filter>("all");
  const [selected, setSelected] = useState<TradeRow | null>(null);

  const totals = useMemo(() => {
    const all = trades ?? [];
    return {
      total: all.length,
      live: all.filter(t => !t.is_replay).length,
      replay: all.filter(t => !!t.is_replay).length,
      open: all.filter(t => t.status === "open").length,
      pending: pending?.count ?? 0,
    };
  }, [trades, pending]);

  const anomByDate = useMemo(() => {
    const m = new Map<string, AnomalyEvent[]>();
    for (const a of anomalies ?? []) {
      const list = m.get(a.as_of_date) ?? [];
      list.push(a);
      m.set(a.as_of_date, list);
    }
    return m;
  }, [anomalies]);

  const filtered = useMemo(() => {
    const all = trades ?? [];
    switch (filter) {
      case "live":   return all.filter(t => !t.is_replay);
      case "replay": return all.filter(t => !!t.is_replay);
      case "open":   return all.filter(t => t.status === "open");
      case "anom":   return all.filter(t => anomByDate.has(t.entry_date));
      default:       return all;
    }
  }, [trades, filter, anomByDate]);

  const hasAny = (trades?.length ?? 0) > 0;

  return (
    <div className="max-w-[1680px] mx-auto px-8 py-8">
      <header className="mb-6 space-y-3">
        <PageGuide
          eyebrow="Decisions"
          title="Trade Decisions"
          subtitle="See why trades were placed or skipped."
          firstLook={
            <>
              Pick any row in the timeline below to read the
              reason in plain English. Latest day first.
            </>
          }
        />

        {/* UX-1 Commit J — Start-here focus card. Calmer framing  */}
        {/* for a page that previously read like an audit         */}
        {/* workstation.                                          */}
        <section
          className="u-card-tight"
          data-test="decisions-start-here"
          style={{ padding: "12px 16px" }}
        >
          <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
            How to read this page
          </div>
          <ol className="u-body text-fg space-y-1 list-decimal pl-5">
            <li>
              <strong>Pick any row</strong> in the timeline on
              the left.
            </li>
            <li>
              <strong>Read the reason</strong> in the centre — a
              plain-English explanation of why the system bought
              or skipped this candidate.
            </li>
            <li>
              <strong>Outcome &amp; pattern context</strong> on
              the right shows how similar past trades behaved.
            </li>
          </ol>
          <p className="u-caption-2 text-fg-3 mt-2">
            Safe to ignore for now: the engineering snapshot, the
            inputs table on the detail panel, and the
            recovered-history filter. Every row is read-only;
            nothing here trades on your behalf.
          </p>
        </section>

        {/* UX-1 Commit J — calm interpretation card. Tells the  */}
        {/* operator whether anything needs attention BEFORE the  */}
        {/* timeline density is shown.                            */}
        <DecisionsCalmCard
          total={totals.total}
          openCount={totals.open}
          pending={totals.pending}
          replayCount={totals.replay}
          loaded={trades !== undefined}
        />

        {/* Truth-banner row (existing data-test preserved).      */}
        {/* Now reads as quieter SECONDARY context after the calm */}
        {/* card has answered "is this okay?".                    */}
        <div
          className="flex flex-wrap items-center gap-2 u-caption-2"
          data-test="decisions-truth-banner"
        >
          <span className="u-chip u-chip-neutral">
            <span className="u-dot u-dot-neutral" />
            <span className="ml-1">
              All decisions {totals.total}
            </span>
          </span>
          <span
            className="u-chip u-chip-accent"
            title="Trades that have not closed yet."
          >
            <span className="u-dot u-dot-accent" />
            <span className="ml-1">Still open {totals.open}</span>
          </span>
          {totals.pending > 0 && (
            <span
              className="u-chip u-chip-warning"
              title="These trades matched the strategy and passed safety checks. They are scheduled to fill once tomorrow's market data arrives — this is intentional, not stuck."
            >
              <span className="u-dot u-dot-warning" />
              <span className="ml-1">
                Waiting for tomorrow's market data {totals.pending}
              </span>
            </span>
          )}
          <span className="ml-2 text-fg-3">
            · {totals.live} real · {totals.replay} recovered
            from backup data
          </span>
        </div>

        <AdvancedDetails label="Where this data comes from">
          <p className="u-caption-2 text-fg-3 max-w-3xl">
            Source: <code>paper_trade</code> joined to{" "}
            <code>paper_position</code>. Recovered-history rows
            (reconstructed from backup data) are tagged separately.
            Trades waiting for tomorrow's market data are held
            intentionally by the next-bar fill rule — they are not
            stuck.
          </p>
        </AdvancedDetails>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)_420px]
                        gap-6 h-[calc(100vh-240px)] min-h-[680px]">
        {/* ============== COL 1: TIMELINE ============== */}
        <div className="flex flex-col min-h-0">
          <div className="mb-3">
            <div className="flex items-center justify-between mb-3">
              <div className="u-label">Timeline</div>
              <span className="u-caption-2 font-mono">
                {filtered.length} / {trades?.length ?? 0}
              </span>
            </div>
            <div className="flex flex-wrap gap-1">
              {FILTERS.map(f => (
                <button key={f.id} onClick={() => setFilter(f.id)}
                  className={cn(
                    "px-3 py-1.5 text-[11px] uppercase tracking-wider",
                    "font-semibold rounded-md border transition-colors",
                    filter === f.id
                      ? "bg-accent-subtle text-accent border-b3"
                      : "bg-transparent text-fg-3 border-b1 hover:text-fg-2",
                  )}
                  style={filter === f.id
                    ? { borderColor: "rgba(75,139,255,0.45)" } : {}}>
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Phase 4 — Virtualization boundary.
              Current row count <200 in production; render-list is fine.
              When count >200 OR perf lag is measurable, swap this div +
              .map() for `react-window` FixedSizeList. Keyboard nav must
              remain (button[role=button] children, selected via
              setSelectedId), and the parent flex-1 scroll container must
              own height (already does via overflow-y-auto). */}
          <div className="flex-1 overflow-y-auto pr-1 space-y-2">
            {!trades ? (
              <>
                <Skeleton className="h-20" /><Skeleton className="h-20" />
                <Skeleton className="h-20" />
              </>
            ) : filtered.length === 0 ? (
              hasAny
                ? <EmptyFilter />
                : <TodaysDecisionFallback state={state} />
            ) : filtered.map(t => (
              <TimelineEntry key={t.trade_id} t={t}
                selected={selected?.trade_id === t.trade_id}
                hasAnomaly={anomByDate.has(t.entry_date)}
                onClick={() => setSelected(t)} />
            ))}
          </div>
        </div>

        {/* ============== COL 2: DECISION DETAIL ============== */}
        <div className="overflow-y-auto pr-1">
          {hasAny
            ? <DecisionDetail trade={selected} />
            : <TodaysDecisionDetail state={state} />}
        </div>

        {/* ============== COL 3: OUTCOME + PATTERN CONTEXT ============== */}
        <div className="overflow-y-auto pr-1">
          {hasAny
            ? <OutcomePatternPanel trade={selected}
                                   allTrades={trades ?? []}
                                   anomByDate={anomByDate} />
            : <PatternEmptyPanel />}
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// COL 1 — timeline entries
// =========================================================================

function TimelineEntry({
  t, selected, hasAnomaly, onClick,
}: {
  t: TradeRow; selected: boolean; hasAnomaly: boolean; onClick: () => void;
}) {
  const tone = toneForNumber(t.net_ret_pct ?? 0);
  const cardCls = t.status === "open" ? "is-open"
    : tone === "pos" ? "is-pos" : tone === "neg" ? "is-neg" : "";
  const retCls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg-2";

  return (
    <button onClick={onClick}
      className={cn("u-trade-card text-left", cardCls,
                    selected && "is-selected")}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="u-mono font-semibold truncate">
            {t.instrument}
          </span>
          <span className="u-mono-sm text-fg-3">{t.entry_date}</span>
        </div>
        <span className={cn("u-num-md font-bold shrink-0", retCls)}>
          {t.net_ret_pct != null ? fmtPct(t.net_ret_pct) : "—"}
        </span>
      </div>
      <div className="flex items-center justify-between u-caption-2">
        <span
          className="uppercase tracking-wider font-semibold"
          title="The plain-English idea behind this trade."
        >
          {t.engine === "A"
            ? "Buy-the-dip"
            : t.engine === "B"
              ? "Defensive"
              : t.regime_at_entry || "paper"}
        </span>
        <span className="u-mono-sm">
          {t.days_held !== null ? `${t.days_held}d held` : "still open"}
        </span>
      </div>
      {/* UX-1 Commit L — chip dedupe. Drop redundant "real" chip   */}
      {/* (the default state needs no badge); the recovered-from-   */}
      {/* backup tag still fires when applicable. Status + anomaly  */}
      {/* chips kept since they carry independent signal.            */}
      <div className="flex gap-1.5 flex-wrap mt-2">
        {t.status === "open" &&
          <span className="u-chip u-chip-neutral">still open</span>}
        {t.status === "closed" &&
          <span className="u-chip u-chip-success">closed</span>}
        {t.is_replay && (
          <span
            className="u-chip u-chip-warning"
            title="Recovered from backup data — not live trading."
          >
            recovered
          </span>
        )}
        {hasAnomaly &&
          <span
            className="u-chip u-chip-danger"
            title="Something unusual was detected for this date — open the row for detail."
          >
            <span className="u-dot u-dot-danger u-dot-pulse" />flagged
          </span>}
      </div>
    </button>
  );
}

function EmptyFilter() {
  return (
    <div className="u-card-tight">
      <div className="u-caption-2 italic">
        🌱 Nothing matches this filter yet. Try "All".
      </div>
    </div>
  );
}

function TodaysDecisionFallback({ state }: {
  state: CurrentState | undefined;
}) {
  if (!state) return <Skeleton className="h-24" />;
  // UX-1 — humanized strategy + status copy. "fire" = the system
  // would buy today; "stood by" = nothing matched the strategy.
  const strategyLabel = state.engine === "A"
    ? "Buy-the-dip strategy"
    : state.engine === "B"
      ? "Defensive strategy"
      : "system";
  return (
    <div className="u-card-tight"
         style={{ background: "var(--accent-subtle)",
                  borderColor: "rgba(75,139,255,0.4)" }}>
      <div className="flex items-center gap-2 mb-2">
        <Pill tone="accent" dot>TODAY</Pill>
        <span className="u-mono-sm">{state.as_of_date}</span>
      </div>
      <div className="u-body-fg font-medium mb-2">
        {state.fire
          ? `${strategyLabel} would buy today`
          : "No matches today — system stood by"}
      </div>
      <div className="u-caption-2">
        No trades recorded yet. The line above is today's plan;
        the actual fill (if any) waits for the next price bar
        before it appears in the timeline.
      </div>
    </div>
  );
}

// =========================================================================
// COL 2 — DECISION DETAIL
// =========================================================================

function DecisionDetail({ trade }: { trade: TradeRow | null }) {
  const asOf = trade?.entry_date ?? null;
  const { data: decision } = useDecision(asOf);

  if (!trade) {
    return (
      <Card size="md" className="h-full flex flex-col justify-center items-center">
        <div className="u-empty w-full">
          <div className="text-fg-4 text-3xl mb-3">◁</div>
          <div className="u-body-fg font-medium mb-1">
            Pick a decision on the left
          </div>
          <div className="u-caption-2 max-w-xs text-center">
            The plain-English reason, the inputs the system used,
            any safety rules that fired, and a short history of
            similar past trades will appear here.
          </div>
        </div>
      </Card>
    );
  }

  // UX-1 messaging:
  //   * Strategy A / B fills came from the legacy selector path and
  //     advertise their strategy + market condition in the header.
  //   * Account-path fills (paper_trade) carry engine="paper" — these
  //     ARE real executed trades. They predate the decision_log
  //     retention window OR were entered by auto_trader without a
  //     captured decision row, so the header says the trade ran but
  //     the original review notes weren't saved.
  //   * Anything else (engine=null, "none") with no decision row is
  //     treated as backfilled.
  const isAccountPath = trade.engine === "paper";
  const isLegacyEngine = trade.engine === "A" || trade.engine === "B";
  const engineLabel = isLegacyEngine
    ? (trade.engine === "A"
        ? "Buy-the-dip strategy"
        : "Defensive strategy")
    : isAccountPath
      ? "Paper trade"
      : "Older trade — full review notes unavailable";
  const subLabel = isLegacyEngine
    ? `Bought · ${trade.regime_at_entry ?? "market condition unknown"} · `
      + `review version ${trade.decision_version ?? "—"}`
    : isAccountPath
      ? (trade.status === "closed"
          ? `Bought ${trade.entry_date} · closed ${trade.exit_date ?? "—"}`
            + ` · ${trade.reason ?? "no reason recorded"}`
          : `Bought ${trade.entry_date} · `
            + `${trade.reason ?? "no reason recorded"}`)
      : "Older row — the review notes for this date are no longer kept.";

  return (
    <Card size="md" className="space-y-6">
      {/* A — decision summary */}
      <header>
        <div className="flex items-center gap-2 mb-3">
          <span className="u-chip u-chip-accent">Decision</span>
          <span className="u-mono-sm">{trade.entry_date}</span>
          {trade.status === "open" &&
            <span className="u-chip u-chip-neutral">still open</span>}
          {trade.status === "closed" &&
            <span className="u-chip u-chip-success">closed</span>}
          {!isLegacyEngine && (
            <span
              className="u-chip u-chip-warning"
              title="The trade ran, but the original review notes weren't saved. The trade itself is fine — only the explanation is missing."
            >
              review notes unavailable
            </span>
          )}
        </div>
        <h2 className="u-title-lg" style={{ fontSize: 24 }}>
          {engineLabel}
        </h2>
        <div className="u-caption text-fg-2 mt-2">
          {subLabel}
        </div>
      </header>

      <Divider />

      {/* B — plain-english reasoning */}
      <Section title="Why this happened">
        <p className="u-body-fg leading-relaxed">
          {humanReasoning(trade, decision ?? null)}
        </p>
        {decision?.reason && (
          <pre className="u-mono-sm bg-sunken rounded-md p-3 mt-3 whitespace-pre-wrap
                           leading-relaxed text-fg-2">
            {decision.reason}
          </pre>
        )}
      </Section>

      {/* C — production inputs */}
      {decision?.factor_attribution && (
        <Section title="What pushed the score up or down"
                 hint="Deterministic 7-input breakdown (review only)">
          <FactorAttributionMini
            attribution={decision.factor_attribution as any} />
        </Section>
      )}

      <Section title="Inputs the system looked at"
               hint="Raw values the strategy used to decide">
        <KVTable data={decision?.inputs_used ?? {}} />
      </Section>

      {/* D — blocking logic */}
      <Section title="Safety checks"
               hint="Whether any pre-trade rule skipped this trade for safety">
        <BlockingPanel decision={decision ?? null} trade={trade} />
      </Section>

      {/* E — diagnostic snapshot */}
      {decision?.diagnostic_snapshot
       && Object.keys(decision.diagnostic_snapshot).length > 0 && (
        <Section title="Engineering snapshot"
                 hint="Observed but NOT used by the trading rule"
                 warn>
          <KVTable data={decision.diagnostic_snapshot} diagnostic />
        </Section>
      )}
    </Card>
  );
}

function Section({
  title, hint, warn = false, children,
}: {
  title: string; hint?: string; warn?: boolean; children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-3">
        <div className={cn("u-label", warn && "text-warning")}>{title}</div>
        {hint && <div className={cn("u-caption-2 mt-1",
                                      warn && "text-warning")}>{hint}</div>}
      </div>
      {children}
    </div>
  );
}

function KVTable({
  data, diagnostic = false,
}: { data: Record<string, unknown>; diagnostic?: boolean }) {
  const entries = Object.entries(data ?? {});
  if (entries.length === 0) {
    return (
      <div className={cn("u-card-tight u-caption-2 italic",
                          diagnostic && "u-nonprod-ribbon")}>
        (empty)
      </div>
    );
  }
  return (
    <div className={cn(
      "rounded-md border divide-y overflow-hidden",
      diagnostic && "u-nonprod-ribbon",
    )} style={!diagnostic
      ? { borderColor: "var(--border-2)", background: "var(--sunken)" }
      : {}}>
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center justify-between px-4 py-2.5">
          <span className="u-caption text-fg-2" title={k}>
            {humanizeKey(k)}
          </span>
          <span className={cn("u-mono-sm",
            diagnostic && "text-warning")}>{formatVal(v)}</span>
        </div>
      ))}
    </div>
  );
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Number.isInteger(v)
    ? v.toString() : v.toFixed(4);
  return String(v);
}

// Phase 3 — humanize known snapshot keys for readability while keeping
// raw key as title attribute for power users / debugging.
const KEY_LABELS: Record<string, string> = {
  alpha_rule_snapshot: "Alpha Rule Snapshot",
  alpha_rule_size_multiplier: "Alpha Rule Size ×",
  context_multiplier: "Context Multiplier",
  context_key: "Context Key",
  similarity: "Similarity",
  similarity_multiplier: "Similarity Multiplier",
  similarity_matched: "Similarity Matched",
  ml_hybrid: "ML Hybrid",
  ml_shadow_multiplier: "ML Shadow Multiplier",
  ml_shadow_available: "ML Shadow Available",
  ml_hybrid_action: "ML Hybrid Action",
  ml_hybrid_reason: "ML Hybrid Reason",
  ml_multiplier: "ML Multiplier",
  paper_size_multiplier: "Paper Size ×",
  entry_price_source: "Entry Price Source",
  entry_price_timestamp: "Entry Price Timestamp",
  exploratory_paper: "Exploratory Paper",
  exploratory_size_multiplier: "Exploratory Size ×",
  gates_failed: "Gates Failed",
  gates_passed: "Gates Passed",
  gates_total: "Gates Total",
  gate_mode: "Gate Mode",
  stress_regime: "Stress Regime",
  directional_regime: "Directional Regime",
  vol_z: "Vol Z-Score",
  credit_stable: "Credit Stable",
  rates_calm: "Rates Calm",
  vrp_supportive: "VRP Supportive",
  liquidity_expanding: "Liquidity Expanding",
  feature_confidence: "Feature Confidence",
  data_confidence: "Data Confidence",
  near_earnings: "Near Earnings",
  catalyst_snapshot: "Catalyst Snapshot",
  failure_analysis: "Failure Analysis",
  execution_quality: "Execution Quality",
  decision_version: "Decision Version",
  net_ret_pct: "Net Return %",
  gross_ret_pct: "Gross Return %",
  days_held: "Days Held",
  applied_rules: "Applied Rules",
};

function humanizeKey(k: string): string {
  if (KEY_LABELS[k]) return KEY_LABELS[k];
  // Fallback: snake_case → Title Case
  return k
    .split("_")
    .map(w => w.length === 0
      ? w
      : w[0].toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function BlockingPanel({
  decision, trade,
}: { decision: DecisionRow | null; trade: TradeRow }) {
  if (!decision) {
    // UX-1 — humanized fallback. Trade exists in paper_trade but
    // decision_log row was not retained for this date (common
    // for backfilled / account-path fills). Make it clear the
    // trade itself ran fine.
    const isAccountPath = trade.engine === "paper";
    return (
      <div className="u-caption-2 italic">
        {isAccountPath
          ? "This trade ran normally. The original safety-check "
            + "notes weren't saved, so we can't show which rules "
            + "passed — but the trade itself is fine."
          : `Older trade — review notes for `
            + `${trade.entry_date} are no longer kept on file.`}
      </div>
    );
  }
  if (decision.blocked_by) {
    return (
      <div className="u-card-tight" style={{
        background: "var(--warning-muted)",
        borderColor: "rgba(248,166,56,0.4)",
      }}>
        <div className="u-label-sm mb-1 text-warning">
          Skipped for safety
        </div>
        <div className="u-body-fg text-warning">
          This candidate matched the strategy, but a safety rule
          stepped in to skip it. No action needed. Reason:{" "}
          <span className="font-semibold">{decision.blocked_by}</span>
        </div>
      </div>
    );
  }
  // Show which contexts were True vs False
  const ctx = decision.context_values ?? {};
  return (
    <div className="space-y-2">
      <div className="u-caption text-fg-2">
        All safety checks passed — the trade was allowed to proceed.
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(ctx).map(([k, v]) => (
          <div key={k} className="flex items-center justify-between
                                    px-3 py-2 u-card-tight">
            <span className="u-mono-sm">{k}</span>
            <Pill tone={v ? "success" : "neutral"}>
              {String(v)}
            </Pill>
          </div>
        ))}
      </div>
    </div>
  );
}

function humanReasoning(trade: TradeRow, decision: DecisionRow | null): string {
  const isAccountPath = trade.engine === "paper";
  const isLegacyEngine = trade.engine === "A" || trade.engine === "B";
  const outcome = trade.net_ret_pct === null
    ? "Position still open."
    : trade.net_ret_pct > 0
      ? `Closed at ${fmtPct(trade.net_ret_pct)} net — thesis confirmed.`
      : `Closed at ${fmtPct(trade.net_ret_pct)} net — thesis rejected.`;

  // Account-path / unknown-engine trades have a real fill but no
  // captured decision_log row. Avoid the misleading "no engine
  // fired long" phrasing — a buy DID execute at trade.entry_price.
  if (!isLegacyEngine) {
    const stem = isAccountPath
      ? `Paper trade (${trade.engine}) executed on ${trade.entry_date} at ` +
        `$${trade.entry_price.toFixed(2)}.`
      : `Backfilled trade — decision context unavailable for ` +
        `${trade.entry_date}.`;
    const reasonText = trade.reason
      ? ` Reason: ${trade.reason}.`
      : "";
    return `${stem}${reasonText} ${outcome}`;
  }

  const engine = trade.engine === "A"
    ? "Engine A (mean reversion)"
    : "Engine B (credit + rates alignment)";
  const regime = trade.regime_at_entry === "stress" ? "stress regime"
    : trade.regime_at_entry === "directional" ? "directional regime"
    : "neutral regime";
  const ctx = decision?.context_values ?? {};
  const ctxTrue = Object.entries(ctx).filter(([, v]) => v).map(([k]) => k);
  const gatesText = ctxTrue.length > 0
    ? ` Supporting contexts: ${ctxTrue.join(", ")}.`
    : "";
  return `${engine} fired long into ${regime} on ${trade.entry_date}.` +
    gatesText + ` ${outcome}`;
}

// =========================================================================
// COL 3 — OUTCOME + PATTERN CONTEXT
// =========================================================================

function OutcomePatternPanel({
  trade, allTrades, anomByDate,
}: {
  trade: TradeRow | null;
  allTrades: TradeRow[];
  anomByDate: Map<string, AnomalyEvent[]>;
}) {
  if (!trade) {
    return <PatternEmptyPanel />;
  }
  const attached = anomByDate.get(trade.entry_date) ?? [];
  const pattern = derivePattern(trade, allTrades);

  return (
    <div className="space-y-4">
      {/* A — realized outcome */}
      <Card size="md">
        <Section title="Realized Outcome">
          <OutcomeBlock trade={trade} pattern={pattern} />
        </Section>
      </Card>

      {/* B — attached anomalies */}
      <Card size="md">
        <Section title="Attached Anomalies"
                 hint="Flagged during the trade's lifetime">
          {attached.length === 0 ? (
            <div className="flex items-center gap-2">
              <span className="u-dot u-dot-success" />
              <span className="u-caption text-fg-2">No flags raised.</span>
            </div>
          ) : (
            <ul className="space-y-2.5">
              {attached.map(a => (
                <li key={a.id} className="flex items-start gap-2">
                  <Pill tone={a.severity === "critical" ? "danger"
                               : a.severity === "warning" ? "warning" : "accent"}>
                    {a.severity}
                  </Pill>
                  <div className="flex-1 min-w-0">
                    <div className="u-caption text-fg font-medium">{a.title}</div>
                    <div className="u-caption-2 mt-0.5">{a.description}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </Card>

      {/* C — pattern context */}
      <Card size="md">
        <Section title="Pattern Context"
                 hint={`Historically similar decisions (same engine + regime, excluding this trade)`}>
          <PatternBlock trade={trade} pattern={pattern} />
        </Section>
      </Card>
    </div>
  );
}

interface Pattern {
  n: number;
  winRate: number | null;
  avgRet: number | null;
  stdRet: number | null;
  avgDuration: number | null;
  comparable: TradeRow[];
}

function derivePattern(trade: TradeRow, all: TradeRow[]): Pattern {
  const peers = all.filter(t =>
    t.trade_id !== trade.trade_id &&
    t.engine === trade.engine &&
    t.regime_at_entry === trade.regime_at_entry &&
    t.status === "closed" &&
    t.net_ret_pct !== null,
  );
  if (peers.length === 0) {
    return { n: 0, winRate: null, avgRet: null, stdRet: null,
             avgDuration: null, comparable: [] };
  }
  const rets = peers.map(p => p.net_ret_pct!);
  const wins = rets.filter(r => r > 0).length;
  const avg = rets.reduce((a, b) => a + b, 0) / rets.length;
  const variance = rets.reduce((s, r) => s + (r - avg) ** 2, 0) / rets.length;
  const std = Math.sqrt(variance);
  const durations = peers
    .filter(p => p.days_held !== null)
    .map(p => p.days_held!);
  const avgDur = durations.length > 0
    ? durations.reduce((a, b) => a + b, 0) / durations.length
    : null;
  return {
    n: peers.length,
    winRate: wins / peers.length,
    avgRet: avg,
    stdRet: std,
    avgDuration: avgDur,
    comparable: peers.slice(0, 4),
  };
}

function OutcomeBlock({
  trade, pattern,
}: { trade: TradeRow; pattern: Pattern }) {
  const realized = trade.net_ret_pct;
  const gross = trade.gross_ret_pct;
  const slippage = (gross !== null && realized !== null)
    ? gross - realized : null;
  const expected = pattern.avgRet;
  const error = (expected !== null && realized !== null)
    ? realized - expected : null;
  const zScore = (expected !== null && pattern.stdRet !== null
                   && pattern.stdRet > 0 && realized !== null)
    ? (realized - expected) / pattern.stdRet : null;

  const scale = Math.max(Math.abs(realized ?? 0), Math.abs(expected ?? 0), 0.1);

  return (
    <div className="space-y-4">
      {/* Actual vs expected bar comparison */}
      {realized !== null && expected !== null && (
        <div className="space-y-3">
          <CompareBar label="Actual"     value={realized} scale={scale} bold />
          <CompareBar label="Peers avg"  value={expected} scale={scale} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <MetricKV label="Realized"
                  value={fmtPct(realized)}
                  tone={toneForNumber(realized ?? 0)} />
        <MetricKV label="Expected (peers)"
                  value={expected !== null ? fmtPct(expected) : "—"}
                  tone="neutral" />
        <MetricKV label="Edge vs peers"
                  value={error !== null ? fmtPct(error) : "—"}
                  tone={toneForNumber(error ?? 0)} />
        <MetricKV label="Slippage"
                  value={slippage !== null ? fmtPct(slippage) : "—"}
                  tone={(slippage ?? 0) > 0.1 ? "warn" : "neutral"} />
      </div>
      {zScore !== null && (
        <div className="u-caption">
          Outcome is <span className={cn("font-semibold u-num-sm",
            Math.abs(zScore) > 1.5 ? "text-warning" : "text-fg")}>
            {zScore > 0 ? "+" : ""}{zScore.toFixed(2)}σ
          </span> relative to peers
          {Math.abs(zScore) > 1.5 && " — outlier"}.
        </div>
      )}
    </div>
  );
}

function CompareBar({
  label, value, scale, bold = false,
}: { label: string; value: number; scale: number; bold?: boolean }) {
  const tone = toneForNumber(value);
  const pct = Math.min(100, Math.abs(value) / scale * 100);
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg-2";
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className={cn("u-caption",
                             bold ? "text-fg font-semibold" : "text-fg-2")}>
          {label}
        </span>
        <span className={cn("u-num-sm font-semibold", cls)}>
          {fmtPct(value)}
        </span>
      </div>
      <div className="u-bar-track is-thick">
        <div className={cn("u-bar-fill",
          tone === "pos" ? "is-pos" : tone === "neg" ? "is-neg" : "")}
          style={{ left: 0, width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MetricKV({
  label, value, tone,
}: {
  label: string; value: string;
  tone: "pos" | "neg" | "neutral" | "warn";
}) {
  const cls = {
    pos: "text-success", neg: "text-danger",
    warn: "text-warning", neutral: "text-fg",
  }[tone];
  return (
    <div className="u-card-tight">
      <div className="u-label-sm mb-1.5">{label}</div>
      <div className={cn("u-num-sm font-semibold", cls)}>{value}</div>
    </div>
  );
}

function PatternBlock({
  trade, pattern,
}: { trade: TradeRow; pattern: Pattern }) {
  if (pattern.n === 0) {
    return (
      <div className="u-caption-2 italic">
        No closed peer trades for Engine {trade.engine} in
        {" "}{trade.regime_at_entry} regime yet.
      </div>
    );
  }
  const wrTone = (pattern.winRate ?? 0) >= 0.55 ? "text-success"
    : (pattern.winRate ?? 0) < 0.4 ? "text-danger" : "text-fg";
  const retTone = (pattern.avgRet ?? 0) > 0 ? "text-success"
    : (pattern.avgRet ?? 0) < 0 ? "text-danger" : "text-fg";

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <MetricKV label="Peers" value={String(pattern.n)} tone="neutral" />
        <MetricKV label="Win rate"
                  value={pattern.winRate !== null
                    ? `${(pattern.winRate * 100).toFixed(0)}%` : "—"}
                  tone={(pattern.winRate ?? 0) >= 0.55 ? "pos"
                        : (pattern.winRate ?? 0) < 0.4 ? "neg" : "neutral"} />
        <MetricKV label="Avg return"
                  value={pattern.avgRet !== null
                    ? fmtPct(pattern.avgRet) : "—"}
                  tone={toneForNumber(pattern.avgRet ?? 0)} />
      </div>
      {/* Win rate bar */}
      {pattern.winRate !== null && (
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="u-label-sm">Win rate bar</span>
            <span className={cn("u-num-sm font-semibold", wrTone)}>
              {(pattern.winRate * 100).toFixed(0)}%
            </span>
          </div>
          <div className="u-bar-track is-thick">
            <div className={cn("u-bar-fill",
              pattern.winRate >= 0.55 ? "is-pos"
              : pattern.winRate < 0.4 ? "is-neg" : "is-warning")}
              style={{ left: 0, width: `${pattern.winRate * 100}%` }} />
          </div>
        </div>
      )}
      <div className="u-caption text-fg-2">
        Engine {trade.engine} in {trade.regime_at_entry} regime wins{" "}
        <span className={cn("font-semibold", wrTone)}>
          {pattern.winRate !== null
            ? `${(pattern.winRate * 100).toFixed(0)}%` : "—"}
        </span>{" "}
        historically · avg{" "}
        <span className={cn("font-semibold", retTone)}>
          {pattern.avgRet !== null ? fmtPct(pattern.avgRet) : "—"}
        </span>
        {pattern.avgDuration !== null
          && ` over ${pattern.avgDuration.toFixed(1)}d`}.
      </div>

      {pattern.comparable.length > 0 && (
        <div>
          <div className="u-label-sm mb-2 mt-3">Recent peers</div>
          <ul className="space-y-1">
            {pattern.comparable.map(p => (
              <li key={p.trade_id}
                  className="flex items-center justify-between
                               px-3 py-2 u-card-tight">
                <span className="u-mono-sm">{p.entry_date}</span>
                <span className={cn("u-num-sm font-semibold",
                  toneForNumber(p.net_ret_pct ?? 0) === "pos" ? "text-success"
                  : toneForNumber(p.net_ret_pct ?? 0) === "neg" ? "text-danger"
                  : "text-fg-2")}>
                  {fmtPct(p.net_ret_pct)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function PatternEmptyPanel() {
  return (
    <Card size="md" className="h-full flex flex-col justify-center items-center">
      <div className="u-empty w-full">
        <div className="text-fg-4 text-3xl mb-3">◌</div>
        <div className="u-body-fg font-medium mb-1">
          Outcome + pattern context
        </div>
        <div className="u-caption-2 max-w-xs text-center">
          Select a decision to see its realized outcome versus peer trades
          with the same engine and regime.
        </div>
      </div>
    </Card>
  );
}

// =========================================================================
// Live fallback (no trades yet) — keeps col 2 usable on empty state
// =========================================================================

function TodaysDecisionDetail({ state }: { state: CurrentState | undefined }) {
  return (
    <Card size="md">
      <div className="u-label mb-2">Today · {state?.as_of_date ?? "—"}</div>
      <h2 className="u-title-lg mb-4">
        {state?.fire ? `Engine ${state.engine} fired` : "No entry today"}
      </h2>

      <div className="grid grid-cols-3 gap-4 mb-6">
        <MetricKV label="Regime"
                  value={state?.stress_regime ? "STRESS"
                          : state?.directional_regime ? "DIRECTIONAL"
                          : "NEUTRAL"}
                  tone="neutral" />
        <MetricKV label="Gates"
                  value={`${state?.gates_favorable ?? 0} / 4`}
                  tone="neutral" />
        <MetricKV label="Version"
                  value={state?.decision_version ?? "—"}
                  tone="neutral" />
      </div>

      <Divider />

      <div className="mt-6">
        <div className="u-label mb-2">Reasoning</div>
        <pre className="u-mono bg-sunken rounded-md p-4 whitespace-pre-wrap">
          {state?.reason ?? "(no reason recorded)"}
        </pre>
      </div>

      <div className="mt-6">
        <div className="u-label mb-3">Context Values</div>
        <dl className="divide-y divide-b1 rounded-md border border-b1">
          {Object.entries(state?.context_values ?? {}).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between px-4 py-2.5">
              <dt className="u-mono-sm">{k}</dt>
              <dd className="u-mono">{String(v)}</dd>
            </div>
          ))}
        </dl>
      </div>

      <p className="u-caption-2 mt-6">
        Once trades exist the timeline becomes clickable and shows per-trade
        outcome, anomalies, and historical pattern context in the right column.
      </p>
    </Card>
  );
}


// UX-1 Commit J — calm interpretation card for the Decisions
// page header. Pure render component. NO new hook, NO data
// fetch — only labels the totals already computed by the parent.
// Branches in priority order: not loaded > zero > pending > open
// > all closed.
function DecisionsCalmCard({
  total, openCount, pending, replayCount, loaded,
}: {
  total: number;
  openCount: number;
  pending: number;
  replayCount: number;
  loaded: boolean;
}) {
  let tone = "Operating normally";
  let chip: "success" | "neutral" | "warning" = "success";
  let headline = "Operating normally.";
  let body =
    "The system continues to monitor the daily pipeline. New "
    + "decisions appear here as they are made. No action is "
    + "needed right now.";

  if (!loaded) {
    tone = "Loading";
    chip = "neutral";
    headline = "Decisions are loading.";
    body =
      "The timeline below will populate once today's pipeline "
      + "finishes. No action needed.";
  } else if (total === 0) {
    tone = "Quiet";
    chip = "neutral";
    headline = "No decisions yet today.";
    body =
      "Once the daily run finishes, every buy / skip will appear "
      + "here with the reason. No action is needed.";
  } else if (pending > 0) {
    tone = "Waiting for next market update";
    chip = "warning";
    headline = `${pending} trade${pending === 1 ? "" : "s"} `
      + "waiting for tomorrow's market data.";
    body =
      "These trades matched the strategy and passed safety "
      + "checks. They are prepared and will complete after "
      + "tomorrow's market data becomes available — this is "
      + "intentional, not stuck. The system continues to monitor "
      + "open paper trades. No action is needed.";
  } else if (openCount > 0) {
    tone = "Holding open trades";
    chip = "neutral";
    headline = `${openCount} paper trade`
      + `${openCount === 1 ? "" : "s"} still open.`;
    body =
      "The system is holding these positions and will close "
      + "them automatically when strategy rules trigger. Skipped "
      + "candidates remain visible below for transparency. No "
      + "action is needed.";
  } else {
    headline = "All paper trades have closed.";
    body =
      "The system continues reviewing today's candidates for new "
      + "matches. Every closed trade and every skipped candidate "
      + "remains visible below. No action is needed.";
  }

  // Replay-specific footnote when recovered-history rows exist.
  let replayNote: string | null = null;
  if (replayCount > 0) {
    replayNote =
      `${replayCount} of the rows below were reconstructed from `
      + "backup data after a 2026-05-02 reset and are tagged "
      + "separately — not live trading.";
  }

  return (
    <section
      className="u-card-tight"
      data-test="decisions-calm-state"
      style={{ padding: "14px 18px" }}
    >
      <div className="flex items-center gap-3 mb-1">
        <span className={`u-chip u-chip-${chip}`}>
          <span className={`u-dot u-dot-${chip}`} />
          {tone}
        </span>
        <span
          className="u-body font-semibold text-fg"
          data-test="decisions-calm-headline"
        >
          {headline}
        </span>
      </div>
      <p
        className="u-caption text-fg-2 max-w-3xl"
        data-test="decisions-calm-body"
      >
        {body}
      </p>
      {replayNote && (
        <p
          className="u-caption-2 text-fg-3 mt-1 max-w-3xl"
          data-test="decisions-calm-replay-note"
        >
          {replayNote}
        </p>
      )}
    </section>
  );
}

