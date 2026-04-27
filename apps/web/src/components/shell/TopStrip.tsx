// Compact persistent top strip — always visible across pages.
// Shows live portfolio + system heartbeat. Dense, single line.

import { usePaperSummary, useCurrentState, useAnomalySummary } from "@/lib/operator/hooks";
import { Pill, fmtUSD, fmtPct, toneForNumber } from "@/components/ui/primitives";
import { useUIMode } from "@/lib/ui/mode";
import { useTheme } from "@/lib/ui/theme";
import { cn } from "@/lib/cn";

function Cell({
  label, children, className, tooltip,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  // Phase 11K.1 — guardrail tooltip text shown on hover
  tooltip?: string;
}) {
  return (
    <div
      className={cn("px-4 py-3 flex flex-col justify-center min-w-0",
                      className)}
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
  const { data: summary } = usePaperSummary();
  const { data: state } = useCurrentState();
  const { data: anomalies } = useAnomalySummary();

  const regime = state?.stress_regime ? "stress"
    : state?.directional_regime ? "directional"
    : "neutral";
  const crit = anomalies?.by_severity?.critical ?? 0;
  const warn = anomalies?.by_severity?.warning ?? 0;
  const healthTone = crit > 0 ? "danger" : warn > 0 ? "warning" : "success";
  const healthLabel = crit > 0 ? "Degraded" : warn > 0 ? "Warnings" : "Healthy";

  return (
    <div className="bg-ink/95 backdrop-blur
                     border-b border-b1 flex items-stretch divide-x divide-b1">
      <Cell
        label="NAV"
        className="min-w-[120px]"
        tooltip="Values reflect simulated paper-trading results. They do not indicate future outcomes."
      >
        {summary ? fmtUSD(summary.equity) : "—"}
      </Cell>
      <Cell
        label="Day P&L"
        className="min-w-[120px]"
        tooltip="Values reflect simulated paper-trading results. They do not indicate future outcomes."
      >
        <span className={cn(
          "tabular-nums",
          summary ? `text-${toneForNumber(summary.daily_pnl) === "pos"
            ? "success" : toneForNumber(summary.daily_pnl) === "neg"
            ? "danger" : "fg"}` : "text-fg",
        )}>
          {summary
            ? (summary.daily_pnl > 0 ? "+" : summary.daily_pnl < 0 ? "−" : "")
              + "$" + Math.abs(summary.daily_pnl).toFixed(2)
            : "—"}
        </span>
      </Cell>
      <Cell
        label="Total Return"
        className="min-w-[110px]"
        tooltip="Values reflect simulated paper-trading results. They do not indicate future outcomes."
      >
        <span className={`tabular-nums ${summary && summary.total_return_pct > 0
          ? "text-success" : summary && summary.total_return_pct < 0
          ? "text-danger" : "text-fg"}`}>
          {fmtPct(summary?.total_return_pct)}
        </span>
      </Cell>
      <Cell
        label="Regime"
        className="min-w-[130px]"
        tooltip="Regime is a model classification and does not imply direction."
      >
        <Pill tone={regime === "stress" ? "accent"
                    : regime === "directional" ? "accent" : "neutral"}>
          {regime}
        </Pill>
      </Cell>
      <Cell label="Engine" className="min-w-[100px]">
        {state?.fire
          ? <Pill tone="success" dot>Engine {state.engine}</Pill>
          : <span className="text-fg-3">No evaluation path currently active</span>}
      </Cell>
      <Cell label="Health" className="min-w-[120px]">
        <Pill tone={healthTone} dot>{healthLabel}</Pill>
      </Cell>
      <div className="ml-auto px-4 py-3 flex items-center gap-3
                        u-caption-2 font-mono">
        <ThemeToggle />
        <UIModeToggle />
        <span>
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
