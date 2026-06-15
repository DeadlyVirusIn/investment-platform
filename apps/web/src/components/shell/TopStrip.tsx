// Compact persistent top strip — always visible across pages.
// Shows live portfolio + system heartbeat. Dense, single line.

import {
  usePaperSummary, useCurrentState,
  useCanonicalStockPortfolio,
} from "@/lib/operator/hooks";
// HEALTH badge shares the Observability page's single source so the two can
// never disagree. Operator event counts live on the Observability page
// (engine room), not on this global rail (P1.6B).
import { useObservability } from "@/v2/lib/observability";
import { pipelineHealth } from "@/v2/lib/observabilityHealth";
import { Pill, fmtUSD, fmtPct, toneForNumber } from "@/components/ui/primitives";
import { useUIMode } from "@/lib/ui/mode";
import { useTheme } from "@/lib/ui/theme";
import { cn } from "@/lib/cn";
// Phase 15h.2 — calm freshness derivation for the NAV cell.
import { formatAsOf } from "@/lib/picks/freshness";

function Cell({
  label, children, className, tooltip, slot,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  // Phase 11K.1 — guardrail tooltip text shown on hover
  tooltip?: string;
  // Phase 14f-B — slot identifier used by mobile CSS to hide
  // non-essential cells. "essential" cells stay visible at <=768.
  slot?: "nav" | "day-pnl" | "total-return" | "regime" | "engine" | "health";
}) {
  return (
    <div
      className={cn("topstrip-cell px-4 py-3 flex flex-col justify-center min-w-0",
                      className)}
      data-slot={slot}
      title={tooltip}
    >
      <div className="u-caption-2 mb-0.5">{label}</div>
      <div className="text-[13px] font-medium text-fg tabular-nums truncate">
        {children}
      </div>
    </div>
  );
}

export default function TopStrip() {
  // P2 root-shell canonicalization — all portfolio TOTALS (NAV, Day P&L,
  // Total Return) read the single canonical stock portfolio, NOT the
  // all-portfolios aggregate (usePaperSummary). This matches every
  // trusted V2 surface (TrackRecord / practice / rail disclosure).
  const { data: book } = useCanonicalStockPortfolio();
  // summary retained ONLY for the non-financial "last run" heartbeat.
  const { data: summary } = usePaperSummary();
  const { data: state } = useCurrentState();
  // Operational health — same backend source the Observability page reads.
  const { data: obs } = useObservability();

  // Freshness reflects the canonical snapshot the NAV is read from. The
  // backend already classifies it (fresh / degraded / stale / unknown);
  // soften the NAV cell when not fresh, with an honest hover title.
  const navStale = book?.freshness != null && book.freshness !== "fresh";
  const navAsOf = book?.as_of ? formatAsOf(book.as_of) : null;
  const navTitle = navStale && navAsOf
    ? `NAV from ${navAsOf} — awaiting next refresh.`
    : "Values reflect simulated paper-trading results. They do not indicate future outcomes.";

  const regime = state?.stress_regime ? "stress"
    : state?.directional_regime ? "directional"
    : "neutral";
  // HEALTH — operational health ONLY, derived via the shared pipelineHealth
  // from /api/admin/observability. Identical to the Observability page hero,
  // so the badge and the page can never disagree. Anomalies do NOT feed this.
  const health = obs ? pipelineHealth(obs) : null;
  const healthTone = health
    ? (health.tone === "good" ? "success"
        : health.tone === "warn" ? "warning"
        : health.tone === "bad" ? "danger" : "neutral")
    : "neutral";
  const healthLabel = health ? health.label : "—";

  return (
    <div className="topstrip-root bg-ink/95 backdrop-blur
                     border-b border-b1 flex items-stretch divide-x divide-b1">
      <Cell
        label="NAV"
        slot="nav"
        className={cn("min-w-[120px]", navStale && "topstrip-cell-stale")}
        tooltip={navTitle}
      >
        {book?.nav != null ? fmtUSD(book.nav) : "—"}
      </Cell>
      <Cell
        label="Day P&L"
        slot="day-pnl"
        className="min-w-[120px]"
        tooltip="Values reflect simulated paper-trading results. They do not indicate future outcomes."
      >
        <span className={cn(
          "tabular-nums",
          book?.daily_pnl != null ? `text-${toneForNumber(book.daily_pnl) === "pos"
            ? "success" : toneForNumber(book.daily_pnl) === "neg"
            ? "danger" : "fg"}` : "text-fg",
        )}>
          {book?.daily_pnl != null
            ? (book.daily_pnl > 0 ? "+" : book.daily_pnl < 0 ? "−" : "")
              + "$" + Math.abs(book.daily_pnl).toFixed(2)
            : "—"}
        </span>
      </Cell>
      <Cell
        label="Total Return"
        slot="total-return"
        className="min-w-[110px]"
        tooltip="Values reflect simulated paper-trading results. They do not indicate future outcomes."
      >
        <span className={`tabular-nums ${book?.total_return_pct != null && book.total_return_pct > 0
          ? "text-success" : book?.total_return_pct != null && book.total_return_pct < 0
          ? "text-danger" : "text-fg"}`}>
          {fmtPct(book?.total_return_pct)}
        </span>
      </Cell>
      <Cell
        label="Regime"
        slot="regime"
        className="min-w-[130px]"
        tooltip="Regime is a model classification and does not imply direction."
      >
        <Pill tone={regime === "stress" ? "accent"
                    : regime === "directional" ? "accent" : "neutral"}>
          {regime}
        </Pill>
      </Cell>
      <Cell label="Engine" slot="engine" className="min-w-[100px]">
        {state?.fire
          ? <Pill tone="success" dot>Engine {state.engine}</Pill>
          : <span className="text-fg-3">No evaluation path currently active</span>}
      </Cell>
      <Cell
        label="Health"
        slot="health"
        className="min-w-[120px]"
        tooltip="Operational health — data freshness, jobs, DB, workers. Same source as the Observability page."
      >
        <Pill tone={healthTone} dot>{healthLabel}</Pill>
      </Cell>
      <div className="topstrip-toggles ml-auto px-4 py-3 flex items-center gap-3
                        u-caption-2 font-mono">
        <ThemeToggle />
        <UIModeToggle />
        <span className="topstrip-last-run">
          {summary?.last_decision_ts
            ? `last run ${new Date(summary.last_decision_ts).toLocaleTimeString()}`
            : "idle"}
        </span>
      </div>
    </div>
  );
}

function UIModeToggle() {
  const [mode, setMode] = useUIMode();
  return (
    <button onClick={() => setMode(mode === "guided" ? "expert" : "guided")}
            className={cn("u-chip",
              mode === "guided" ? "u-chip-accent" : "u-chip-neutral")}
            title={mode === "guided"
              ? "Beginner guidance ON — click for expert mode"
              : "Expert mode — click for guided mode"}>
      {mode === "guided" ? "guided" : "expert"}
    </button>
  );
}


// Phase 3 — theme toggle. Persists to localStorage["theme"].
function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className={cn("u-chip", "u-chip-neutral", "u-btn-toggle")}
      role="switch"
      aria-checked={theme === "light"}
      title={`Switch to ${next} mode`}>
      {theme === "dark" ? "dark" : "light"}
    </button>
  );
}
