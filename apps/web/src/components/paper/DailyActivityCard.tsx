// Phase DAILY-VISIBILITY v3 + Phase UX-PHASE2 HI-5 — compact rows.
// One-line summary by default; click to expand for full annotation
// stack (similarity, ML hybrid, learning, outcome, confidence).

import { useState } from "react";
import {
  useLatestPaperRun, useLatestPaperRunEvents,
} from "@/lib/paper/runs";
import { usePerformance } from "@/lib/operator/hooks";
import { Label } from "@/components/ui/primitives";
import {
  ChevronRight, ChevronDown, Diamond,
} from "@/components/ui/Icon";
import { cn } from "@/lib/cn";

const MAX_FEED = 10;


export default function DailyActivityCard({
  defaultCollapsed = true,
}: { defaultCollapsed?: boolean } = {}) {
  const { data: run } = useLatestPaperRun();
  const { data: events } = useLatestPaperRunEvents();
  const { data: perf } = usePerformance();
  const [expanded, setExpanded] = useState(!defaultCollapsed);

  if (!run) return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between">
        <Label>Today's Paper Trading Run</Label>
        <span className="u-caption-2">loading…</span>
      </div>
    </div>
  );
  if (!run.present) return (
    <div className="u-card-tight">
      <div className="flex items-center justify-between">
        <Label>Today's Paper Trading Run</Label>
        <span className="u-caption-2">
          No run recorded yet. Start the daily paper pipeline.
        </span>
      </div>
    </div>
  );

  const rawStatus = (run.status ?? "running").toLowerCase();
  const reason = _derivePartialReason(run);
  const effectiveStatus =
    rawStatus === "partial" && !reason?.marksPartial
      ? "success" : rawStatus;
  const tone = statusTone(effectiveStatus);
  const opened = run.trades_opened ?? 0;
  const closed = run.trades_closed ?? 0;
  const noTrade = opened === 0 && closed === 0;
  const decisions = run.decisions_evaluated ?? 0;
  const gp = run.details && (run.details as Record<string, unknown>)["gates_passed"];
  const gt = run.details && (run.details as Record<string, unknown>)["gates_total"];
  const gateStr = (gp != null && gt != null) ? `${gp}/${gt}` : null;

  const feed = buildFeed(events, perf);

  // Phase: collapsed default per UX spec — header carries one-line
  // summary; click chevron expands full content. Activity feed renders
  // inside expanded panel only; compact variant lives in <RecentEventsFeed>.
  return (
    <div className="u-card">
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
        className="u-feed-row-clickable w-full flex items-center
                     justify-between gap-3 text-left">
        <div className="flex items-center gap-3 min-w-0 flex-wrap">
          <span className={cn("u-chip", tone)}>{effectiveStatus}</span>
          <span className="u-caption-2 text-fg-3">{run.run_date}</span>
          <span
            className="u-caption text-fg truncate"
            title="Gates represent rule condition alignment. Partial completion does not imply pending or expected action."
          >
            {decisions} observation{decisions === 1 ? "" : "s"}
            · {opened} opened · {closed} closed
            {noTrade ? " · no state change recorded" : ""}
            {gateStr ? ` · ${gateStr} gates` : ""}
          </span>
        </div>
        <span className="text-fg-3 inline-flex items-center"
              aria-hidden="true">
          {expanded
            ? <ChevronDown size={14} />
            : <ChevronRight size={14} />}
        </span>
      </button>

      {expanded && (
        <div className="mt-3">

      {/* PROMOTED SUMMARY — primary explanation */}
      {run.summary && (
        <div className="u-card-tight u-card-tight-accent mb-3">
          <div className="u-body-fg leading-snug font-medium">
            {run.summary}
          </div>
        </div>
      )}

      {/* REASON block — only for genuinely PARTIAL/FAILED runs */}
      {reason && (reason.marksPartial || effectiveStatus === "failed") && (
        <div className="u-card-tight u-card-tight-warning mb-3">
          <div className="u-label-sm mb-1 text-warning">
            {reason.title}
          </div>
          <div className="u-caption text-fg leading-snug">
            {reason.detail}
          </div>
        </div>
      )}

      {/* No-state-change explanation */}
      {noTrade && (
        <div className="u-caption text-fg-2 mb-3">
          No state changes recorded today. System evaluated{" "}
          {run.decisions_evaluated ?? 0} observation(s) and recorded
          no state change
          {run.blocked_by_gates
            ? " due to incomplete macro alignment." : "."}
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-6 gap-y-1 mb-3">
        <KV k="Observations" v={`${run.decisions_evaluated ?? 0}`} />
        <KV k="Opened"       v={`${opened}`} />
        <KV k="Closed"       v={`${closed}`} />
        <KV k="Exploratory"  v={`${run.exploratory_trades ?? 0}`} />
        <KV k="Strict"       v={`${run.strict_trades ?? 0}`} />
        <KV k="Day P&L"
            v={run.net_pnl_today != null
                ? `$${Number(run.net_pnl_today).toFixed(2)}`
                : "—"}
            tone={(run.net_pnl_today ?? 0) > 0 ? "pos"
                   : (run.net_pnl_today ?? 0) < 0 ? "neg" : "neutral"} />
      </div>

      {/* ACTIVITY FEED */}
      <div
        className="pt-3 border-t border-b1"
        title="Events reflect internal evaluation states. They do not represent trade actions or instructions."
      >
        <div className="u-label-sm mb-2">Today's Activity Feed</div>
        {feed.length === 0 ? (
          <div className="u-caption-2 italic">No activity this run.</div>
        ) : (
          <ul className="space-y-1">
            {feed.slice(0, MAX_FEED).map((r, i) => (
              <FeedRowItem key={i} r={r} />
            ))}
          </ul>
        )}
      </div>
        </div>
      )}
    </div>
  );
}


// CF-5/HI-5 — single-row compact feed entry. Click row → expand details.
function FeedRowItem({ r }: { r: FeedRow }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = !!(r.confidence || r.outcome || r.learning
    || (r.similarityMatched && r.action === "opened")
    || (r.mlApplied && r.action === "opened")
    || (r.mlAvailable && r.mlAction === "annotate" && r.action === "opened"));
  const toggle = () => hasDetail && setExpanded(v => !v);
  return (
    <li className="u-caption-2">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={expanded}
        disabled={!hasDetail}
        className={cn(
          "w-full text-left grid items-center gap-2 px-1 py-0.5 rounded",
          "grid-cols-[48px_1fr_auto]",
          hasDetail ? "u-feed-row-clickable" : "cursor-default",
        )}
        title={hasDetail
          ? (expanded ? "Hide details" : "Show details") : ""}
      >
        <span className="u-mono-sm text-fg-3">{r.time}</span>
        <span className="truncate">
          <span className={cn("u-chip", toneForAction(r.action))}>
            {r.action}
          </span>{" "}
          <span className="u-mono-sm text-fg">{r.symbol}</span>
          {r.engine && (
            <span className="text-fg-3"> · {r.engine}</span>
          )}
          {r.exploratory && (
            <span className="u-chip u-chip-neutral ml-1"
                  title="Exploratory: gates incomplete, learning only.">
              exp
            </span>
          )}
          {r.size_pct != null && (
            <span className="text-fg-3"> · {_fmtPct(r.size_pct)}%</span>
          )}
          {r.quality && r.action === "closed" && (
            <span className={cn("u-chip ml-1", _qualityCls(r.quality))}>
              {r.quality}
            </span>
          )}
          {/* Inline summary — single short suffix only */}
          {!expanded && (r.outcome || r.reason) && (
            <span className="text-fg-3 ml-1 truncate">
              {r.outcome || r.reason}
            </span>
          )}
          {/* Compact ML/similarity flags collapse to glyph dots */}
          {!expanded && r.similarityMatched
            && r.action === "opened" && (
            <span className="ml-1 text-warning inline-flex items-center gap-0.5"
                  title={r.similarityReason
                          ?? "Similar past trades underperformed"}>
              <Diamond size={10} aria-hidden="true" />sim
            </span>
          )}
          {!expanded && r.mlApplied && r.action === "opened" && (
            <span className="ml-1 text-warning inline-flex items-center gap-0.5"
                  title={r.mlReason ?? "ML shadow warned"}>
              <Diamond size={10} aria-hidden="true" />ml
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          <span className={cn("u-mono-sm shrink-0",
            _num(r.retPct) != null && _num(r.retPct)! > 0 ? "text-success"
            : _num(r.retPct) != null && _num(r.retPct)! < 0 ? "text-danger"
            : "text-fg-3")}>
            {_num(r.retPct) != null
              ? `${_num(r.retPct)! > 0 ? "+" : ""}${_num(r.retPct)!.toFixed(2)}%`
              : ""}
          </span>
          {hasDetail && (
            <span className="text-fg-3 inline-flex items-center"
                  aria-hidden="true">
              {expanded
                ? <ChevronDown size={12} />
                : <ChevronRight size={12} />}
            </span>
          )}
        </span>
      </button>
      {expanded && hasDetail && (
        <div className="pl-[56px] pr-2 py-1 space-y-0.5 text-fg-3">
          {r.confidence && (
            <div>
              Confidence:{" "}
              <span className={cn("font-semibold",
                r.confidence === "HIGH" ? "text-success" : "text-warning")}>
                {r.confidence}
              </span>
            </div>
          )}
          {r.engineHealth && (
            <div title="Engine attribution reflects historical paper-trading contribution only. It does not indicate future performance or strategy selection.">
              Engine contribution level:{" "}
              <span className={cn("font-semibold",
                                    _healthCls(r.engineHealth))}>
                {_engineHealthLabel(r.engineHealth)}
              </span>
            </div>
          )}
          {r.outcome && <div>Outcome: <span className="text-fg">{r.outcome}</span></div>}
          {r.learning && <div className="italic">Learning: {r.learning}</div>}
          {r.similarityMatched && r.action === "opened" && (
            <div className="text-warning" title={r.similarityReason}>
              Similar past trades underperformed — size reduced
              {_num(r.similarityMultiplier) != null && (
                <span className="u-mono-sm ml-1 text-fg-3">
                  (×{_num(r.similarityMultiplier)!.toFixed(2)})
                </span>
              )}
            </div>
          )}
          {r.mlApplied && r.action === "opened" && (
            <div className="text-warning" title={r.mlReason}>
              ML shadow warned — size reduced
              {_num(r.mlMultiplier) != null && (
                <span className="u-mono-sm ml-1 text-fg-3">
                  (×{_num(r.mlMultiplier)!.toFixed(2)})
                </span>
              )}
            </div>
          )}
          {r.mlAvailable && !r.mlApplied
            && r.action === "opened"
            && r.mlAction === "annotate" && (
            <div className="italic" title={r.mlReason}>
              ML shadow available but not eligible.
            </div>
          )}
        </div>
      )}
    </li>
  );
}


// ---------------------------------------------------------------------------

type EngineHealth = "STRONG" | "MIXED" | "WEAK" | "WATCH";

interface FeedRow {
  time: string;
  symbol: string;
  engine?: string;
  engineHealth?: EngineHealth;
  action: "opened" | "closed" | "skipped" | "blocked" | "decision";
  exploratory?: boolean;
  size_pct?: number | null;
  reason?: string | null;
  retPct?: number | null;
  // Phase CLARITY-2 annotations
  quality?: "GOOD" | "BAD" | "NEUTRAL";
  confidence?: "HIGH" | "LOW";
  outcome?: string;                 // "Better than expected" etc.
  learning?: string;                // one-line deterministic note
  // ALPHA-8 similarity annotation
  similarityMatched?: boolean;
  similarityMultiplier?: number;
  similarityReason?: string;
  // ML-5 hybrid advisor annotation
  mlAvailable?: boolean;
  mlAction?: string;            // none|annotate|reduce_size|would_block
  mlMultiplier?: number;
  mlReason?: string;
  mlApplied?: boolean;          // true when it actually reduced size
}


function buildFeed(
  events: ReturnType<typeof useLatestPaperRunEvents>["data"],
  perf: ReturnType<typeof usePerformance>["data"] | undefined,
): FeedRow[]
{
  if (!events) return [];
  const rows: FeedRow[] = [];
  const peerMean = _peerMeanReturn(perf);

  for (const t of events.trades || []) {
    const et = (t as any).event_type as string | undefined;
    const action: FeedRow["action"] =
      et === "opened" ? "opened"
      : et === "closed" ? "closed"
      : "decision";
    const ret = _num(t.net_ret_pct ?? t.gross_ret_pct);
    const eng = t.engine ?? undefined;
    const engHealth = _engineHealthFromPerf(eng, perf);
    const exploratory = !!t.exploratory_paper;
    const quality = action === "closed"
      ? _classifyQuality(ret, peerMean) : undefined;
    const confidence: FeedRow["confidence"] | undefined =
      (action === "opened")
        ? (exploratory ? "LOW" : "HIGH")
        : undefined;
    const outcome = action === "closed"
      ? _outcomeLabel(ret, exploratory, engHealth)
      : undefined;
    const learning = action === "closed"
      ? _learningLine(ret, exploratory, engHealth)
      : undefined;
    const simMatched = String(t.sim_matched ?? "").toLowerCase() === "true";
    const simMultNum = t.sim_mult != null ? Number(t.sim_mult) : undefined;
    const simValid = simMultNum != null && !isNaN(simMultNum);
    const mlAvail = String(t.ml_avail ?? "").toLowerCase() === "true";
    const mlMultNum = t.ml_mult != null ? Number(t.ml_mult) : undefined;
    const mlValid = mlMultNum != null && !isNaN(mlMultNum);
    const mlAction = (t.ml_action ?? "none").toString();
    rows.push({
      time: _formatTime(t.ts),
      symbol: t.symbol ?? "—",
      engine: eng,
      engineHealth: engHealth,
      action,
      exploratory,
      size_pct: _num(t.position_size_pct),
      retPct: ret,
      quality,
      confidence,
      outcome,
      learning,
      similarityMatched: simMatched && simValid && simMultNum! < 1.0,
      similarityMultiplier: simValid ? simMultNum : undefined,
      similarityReason: t.sim_reason ?? undefined,
      mlAvailable: mlAvail,
      mlAction: mlAction,
      mlMultiplier: mlValid ? mlMultNum : undefined,
      mlReason: t.ml_reason ?? undefined,
      mlApplied: mlValid && mlMultNum! < 1.0,
    });
  }

  for (const d of events.decisions || []) {
    const acc = (d.action ?? "").toLowerCase();
    if (acc === "enter_long") continue;     // captured via trades
    const action: FeedRow["action"] =
      acc === "skip" ? "skipped"
      : acc === "no_fire" ? "skipped"
      : acc.includes("block") ? "blocked"
      : "decision";
    const missing = d.gates_passed != null && d.gates_total != null
      && d.gates_passed < d.gates_total
      ? `${d.gates_passed}/${d.gates_total} gates`
      : undefined;
    rows.push({
      time: _formatTime(d.ts),
      symbol: d.symbol ?? "—",
      engine: d.engine ?? undefined,
      engineHealth: _engineHealthFromPerf(d.engine ?? undefined, perf),
      action,
      exploratory: !!d.exploratory_paper,
      reason: missing ?? d.reason ?? null,
    });
  }

  rows.sort((a, b) => a.time.localeCompare(b.time));
  return rows;
}


// ---------------------------------------------------------------------------
// Phase CLARITY-2 — deterministic classifiers
// ---------------------------------------------------------------------------

function _classifyQuality(
  ret: number | null | undefined, peerMean: number | null,
): FeedRow["quality"] {
  if (ret == null) return "NEUTRAL";
  if (peerMean != null) {
    if (ret > 0.3 && ret > peerMean) return "GOOD";
    if (ret < -0.3 && ret < peerMean) return "BAD";
    return "NEUTRAL";
  }
  if (ret > 0.3)  return "GOOD";
  if (ret < -0.3) return "BAD";
  return "NEUTRAL";
}


function _outcomeLabel(
  ret: number | null | undefined,
  exploratory: boolean,
  engHealth: EngineHealth | undefined,
): string | undefined {
  if (ret == null) return undefined;
  const positive = ret > 0;
  // Base expectation — exploratory & weak engine = low; strict & strong = high
  const highExpectation = !exploratory && engHealth === "STRONG";
  const lowExpectation  = exploratory || engHealth === "WEAK";
  if (positive && lowExpectation)  return "Better than expected";
  if (positive && !highExpectation) return "Met expectation";
  if (positive)                     return "Met expectation";
  if (highExpectation)              return "Missed expectation";
  if (lowExpectation)               return "In line with low expectation";
  return "Below expectation";
}


function _learningLine(
  ret: number | null | undefined,
  exploratory: boolean,
  engHealth: EngineHealth | undefined,
): string | undefined {
  if (ret == null) return undefined;
  const positive = ret > 0;
  if (exploratory && positive) {
    return "Exploratory trades can still perform in low-risk conditions.";
  }
  if (exploratory && !positive) {
    return "Exploratory path did not pay off — gate incompleteness mattered.";
  }
  if (engHealth === "WEAK" && !positive) {
    return "Engine continues to underperform in this regime.";
  }
  if (engHealth === "STRONG" && !positive) {
    return "Signal failed despite strong track record — review entry timing.";
  }
  if (engHealth === "STRONG" && positive) {
    return "Strong engine performed as expected.";
  }
  if (engHealth === "WEAK" && positive) {
    return "Weak engine delivered a win — single sample, don't over-weight.";
  }
  return positive
    ? "Outcome consistent with recent performance."
    : "Outcome weaker than recent average — monitor.";
}


function _peerMeanReturn(
  perf: ReturnType<typeof usePerformance>["data"] | undefined,
): number | null {
  if (!perf) return null;
  const a = perf.engine_a?.avg_return_pct;
  const b = perf.engine_b?.avg_return_pct;
  const vals = [a, b].filter(
    (v): v is number => typeof v === "number" && !isNaN(v),
  );
  if (vals.length === 0) return null;
  return vals.reduce((x, y) => x + y, 0) / vals.length;
}


function _engineHealthFromPerf(
  engine: string | undefined,
  perf: ReturnType<typeof usePerformance>["data"] | undefined,
): EngineHealth | undefined {
  if (!engine || !perf) return undefined;
  const s = engine.toUpperCase() === "A" ? perf.engine_a
          : engine.toUpperCase() === "B" ? perf.engine_b : undefined;
  if (!s) return undefined;
  if (s.n_trades < 10) return "WATCH";
  const sh = s.sharpe_proxy;
  const avg = s.avg_return_pct ?? 0;
  if ((sh != null && sh < 0) || avg < 0 || s.total_pnl_pct < 0
       || s.win_rate < 0.5) return "WEAK";
  if (sh != null && sh > 1.0 && s.win_rate >= 0.55) return "STRONG";
  return "MIXED";
}


function _healthCls(h: EngineHealth | undefined): string {
  switch (h) {
    case "STRONG": return "text-success";
    case "MIXED":  return "text-warning";
    case "WEAK":   return "text-danger";
    default:       return "text-fg-3";
  }
}


// Phase 11K.1 — neutralised user-visible attribution labels.
// Internal codes ("STRONG"/"MIXED"/"WEAK"/"WATCH") remain unchanged
// for stable JSON contracts; rendered text is observational only.
function _engineHealthLabel(h: EngineHealth | undefined): string {
  switch (h) {
    case "STRONG": return "HIGH contribution level";
    case "MIXED":  return "MIXED contribution level";
    case "WEAK":   return "LOW contribution level";
    case "WATCH":  return "MONITORING contribution level";
    default:       return "—";
  }
}


function _qualityCls(q: FeedRow["quality"] | undefined): string {
  if (q === "GOOD")    return "u-chip-success";
  if (q === "BAD")     return "u-chip-danger";
  if (q === "NEUTRAL") return "u-chip-neutral";
  return "u-chip-neutral";
}

// Numeric values can arrive as string (Postgres numeric → JSON string).
// Coerce defensively — return null for non-finite / empty.
function _num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function _fmtPct(v: unknown, digits = 1): string {
  const n = _num(v);
  return n == null ? "—" : n.toFixed(digits);
}


function _formatTime(ts: string | undefined): string {
  if (!ts) return "";
  try {
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString(undefined, {
      hour: "2-digit", minute: "2-digit",
    });
  } catch {
    return ts;
  }
}


function toneForAction(a: string): string {
  switch (a) {
    case "opened":   return "u-chip-success";
    case "closed":   return "u-chip-accent";
    case "skipped":  return "u-chip-warning";
    case "blocked":  return "u-chip-danger";
    default:         return "u-chip-neutral";
  }
}


function KV({ k, v, tone = "neutral" }: {
  k: string; v: string; tone?: "pos" | "neg" | "neutral";
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption text-fg-2">{k}</span>
      <span className={cn("u-mono-sm font-semibold", cls)}>{v}</span>
    </div>
  );
}


function statusTone(s: string): string {
  switch (s) {
    case "success":   return "u-chip-success";
    case "partial":   return "u-chip-warning";
    case "failed":    return "u-chip-danger";
    case "no_action": return "u-chip-neutral";
    default:          return "u-chip-accent";
  }
}


// ---------------------------------------------------------------------------
// Phase UI-PARTIAL-REASON — derive human-readable reason from run payload.
// Frontend-only. Does not mutate backend status. Only the display chip is
// downgraded when warnings are benign (e.g. external data-provider timeouts
// with NO required-step skip).
// ---------------------------------------------------------------------------

type PartialReason = {
  title: string;
  detail: string;
  marksPartial: boolean;   // true → keep status PARTIAL; false → benign
};


function _derivePartialReason(run: {
  status?: string;
  warnings?: string[] | null;
  details?: Record<string, unknown> | null;
}): PartialReason | null {
  const status = (run.status ?? "").toLowerCase();
  const warnings = Array.isArray(run.warnings) ? run.warnings : [];
  const details = (run.details ?? {}) as Record<string, unknown>;

  // Market-data skip — paper_daily did not run because prior-day bars
  // were unavailable. This is a REQUIRED-step skip.
  const entrySource = details["entry_price_source"];
  const noPriceSkips = Number(details["no_price_skips"] ?? 0) || 0;
  const marketSkip = entrySource === null || entrySource === undefined
    || entrySource === "" || entrySource === "none"
    || noPriceSkips > 0
    || warnings.some(w =>
         /market data|production data missing|no_price/i.test(String(w)));
  if (status === "partial" && marketSkip) {
    return {
      title: "Paper trading skipped",
      detail: "Market data not available — paper trading skipped.",
      marksPartial: true,
    };
  }

  // Outright failure — surface failed step + first error line.
  if (status === "failed") {
    const first = warnings[0] || "pipeline error";
    return {
      title: "Run failed",
      detail: String(first).slice(0, 240),
      marksPartial: true,
    };
  }

  // Partial from external-provider warnings only (e.g. FRED timeouts) →
  // benign. Do not mark partial. We still return a reason for tooltip-
  // level detail, but marksPartial=false means the chip shows success.
  if (status === "partial" && warnings.length > 0) {
    return {
      title: "Non-blocking warning",
      detail: String(warnings[0]).slice(0, 240),
      marksPartial: false,
    };
  }

  return null;
}
