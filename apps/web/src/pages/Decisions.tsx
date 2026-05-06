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
  Card, Pill, Divider, fmtPct, toneForNumber, Skeleton, Label,
} from "@/components/ui/primitives";
import FactorAttributionMini from "@/components/decisions/FactorAttributionMini";
import type {
  TradeRow, CurrentState, DecisionRow, AnomalyEvent,
} from "@/lib/operator/types";
import { cn } from "@/lib/cn";

// Filter set — paper-trading aware. Engine A/B retained for the
// rare legacy row that still carries those engine values; the
// active paper-trading data has engine="paper" and is shown via
// "All" / "Open" / "Live" / "Replay".
type Filter = "all" | "live" | "replay" | "open" | "anom";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all",    label: "All" },
  { id: "live",   label: "Live" },
  { id: "replay", label: "Replay" },
  { id: "open",   label: "Open" },
  { id: "anom",   label: "Anomaly" },
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
      <header className="mb-6">
        <Label>Decisions</Label>
        <h1 className="u-title-lg mt-1">Decision Audit Workstation</h1>
        <p className="u-body mt-2 max-w-3xl">
          Real paper-trading decisions sourced from{" "}
          <code>paper_trade</code> joined to{" "}
          <code>paper_position</code>. Live and replay-recovered
          rows are tagged separately. Pending next-bar fills are
          shown in the badge below — they are valid decisions
          held by the next-bar guard, not failures.
        </p>
        <div
          className="mt-3 flex flex-wrap items-center gap-2 u-caption-2"
          data-test="decisions-truth-banner"
        >
          <span className="u-chip u-chip-neutral">
            <span className="u-dot u-dot-neutral" />
            <span className="ml-1">
              Total {totals.total}
            </span>
          </span>
          <span className="u-chip u-chip-success">
            <span className="u-dot u-dot-success" />
            <span className="ml-1">Live {totals.live}</span>
          </span>
          <span className="u-chip u-chip-warning">
            <span className="u-dot u-dot-warning" />
            <span className="ml-1">Replay {totals.replay}</span>
          </span>
          <span className="u-chip u-chip-accent">
            <span className="u-dot u-dot-accent" />
            <span className="ml-1">Open {totals.open}</span>
          </span>
          {totals.pending > 0 && (
            <span className="u-chip u-chip-warning">
              <span className="u-dot u-dot-warning" />
              <span className="ml-1">
                Pending next-bar {totals.pending}
              </span>
            </span>
          )}
        </div>
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
        <span className="uppercase tracking-wider font-semibold">
          {t.engine === "A" || t.engine === "B"
            ? `Engine ${t.engine}`
            : t.regime_at_entry || "paper"}
        </span>
        <span className="u-mono-sm">
          {t.days_held !== null ? `${t.days_held}d` : "holding"}
        </span>
      </div>
      <div className="flex gap-1.5 flex-wrap mt-2">
        {t.status === "open" &&
          <span className="u-chip u-chip-neutral">open</span>}
        {t.status === "closed" &&
          <span className="u-chip u-chip-success">closed</span>}
        {t.is_replay
          ? <span className="u-chip u-chip-warning">replay</span>
          : <span className="u-chip u-chip-success">live</span>}
        {hasAnomaly &&
          <span className="u-chip u-chip-danger">
            <span className="u-dot u-dot-danger u-dot-pulse" />anomaly
          </span>}
      </div>
    </button>
  );
}

function EmptyFilter() {
  return (
    <div className="u-card-tight">
      <div className="u-caption-2 italic">
        No decisions match this filter.
      </div>
    </div>
  );
}

function TodaysDecisionFallback({ state }: {
  state: CurrentState | undefined;
}) {
  if (!state) return <Skeleton className="h-24" />;
  return (
    <div className="u-card-tight"
         style={{ background: "var(--accent-subtle)",
                  borderColor: "rgba(75,139,255,0.4)" }}>
      <div className="flex items-center gap-2 mb-2">
        <Pill tone="accent" dot>LIVE</Pill>
        <span className="u-mono-sm">{state.as_of_date}</span>
      </div>
      <div className="u-body-fg font-medium mb-2">
        {state.fire ? `Engine ${state.engine} → enter_long` : "Stood by"}
      </div>
      <div className="u-caption-2">
        No trades recorded yet. Timeline shows today's live decision.
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
            Select a decision on the left
          </div>
          <div className="u-caption-2 max-w-xs text-center">
            Full reasoning, production inputs, blocking logic, and diagnostic
            snapshot appear here.
          </div>
        </div>
      </Card>
    );
  }

  const engineLabel = trade.engine === "A"
    ? "Engine A · mean reversion"
    : trade.engine === "B" ? "Engine B · credit + rates" : "No entry";

  return (
    <Card size="md" className="space-y-6">
      {/* A — decision summary */}
      <header>
        <div className="flex items-center gap-2 mb-3">
          <span className="u-chip u-chip-accent">Decision</span>
          <span className="u-mono-sm">{trade.entry_date}</span>
          {trade.status === "open" &&
            <span className="u-chip u-chip-neutral">open</span>}
        </div>
        <h2 className="u-title-lg" style={{ fontSize: 24 }}>
          {engineLabel}
        </h2>
        <div className="u-caption text-fg-2 mt-2">
          Fired long · {trade.regime_at_entry} regime ·
          {" "}version {trade.decision_version}
        </div>
      </header>

      <Divider />

      {/* B — plain-english reasoning */}
      <Section title="Reasoning">
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
        <Section title="Factor Attribution"
                 hint="Deterministic 7-factor breakdown (advisory)">
          <FactorAttributionMini
            attribution={decision.factor_attribution as any} />
        </Section>
      )}

      <Section title="Production Inputs"
               hint="Raw features used by the decision rule">
        <KVTable data={decision?.inputs_used ?? {}} />
      </Section>

      {/* D — blocking logic */}
      <Section title="Blocking Logic"
               hint="Why entry was/was-not suppressed">
        <BlockingPanel decision={decision ?? null} trade={trade} />
      </Section>

      {/* E — diagnostic snapshot */}
      {decision?.diagnostic_snapshot
       && Object.keys(decision.diagnostic_snapshot).length > 0 && (
        <Section title="Diagnostic Snapshot"
                 hint="Observed but NOT USED IN PRODUCTION"
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
    return (
      <div className="u-caption-2 italic">
        Decision log not found for {trade.entry_date}.
      </div>
    );
  }
  if (decision.blocked_by) {
    return (
      <div className="u-card-tight" style={{
        background: "var(--warning-muted)",
        borderColor: "rgba(248,166,56,0.4)",
      }}>
        <div className="u-label-sm mb-1 text-warning">Blocked</div>
        <div className="u-body-fg text-warning">{decision.blocked_by}</div>
      </div>
    );
  }
  // Show which contexts were True vs False
  const ctx = decision.context_values ?? {};
  return (
    <div className="space-y-2">
      <div className="u-caption text-fg-2">
        Entry allowed — all required contexts aligned.
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
  const engine = trade.engine === "A" ? "Engine A (mean reversion)"
    : trade.engine === "B" ? "Engine B (credit + rates alignment)"
    : "No engine";
  const regime = trade.regime_at_entry === "stress" ? "stress regime"
    : trade.regime_at_entry === "directional" ? "directional regime"
    : "neutral regime";
  const ctx = decision?.context_values ?? {};
  const ctxTrue = Object.entries(ctx).filter(([, v]) => v).map(([k]) => k);
  const gatesText = ctxTrue.length > 0
    ? ` Supporting contexts: ${ctxTrue.join(", ")}.`
    : "";
  const outcome = trade.net_ret_pct === null
    ? "Position still open."
    : trade.net_ret_pct > 0
      ? `Closed at ${fmtPct(trade.net_ret_pct)} net — thesis confirmed.`
      : `Closed at ${fmtPct(trade.net_ret_pct)} net — thesis rejected.`;
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

