// OVERVIEW v4 (Elite Terminal) — Bloomberg clarity × Apple polish.
// Strict: 65/35 hero, 4px gradient accent bar, 40px headline, 2x2 intel,
// NAV 64px, space not borders, chart 360+120 with glow, Next Action
// highlight, activity 44px rows with profit/loss strip.

import { useMemo } from "react";
import {
  usePaperSummary, useCurrentState, useAnomalySummary,
  usePaperTrades, usePerformance, useSystemHealth, useAnomalies,
  usePaperEquity, useExecutedSummary,
} from "@/lib/operator/hooks";
import EquityDrawdownChart from "@/components/operator/EquityDrawdownChart";
import WhatChanged from "@/components/overview/WhatChanged";
import RegimeHeatmap from "@/components/overview/RegimeHeatmap";
import TradeBlotter from "@/components/overview/TradeBlotter";
import TopCatalysts from "@/components/overview/TopCatalysts";
import GuidancePanel from "@/components/guidance/GuidancePanel";
import ExploratoryBanner from "@/components/guidance/ExploratoryBanner";
import DailyActivityCard from "@/components/paper/DailyActivityCard";
import ExecutionStatusCard from "@/components/paper/ExecutionStatusCard";
import ReadinessStrip from "@/components/overview/ReadinessStrip";
import AlphaCoreStatus from "@/components/overview/AlphaCoreStatus";
import RecentEventsFeed from "@/components/overview/RecentEventsFeed";
import { useLatestPaperRun } from "@/lib/paper/runs";
import {
  fmtUSD, fmtPct, toneForNumber, Label,
} from "@/components/ui/primitives";
import type {
  TradeRow, CurrentState, AnomalyEvent, PerformanceAttribution,
  PaperSummary, AnomalySummary, SystemHealth,
} from "@/lib/operator/types";
import { cn } from "@/lib/cn";
// Commit 2 (Novice UX) — page-level intro card. Pure layout add;
// no data dependency, no auto-fetch.
import { PageGuide, AdvancedDetails } from "@/components/novice";

export default function Overview() {
  const { data: summary } = usePaperSummary();
  const { data: state } = useCurrentState();
  const { data: anomSummary } = useAnomalySummary();
  const { data: anomalies } = useAnomalies("open");
  const { data: trades } = usePaperTrades();
  const { data: perf } = usePerformance();
  const { data: health } = useSystemHealth();
  const { data: equity } = usePaperEquity();
  // Phase 11Z — executed-trade headline numbers come from the
  // account/recommendation path, not paper_trade_log. Without this,
  // the Overview reports "Trades 0" while paper_trade has 18
  // replay-tagged rows behind the toggle.
  const { data: execSummary } = useExecutedSummary(false);

  const recentTrades = (trades ?? []).slice(0, 8);
  // Headline trade count = LIVE executed trades only. Replay rows
  // get their own badge below; never silently rolled into "Trades".
  const liveTradeCount = execSummary?.live_trades_count ?? 0;
  const replayTradeCount = execSummary?.replay_trades_count ?? 0;
  const replayPositionCount = execSummary?.replay_open_positions_count ?? 0;
  const hasReplayRecovered = !!execSummary?.has_replay_recovered_rows;
  const totalTrades = trades?.length ?? 0;  // strategy-log count (selector path)
  const winRate = useMemo(() => computeWinRate(trades ?? []), [trades]);
  const intel = useMemo(() => deriveIntelligence({
    state, perf, anomalies: anomalies ?? [], winRate,
    recentTrades: trades ?? [],
  }), [state, perf, anomalies, winRate, trades]);

  const hero = deriveHero({ state, summary, anomSummary });
  // UX-1 Commit C — single calm sentence summarising current
  // operational state. Logic-only derivation from data already
  // fetched above; no new hook, no auto-fetch. Order matters:
  // critical anomalies > pipeline failure > cautious gates >
  // normal. Shown in plain English so a beginner does not need
  // to read four telemetry chips to know "am I okay?".
  const calmState = deriveCalmState({ state, summary, anomSummary });

  return (
    <div className="max-w-[1520px] mx-auto px-6 py-6 space-y-5">

      {/* === 0. NOVICE PAGE GUIDE (Commit 2) ============================ */}
      {/* Plain-English page intro. Read-only research footer is shown    */}
      {/* once at the page level — individual cards do NOT repeat it.     */}
      <PageGuide
        title="Today at a glance"
        subtitle={
          "Quick summary of your paper account and what the system is "
          + "doing right now. All numbers are from simulated trades — "
          + "no real money is involved."
        }
        firstLook={
          <>
            Look at <strong>Account value</strong> first. Green means
            up vs your starting amount; red means down.
          </>
        }
      />

      {/* === 0b. START-HERE FOCUS CARD (UX-1 Commit E) ================ */}
      {/* Attention-sequencing guidance: tells the operator where to    */}
      {/* place their eye in order, and what they can defer. NOT a new  */}
      {/* data fetch — it just labels the existing layout below.        */}
      <section
        className="u-card-tight"
        data-test="overview-start-here"
        style={{ padding: "12px 16px" }}
      >
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Start here
        </div>
        <ol className="u-body text-fg space-y-1 list-decimal pl-5">
          <li>
            <strong>Account value</strong> — total worth of your
            paper account today.
          </li>
          <li>
            <strong>System status</strong> — the calm summary
            below answers "am I okay?".
          </li>
          <li>
            <strong>Trades still open</strong> — what the system is
            holding right now.
          </li>
        </ol>
        <p className="u-caption-2 text-fg-3 mt-2">
          Safe to ignore for now: the deeper diagnostics, market
          heatmap, intelligence grid, and engine attribution
          further down the page. They're available when you want
          them — none require action.
        </p>
      </section>

      {/* === 1. READINESS STRIP — single source of truth (CF-1, CF-3) === */}
      <section className="u-card-tight"
               style={{ padding: "10px 14px" }}>
        <ReadinessStrip />
      </section>

      {/* === 1b. EXECUTION STATUS — clear next-bar pending narrative.   */}
      {/*        Resolves "system ignored 05/04 data" misread; shows     */}
      {/*        signals ready, pending count, next-bar target, reason.  */}
      <ExecutionStatusCard />

      {/* === 2. CALM-STATE LINE (UX-1 Commit C) — replaces wall of   */}
      {/*       chips at top level. Single plain-English sentence     */}
      {/*       answering "am I okay? / do I need to do anything?".   */}
      {/*       Engineering chips (Regime / Gates / Engine / Pipeline */}
      {/*       / last decision) preserved one click away inside      */}
      {/*       AdvancedDetails. ExploratoryBanner stays visible      */}
      {/*       when active — it is a real warning.                   */}
      <section
        className="u-card-tight"
        style={{ padding: "12px 16px" }}
        data-test="overview-calm-state"
      >
        <div className="flex items-center gap-3">
          <span className={`u-chip u-chip-${calmState.chip}`}>
            <span className={`u-dot u-dot-${calmState.chip}`} />
            {calmState.tone}
          </span>
          <p className="u-body text-fg" data-test="overview-calm-sentence">
            {calmState.sentence}
          </p>
        </div>
        <ExploratoryBannerWired />
        <AdvancedDetails
          label="System diagnostics"
          className="mt-3"
        >
          <div
            className="flex items-center flex-wrap gap-x-8 gap-y-2"
            data-test="overview-system-diagnostics"
          >
            <span className={`u-chip u-chip-${hero.chip}`}>
              <span className={`u-dot u-dot-${hero.chip}`} />
              {hero.toneLabel}
            </span>
            <BannerCell label="Market condition">
              <RegimeBadge state={state} />
            </BannerCell>
            <BannerCell label="Safety checks passing">
              <span className={cn(
                "u-mono-sm font-semibold",
                (state?.gates_favorable ?? 0) >= 3 ? "text-success"
                : (state?.gates_favorable ?? 0) <= 1 ? "text-danger"
                : "text-warning"
              )}>
                {state?.gates_favorable ?? 0}
                <span className="text-fg-3"> / 4</span>
              </span>
            </BannerCell>
            <BannerCell label="Active strategy">
              <span className={`u-chip u-chip-${
                state?.fire ? "accent" : "neutral"}`}>
                {state?.fire
                  ? `${strategyHumanName(state.engine)} active`
                  : state?.engine && state.engine !== "none"
                    ? `${strategyHumanName(state.engine)} standby`
                    : "No strategy armed"}
              </span>
            </BannerCell>
            <BannerCell label="Daily run">
              <span className={`u-chip u-chip-${
                summary?.pipeline_status === "success" ? "success"
                : summary?.pipeline_status === "failed" ? "danger" : "neutral"
              }`}>
                {pipelineLabel(summary?.pipeline_status, !!state?.fire)}
              </span>
            </BannerCell>
            <span className="ml-auto u-caption-2 u-mono-sm text-fg-3">
              Last activity:{" "}
              {summary?.last_decision_ts
                ? new Date(summary.last_decision_ts).toLocaleString()
                : "—"}
            </span>
          </div>
        </AdvancedDetails>
      </section>

      {/* === 3. DAILY ACTIVITY — promoted above fold (CF-4) === */}
      <DailyActivityCard />

      {/* ================= 2. NAV STRIP — premium rail ================= */}
      <section className="u-nav-strip">
        <div className="u-stat-strip"
             style={{ gridTemplateColumns: "2.2fr 1fr 1fr 1fr 1fr",
                      padding: 0, gap: "44px" }}>
          {/* Commit 2 (Novice UX) — labels renamed to plain English. */}
          {/* Calculations + sub-text data sources unchanged.         */}
          <StatCell label="Account value"
            value={summary ? fmtUSD(summary.equity) : "—"}
            sub={summary
              ? `Available cash ${fmtUSD(summary.cash)}`
              : "Waiting for first run"}
            size="mega"
            tone={toneForNumber(summary?.total_return_pct ?? 0)}
            glow />
          <StatCell label="Today's change"
            value={summary ? fmtSignedCompact(summary.daily_pnl) : "—"}
            tone={toneForNumber(summary?.daily_pnl ?? 0)}
            sub={summary
              ? fmtPct(summary.daily_pnl / (summary.equity || 1) * 100, 3)
              : "n/a"}
            size="sec" />
          <StatCell label="Total return so far"
            value={fmtPct(summary?.total_return_pct)}
            tone={toneForNumber(summary?.total_return_pct ?? 0)}
            sub="Since the system started"
            size="sec" />
          <StatCell label="Biggest drop from peak"
            value={fmtPct(summary?.max_drawdown_pct)}
            tone="neg"
            sub="Largest dip in account value"
            size="sec" />
          <StatCell label="Paper trades so far"
            value={String(liveTradeCount)}
            sub={
              hasReplayRecovered
                ? `${replayTradeCount} recovered history rows available`
                : winRate !== null
                  ? `${(winRate * 100).toFixed(0)}% of closed trades finished positive`
                  : "None closed yet"
            }
            size="sec" />
        </div>
        {hasReplayRecovered && liveTradeCount === 0 && (
          <div
            data-test="overview-replay-availability"
            className="mt-3 u-card-tight flex items-center justify-between"
            style={{ background: "var(--sunken)", padding: "8px 12px" }}
          >
            <div className="u-caption">
              <span className="u-chip u-chip-warning mr-2">
                Recovered replay
              </span>
              <strong>{replayTradeCount}</strong> recovered replay trades
              {replayPositionCount > 0 && (
                <> · <strong>{replayPositionCount}</strong> recovered open positions</>
              )}
              {" "}available — NOT live trading activity. Open the
              {" "}<a href="/portfolio" className="underline">Paper Trading Terminal</a>
              {" "}and toggle "Show recovered replay data" to inspect.
            </div>
          </div>
        )}
      </section>

      {/* ================= 3. CORE GRID — 70/30 terminal ============== */}
      {/*  LEFT  : chart + recent events (no empty space under chart)    */}
      {/*  RIGHT : Alpha Core Status + Catalysts + Engine Attribution    */}
      {/*          + Current Risk + Next Action                          */}
      <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]
                             gap-4">
        <div className="flex flex-col gap-3 min-h-0">
          <div className="u-chart-frame">
            <EquityDrawdownChart />
          </div>
          {/* Compact events feed — eliminates empty space under chart */}
          <RecentEventsFeed />
          <WhatChanged />
        </div>

        <div className="flex flex-col gap-3 min-h-0">
          {/* PRIMARY system truth at top of right column */}
          <AlphaCoreStatus />

          <TopCatalysts />

          <SideCard title="Engine Attribution"
                    hint="Contribution to total return">
            <AttributionBlock perf={perf} />
          </SideCard>

          <SideCard title="Current Risk"
                    hint="Live exposure + anomalies">
            <RiskBlock summary={summary} anomSummary={anomSummary}
                       openTrades={recentTrades.filter(t =>
                         t.status === "open").length} />
          </SideCard>

          {/* HIGHLIGHT — Next Action */}
          <div className="u-card-highlight-pro flex flex-col min-h-0
                            relative z-0">
            <div className="relative z-10">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="u-dot u-dot-accent" />
                  <span className="u-section-title text-fg"
                        style={{ fontSize: 17 }}>
                    Next step
                  </span>
                </div>
                <span className="u-chip u-chip-accent">Watching market</span>
              </div>
              <NextActionBlock state={state} health={health} />
            </div>
          </div>
        </div>
      </section>

      {/* UX-1 Commit K — global hierarchy calming. The market-     */}
      {/* condition heatmap is below-the-fold context, not primary, */}
      {/* so it now collapses by default. Truth one click away.     */}
      <AdvancedDetails label="Market condition history (advanced)">
        <RegimeHeatmap />
      </AdvancedDetails>

      {/* UX-1 Commit K — Intelligence + Guidance section was       */}
      {/* already 'demoted below the fold' per its own comment.     */}
      {/* Now hidden behind a single expander so it stops competing */}
      {/* with the primary calm-state line and NAV strip up top.    */}
      <AdvancedDetails label="Today's intelligence & guidance (advanced)">
        <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]
                             gap-5">
          <div className="u-card">
            <div className="flex items-center justify-between mb-3">
              <Label>Intelligence</Label>
              <span className="u-chip u-chip-accent">LIVE</span>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <IntelTile label="Top driver"   item={intel.topDriver} />
              <IntelTile label="Drag"         item={intel.topBlocker} />
              <IntelTile label="Risk"         item={intel.topConcern} />
              <IntelTile label="Next action"  item={intel.nextTrigger} />
            </div>
          </div>
          <div>
            <GuidancePanel state={state} summary={summary}
                              anomSummary={anomSummary} />
          </div>
        </section>
      </AdvancedDetails>

      {/* ================= 4. ACTIVITY + LATEST DECISION ================= */}
      <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]
                             gap-5">
        <div className="u-card" style={{ padding: 0 }}>
          <div className="flex items-center justify-between px-5 py-4">
            <div>
              <Label>Recent Activity</Label>
              <div className="u-caption-2 mt-0.5">
                {totalTrades === 0
                  ? hasReplayRecovered
                    ? `No live strategy-log activity. ${replayTradeCount} recovered replay rows available in the Paper Terminal — not live.`
                    : `No trades yet — regime has not triggered entry.`
                  : `${totalTrades} total · showing ${recentTrades.length}`}
              </div>
            </div>
            {totalTrades === 0 && (
              <span className="u-chip u-chip-neutral">
                {hasReplayRecovered ? "Live: 0" : "Awaiting signal"}
              </span>
            )}
          </div>

          {recentTrades.length === 0 ? (
            <div className="px-5 pb-5">
              <ActivityFallback state={state} summary={summary} />
            </div>
          ) : (
            <>
              <div className="u-act-header">
                <span>Date</span>
                <span>Eng</span>
                <span>Regime</span>
                <span className="text-right">Return</span>
                <span className="text-right">Held</span>
                <span>Status</span>
              </div>
              {recentTrades.map(t => {
                const tone = toneForNumber(t.net_ret_pct ?? 0);
                const rowCls = t.status === "open" ? "is-open"
                  : tone === "pos" ? "is-pos"
                  : tone === "neg" ? "is-neg" : "";
                return (
                  <div key={t.trade_id} className={cn("u-act-row", rowCls)}>
                    <span className="u-mono text-fg">{t.entry_date}</span>
                    <span>
                      <span className="u-chip u-chip-accent">{t.engine}</span>
                    </span>
                    <span className="u-caption uppercase text-fg-2 tracking-wide">
                      {t.regime_at_entry}
                    </span>
                    <span className={cn(
                      "text-right u-mono font-semibold",
                      tone === "pos" ? "text-success"
                      : tone === "neg" ? "text-danger"
                      : "text-fg-2")}>
                      {fmtPct(t.net_ret_pct)}
                    </span>
                    <span className="text-right u-mono-sm text-fg-3">
                      {t.days_held !== null ? `${t.days_held}d` : "holding"}
                    </span>
                    <span>
                      <span className={cn("u-chip",
                        t.status === "open" ? "u-chip-accent"
                        : t.status === "closed" ? "u-chip-neutral"
                        : "u-chip-warning")}>
                        {t.status}
                      </span>
                    </span>
                  </div>
                );
              })}
            </>
          )}
        </div>

        <LatestDecisionPreview state={state} trades={trades ?? []} />
      </section>

      {/* UX-1 Commit K — trade blotter live feed and the macro    */}
      {/* insights ticker are both detailed telemetry. Demoted     */}
      {/* under expanders so the page presents a calm primary      */}
      {/* surface and reveals deeper detail only on request.       */}
      <AdvancedDetails label="Trade activity feed (advanced)">
        <TradeBlotter />
      </AdvancedDetails>

      <AdvancedDetails label="Detailed insights ticker (advanced)">
      <section className="u-ticker">
        <TickerCell label="Regime"
          value={state?.stress_regime ? "STRESS"
                 : state?.directional_regime ? "DIRECTIONAL" : "NEUTRAL"}
          sub={`${state?.gates_favorable ?? 0}/4 gates favorable`} />
        <TickerCell label="Engine armed"
          value={state?.engine && state.engine !== "none"
                 ? `Engine ${state.engine}` : "None"}
          sub={state?.fire ? "FIRING" : "standing by"} />
        <TickerCell label="Open positions"
          value={String(summary?.open_positions_count ?? 0)}
          sub={recentTrades.filter(t => t.status === "open").length > 0
            ? "monitoring exits" : "no exposure"} />
        <TickerCell label="Anomalies"
          value={`${anomSummary?.total_open ?? 0} open`}
          sub={`${anomSummary?.by_severity?.critical ?? 0}c · ${
            anomSummary?.by_severity?.warning ?? 0}w · ${
            anomSummary?.by_severity?.info ?? 0}i`}
          tone={(anomSummary?.by_severity?.critical ?? 0) > 0 ? "danger"
                : (anomSummary?.by_severity?.warning ?? 0) > 0 ? "warning" : "neutral"} />
        <TickerCell label="Last 5 trades"
          value={<WinLossStrip trades={recentTrades.slice(0, 5)} />}
          sub={`latest ${recentTrades[0]?.entry_date ?? "—"}`} />
        <TickerCell label="Equity peak"
          value={equity
            ? fmtUSD(Math.max(...equity.map(p => p.equity)))
            : "—"}
          sub={equity
            ? `${(((summary?.equity ?? 0) -
                    Math.max(...equity.map(p => p.equity)))
                  / Math.max(...equity.map(p => p.equity), 1) * 100).toFixed(2)}% off peak`
            : "—"} />
        <TickerCell label="Health"
          value={health?.overall?.toUpperCase() ?? "—"}
          sub={health?.overall === "healthy" ? "all systems nominal"
               : health?.overall === "failed" ? "failed run" : "degraded"}
          tone={health?.overall === "healthy" ? "success"
                : health?.overall === "failed" ? "danger" : "warning"} />
      </section>
      </AdvancedDetails>
    </div>
  );
}

// =========================================================================
// HERO derivation — human narrative, no debug artifacts
// =========================================================================

function ExploratoryBannerWired() {
  const { data } = useLatestPaperRun();
  const exploratoryCount = data?.exploratory_trades ?? 0;
  const details = data?.details as Record<string, unknown> | undefined;
  const gateMode = details?.gate_mode as string | undefined;
  const active = gateMode === "exploratory" || exploratoryCount > 0;
  if (!active) return null;
  return (
    <div className="mt-3">
      <ExploratoryBanner active={active}
                           lastExploratory={exploratoryCount > 0} />
    </div>
  );
}


function pipelineLabel(
  status: string | undefined, fire: boolean,
): string {
  if (!status) return "IDLE";
  const s = status.toLowerCase();
  if (s === "failed") return "FAILED";
  if (s === "partial") return "PARTIAL";
  if (s === "success") {
    // SUCCESS + engine idle = READY (reduces "success / none armed" confusion)
    return fire ? "RUNNING" : "READY";
  }
  return s.toUpperCase();
}


// UX-1 Commit C — single calm sentence summarising current state.
// Derived from data already fetched on the page (no new hook).
// Order: critical anomalies > pipeline failure > cautious gates >
// normal. Result feeds the top-of-page "am I okay?" line.
function deriveCalmState({
  state, summary, anomSummary,
}: {
  state: CurrentState | undefined;
  summary: PaperSummary | undefined;
  anomSummary: AnomalySummary | undefined;
}): {
  tone: string;
  chip: "success" | "warning" | "danger" | "accent";
  sentence: string;
} {
  if (!state || !summary) {
    return {
      tone: "Warming up",
      chip: "warning",
      sentence:
        "System is starting up. Once the daily run finishes, "
        + "your account summary will appear here. No action needed.",
    };
  }
  const crit = anomSummary?.by_severity?.critical ?? 0;
  if (crit > 0) {
    return {
      tone: "Needs attention",
      chip: "danger",
      sentence:
        `Something needs attention (${crit} flagged). `
        + "Open System diagnostics below for the specific reason.",
    };
  }
  if (summary.pipeline_status === "failed") {
    return {
      tone: "Needs attention",
      chip: "danger",
      sentence:
        "Today's automated workflow ran into trouble. The team "
        + "reviews these on the Ops page. Your account is unaffected.",
    };
  }
  const gatesFav = state.gates_favorable ?? 0;
  if (gatesFav <= 1) {
    return {
      tone: "Cautious",
      chip: "warning",
      sentence:
        "Trading activity is intentionally cautious today — most "
        + "safety checks are signalling caution. No action needed.",
    };
  }
  return {
    tone: "Operating normally",
    chip: "success",
    sentence:
      "System operating normally. No action needed right now.",
  };
}


// UX-1 Commit C — plain-English strategy name for visible chips.
// Engineering identifiers (engine === "A" / "B") preserved
// throughout the codebase; this is a display-only helper.
function strategyHumanName(engine: string | null | undefined): string {
  if (engine === "A") return "Buy-the-dip strategy";
  if (engine === "B") return "Defensive strategy";
  return "Strategy";
}


function deriveHero({
  state, summary, anomSummary,
}: {
  state: CurrentState | undefined;
  summary: PaperSummary | undefined;
  anomSummary: AnomalySummary | undefined;
}): {
  headline: string; body: string;
  word: string; glow: string;
  chip: "success" | "danger" | "warning" | "accent";
  ring: "is-success" | "is-danger" | "is-warning" | "is-accent";
  toneLabel: string;
} {
  if (!summary || !state) {
    return {
      headline: "System initializing",
      body: "Waiting for the daily pipeline to produce its first evaluation.",
      word: "text-warning", glow: "u-glow-warning",
      chip: "warning", ring: "is-warning",
      toneLabel: "Warming up",
    };
  }

  const crit = anomSummary?.by_severity?.critical ?? 0;
  const warn = anomSummary?.by_severity?.warning ?? 0;

  if (crit > 0 || summary.pipeline_status === "failed") {
    return {
      headline: "System degraded — review required",
      body: crit > 0
        ? `${crit} critical anomaly open. Pause new entries until cleared.`
        : "Pipeline failed on last run. Diagnose before re-enabling.",
      word: "text-danger", glow: "u-glow-danger",
      chip: "danger", ring: "is-danger",
      toneLabel: "Needs attention",
    };
  }

  if (warn > 0 || summary.pipeline_status === "partial") {
    return {
      headline: "Monitoring — non-critical issues present",
      body: warn > 0
        ? `${warn} warning-level anomaly${warn === 1 ? "" : "s"} open. Production unaffected but worth a glance.`
        : "Pipeline ran partially. Some non-critical data sources missing.",
      word: "text-warning", glow: "u-glow-warning",
      chip: "warning", ring: "is-warning",
      toneLabel: "Watching",
    };
  }

  const regimeName = state.stress_regime ? "Stress regime"
    : state.directional_regime ? "Directional regime"
    : "Neutral regime";
  const engine = state.engine === "A" ? "Engine A (mean reversion)"
    : state.engine === "B" ? "Engine B (credit + rates)"
    : "neither engine";

  if (state.fire) {
    return {
      headline: `${regimeName} — ${engine} firing long`,
      body: `${summary.open_positions_count} open position${
        summary.open_positions_count === 1 ? "" : "s"
      }. System will hold to target exit. No operator action required.`,
      word: "text-success", glow: "u-glow-success",
      chip: "success", ring: "is-success",
      toneLabel: "Healthy",
    };
  }

  const blockers = extractBlockers(state.reason);
  return {
    headline: `${regimeName} — standing by`,
    body: blockers.length === 0
      ? "All gates favourable. New signals will fill on the next "
        + "trading bar (same-bar fills forbidden)."
      : `${engine} waiting on ${joinEn(blockers.slice(0, 2))} to align.`,
    word: "text-success", glow: "u-glow-success",
    chip: "success", ring: "is-success",
    toneLabel: "Healthy",
  };
}

function extractBlockers(reason: string): string[] {
  return (reason.match(/(\w+)=False/g) ?? [])
    .map(t => t.split("=")[0])
    .filter(k => k !== "fire" && k !== "stress_regime" && k !== "directional_regime")
    .map(humanize);
}

function joinEn(xs: string[]): string {
  if (xs.length === 0) return "";
  if (xs.length === 1) return xs[0];
  return xs.slice(0, -1).join(", ") + " and " + xs.at(-1);
}

// =========================================================================
// Intelligence derivation
// =========================================================================

type IntelTone = "pos" | "neg" | "warn" | "neutral" | "accent";
interface IntelItem { text: string; tone: IntelTone; }

function deriveIntelligence({
  state, perf, anomalies, winRate, recentTrades,
}: {
  state: CurrentState | undefined;
  perf: PerformanceAttribution | undefined;
  anomalies: AnomalyEvent[];
  winRate: number | null;
  recentTrades: TradeRow[];
}): {
  topDriver: IntelItem; topBlocker: IntelItem;
  topConcern: IntelItem; nextTrigger: IntelItem;
} {
  const topDriver: IntelItem = (() => {
    if (!perf) return { text: "Awaiting first trade", tone: "neutral" };
    const a = perf.engine_a, b = perf.engine_b;
    if (a.n_trades === 0 && b.n_trades === 0)
      return { text: "No engines fired yet", tone: "neutral" };
    const winner = a.total_pnl_pct >= b.total_pnl_pct ? "A" : "B";
    const w = winner === "A" ? a : b;
    return {
      text: `Engine ${winner} · ${fmtPct(w.total_pnl_pct)}`,
      tone: w.total_pnl_pct > 0 ? "pos" : "neg",
    };
  })();

  const topBlocker: IntelItem = (() => {
    if (!state) return { text: "Pipeline pending", tone: "neutral" };
    if (state.fire)
      return { text: `None — Engine ${state.engine} firing`, tone: "pos" };
    const falseKeys = extractBlockers(state.reason);
    if (falseKeys.length === 0)
      return { text: "Conditions met", tone: "neutral" };
    return { text: falseKeys.slice(0, 2).join(", "), tone: "warn" };
  })();

  const topConcern: IntelItem = (() => {
    const crit = anomalies.find(a => a.severity === "critical");
    if (crit) return { text: crit.title, tone: "neg" };
    const warn = anomalies.find(a => a.severity === "warning");
    if (warn) return { text: warn.title, tone: "warn" };
    if (winRate !== null && winRate < 0.4)
      return { text: `Win rate low · ${(winRate * 100).toFixed(0)}%`, tone: "warn" };
    return { text: "No open concerns", tone: "pos" };
  })();

  const nextTrigger: IntelItem = (() => {
    if (!state) return { text: "Next pipeline run", tone: "neutral" };
    if (state.fire) {
      const openCount = recentTrades.filter(t => t.status === "open").length;
      return {
        text: openCount > 0 ? `Target exit · ${openCount} open`
                            : "Entry pending",
        tone: "accent",
      };
    }
    if (state.stress_regime)
      return { text: "Oversold bounce setup", tone: "accent" };
    if (state.directional_regime)
      return { text: "Credit + rates alignment", tone: "accent" };
    return { text: `${state.gates_favorable}/4 gates`, tone: "neutral" };
  })();

  return { topDriver, topBlocker, topConcern, nextTrigger };
}

function computeWinRate(trades: TradeRow[]): number | null {
  const closed = trades.filter(t => t.net_ret_pct !== null && t.status === "closed");
  if (closed.length === 0) return null;
  const wins = closed.filter(t => (t.net_ret_pct ?? 0) > 0).length;
  return wins / closed.length;
}

function humanize(s: string): string {
  return s.replace(/_/g, " ");
}

function fmtSignedCompact(n: number): string {
  const s = n > 0 ? "+" : n < 0 ? "−" : "";
  return `${s}$${Math.abs(n).toFixed(2)}`;
}

// =========================================================================
// Subcomponents
// =========================================================================

function IntelTile({ label, item }: { label: string; item: IntelItem }) {
  const text = {
    pos: "text-success", neg: "text-danger", warn: "text-warning",
    accent: "text-accent", neutral: "text-fg",
  }[item.tone];
  const dot = {
    pos: "u-dot-success", neg: "u-dot-danger", warn: "u-dot-warning",
    accent: "u-dot-accent", neutral: "",
  }[item.tone];
  return (
    <div className="u-card-tight" style={{ padding: "12px 14px" }}>
      <div className="flex items-center gap-1.5 mb-1.5">
        {dot && <span className={cn("u-dot", dot)}
                      style={{ width: 6, height: 6 }} />}
        <span className="u-ticker-label">{label}</span>
      </div>
      <div className={cn("u-caption font-semibold leading-snug", text)}>
        {item.text}
      </div>
    </div>
  );
}

function StatCell({
  label, value, sub, tone = "neutral", size = "sec", glow = false,
}: {
  label: string; value: string; sub: string;
  tone?: "pos" | "neg" | "neutral";
  size?: "mega" | "hero" | "sec";
  glow?: boolean;
}) {
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg";
  const glowCls = !glow ? "" : tone === "pos" ? "u-glow-success"
    : tone === "neg" ? "u-glow-danger" : "";
  const sizeCls = size === "mega" ? "u-num-mega"
    : size === "hero" ? "u-num-hero" : "u-num-sec";
  return (
    <div className="u-stat-cell">
      <div className="u-ticker-label mb-3">{label}</div>
      <div className={cn(sizeCls, cls, glowCls)}>{value}</div>
      <div className="u-caption-2 mt-2">{sub}</div>
    </div>
  );
}

// CF-4: compact banner cell — replaces 4×HeroMetaCell vertical block.
function BannerCell({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <span className="u-label-sm text-fg-3">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  );
}

function SideCard({
  title, hint, children,
}: {
  title: string; hint: string; children: React.ReactNode;
}) {
  return (
    <div className="u-card-tight">
      <div className="mb-2"><Label>{title}</Label></div>
      <div className="u-caption-2 mb-3">{hint}</div>
      {children}
    </div>
  );
}

function RegimeBadge({ state }: { state: CurrentState | undefined }) {
  if (!state)
    return <span className="u-chip u-chip-neutral">PENDING</span>;
  if (state.stress_regime)
    return <span className="u-chip u-chip-danger">STRESS</span>;
  if (state.directional_regime)
    return <span className="u-chip u-chip-accent">DIRECTIONAL</span>;
  return <span className="u-chip u-chip-neutral">NEUTRAL</span>;
}

function AttributionBlock({
  perf,
}: { perf: PerformanceAttribution | undefined }) {
  if (!perf) {
    return <div className="u-caption-2 italic">Waiting for closed trades.</div>;
  }
  const max = Math.max(
    Math.abs(perf.engine_a.total_pnl_pct),
    Math.abs(perf.engine_b.total_pnl_pct), 0.01,
  );
  return (
    <div className="space-y-3.5">
      <AttributionRow eng="A" label="Mean reversion"
                      stats={perf.engine_a} max={max} />
      <AttributionRow eng="B" label="Credit + rates"
                      stats={perf.engine_b} max={max} />
    </div>
  );
}

function AttributionRow({
  eng, label, stats, max,
}: {
  eng: "A" | "B"; label: string;
  stats: {
    n_trades: number; total_pnl_pct: number; win_rate: number;
    avg_return_pct?: number; sharpe_proxy?: number;
  };
  max: number;
}) {
  const tone = toneForNumber(stats.total_pnl_pct);
  const cls = tone === "pos" ? "text-success"
    : tone === "neg" ? "text-danger" : "text-fg-2";
  const pct = Math.min(100, Math.abs(stats.total_pnl_pct) / max * 100);
  const health = engineHealth(stats);
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="u-chip u-chip-accent">{eng}</span>
          <span className="u-caption text-fg truncate">{label}</span>
          <span className={cn("u-chip", health.chipCls)}
                title={health.note}>
            {health.status}
          </span>
        </div>
        <div className={cn("u-num-md font-semibold", cls)}>
          {fmtPct(stats.total_pnl_pct)}
        </div>
      </div>
      <div className="u-bar-track is-thick">
        <div className={cn("u-bar-fill",
          tone === "pos" ? "is-pos" : tone === "neg" ? "is-neg" : "")}
          style={{ left: 0, width: `${pct}%` }} />
      </div>
      <div className="u-caption-2 mt-1.5 flex items-center justify-between">
        <span>{stats.n_trades} trades</span>
        <span className={cn("font-semibold",
          stats.win_rate >= 0.55 ? "text-success"
          : stats.win_rate < 0.4 ? "text-danger" : "text-warning")}>
          {(stats.win_rate * 100).toFixed(0)}% win
        </span>
      </div>
      {health.note && (
        <div className="u-caption-2 mt-1 italic text-fg-3">
          {health.note}
        </div>
      )}
      {/* Phase 11K.1 — impact-on-Sharpe (observational only) */}
      <div
        className="u-caption-2 mt-1 text-fg-3"
        title="Engine attribution reflects historical paper-trading contribution only. It does not indicate future performance or strategy selection."
      >
        Historical Sharpe contribution:{" "}
        <span className={cn("font-semibold",
          (stats.sharpe_proxy ?? 0) >= 1.0 ? "text-success"
          : (stats.sharpe_proxy ?? 0) <= -0.3 ? "text-danger"
          : "text-warning")}>
          {(stats.sharpe_proxy ?? 0) >= 1.0 ? "historical contribution observed"
            : (stats.sharpe_proxy ?? 0) <= -0.3 ? "historical drag observed"
            : "no clear historical contribution"}
        </span>
      </div>
      {(stats.sharpe_proxy ?? 0) <= -0.3 && (
        <div className="u-caption-2 mt-0.5 text-warning">
          Note: historical drag observed under current regime — review context only.
        </div>
      )}
    </div>
  );
}

// Phase 11K.1 — Engine attribution: status codes are STATE LABELS
// only. Notes are observational; never directives.
function engineHealth(stats: {
  n_trades: number; total_pnl_pct: number; win_rate: number;
  avg_return_pct?: number; sharpe_proxy?: number;
}): { status: string; chipCls: string; note: string } {
  const s = stats.sharpe_proxy;
  const avg = stats.avg_return_pct ?? 0;
  if (stats.n_trades < 10) {
    return {
      status: "MONITORING contribution level",
      chipCls: "u-chip-neutral",
      note: "Sample size too small to characterise reliability.",
    };
  }
  if ((s != null && s < 0) || avg < 0 || stats.total_pnl_pct < 0
       || stats.win_rate < 0.5) {
    return {
      status: "LOW contribution level",
      chipCls: "u-chip-danger",
      note: "Historical drag observed in this regime. Review context only.",
    };
  }
  if (s != null && s > 1.0 && stats.win_rate >= 0.55) {
    return {
      status: "HIGH contribution level",
      chipCls: "u-chip-success",
      note: "Historically active under similar conditions. Review context only.",
    };
  }
  return {
    status: "MIXED contribution level",
    chipCls: "u-chip-warning",
    note: "Mixed historical contribution across regimes. Review context only.",
  };
}

function RiskBlock({
  summary, anomSummary, openTrades,
}: {
  summary: PaperSummary | undefined;
  anomSummary: AnomalySummary | undefined;
  openTrades: number;
}) {
  const dd = summary?.max_drawdown_pct ?? 0;
  const ddTone = dd < -5 ? "text-danger" : dd < -2 ? "text-warning" : "text-fg";
  const anomCls = (anomSummary?.by_severity?.critical ?? 0) > 0 ? "text-danger"
                 : (anomSummary?.by_severity?.warning ?? 0) > 0 ? "text-warning"
                 : "text-success";
  return (
    <div className="space-y-2.5">
      <KVRow label="Open positions" value={String(openTrades)} />
      <KVRow label="Current drawdown"
             value={fmtPct(summary?.max_drawdown_pct)}
             valueCls={ddTone} />
      <KVRow label="Open anomalies"
             value={String(anomSummary?.total_open ?? 0)}
             valueCls={anomCls} />
    </div>
  );
}

function KVRow({ label, value, valueCls = "text-fg" }: {
  label: string; value: string; valueCls?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption text-fg-2">{label}</span>
      <span className={cn("u-mono font-semibold", valueCls)}>{value}</span>
    </div>
  );
}

function NextActionBlock({
  state, health,
}: {
  state: CurrentState | undefined;
  health: SystemHealth | undefined;
}) {
  if (!state) {
    return <div className="u-caption-2 italic">Pipeline pending first run.</div>;
  }
  const action = state.fire
    ? `Monitor open Engine ${state.engine} position. Hold to target exit.`
    : state.stress_regime
      ? "Scanning for oversold mean-reversion entry (loose range + vol elevated)."
      : state.directional_regime
        ? "Waiting for credit_stable AND rates_calm agreement."
        : "Regime unclear — neither engine armed.";
  const healthTone = health?.overall === "healthy" ? "success"
                   : health?.overall === "failed" ? "danger" : "warning";
  return (
    <div className="space-y-3 flex-1 flex flex-col min-h-0">
      <p className="u-body-fg text-accent leading-snug font-medium">
        {action}
      </p>
      <div className="mt-auto flex items-center justify-between
                         pt-3 border-t border-b1">
        <span className="u-ticker-label">System health</span>
        <span className={`u-chip u-chip-${healthTone}`}>
          <span className={`u-dot u-dot-${healthTone}`} />
          {health?.overall?.toUpperCase() ?? "—"}
        </span>
      </div>
    </div>
  );
}

function LatestDecisionPreview({
  state, trades,
}: {
  state: CurrentState | undefined; trades: TradeRow[];
}) {
  const latest = trades[0];
  const src = latest ? {
    dateLabel: latest.entry_date,
    title: latest.engine === "A"
            ? "Engine A · mean-reversion long"
            : latest.engine === "B"
              ? "Engine B · directional long"
              : "No entry",
    humanReason: buildHumanReason(latest),
    blockers: [] as string[],
    regime: latest.regime_at_entry,
    engine: latest.engine,
    isLive: false,
    ret: latest.net_ret_pct,
  } : state ? {
    dateLabel: state.as_of_date,
    title: state.fire
            ? `Engine ${state.engine} · entry fired`
            : "Stood by — no entry today",
    humanReason: buildHumanStateReason(state),
    blockers: extractBlockers(state.reason),
    regime: state.stress_regime ? "stress"
            : state.directional_regime ? "directional" : "none",
    engine: state.engine,
    isLive: true,
    ret: null,
  } : null;

  return (
    <div className="u-card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <Label>Latest Decision</Label>
          <div className="u-caption-2 mt-0.5">
            {src ? (src.isLive ? "Live — today's evaluation" : "Most recent trade")
                 : "—"}
          </div>
        </div>
        {src && (
          <span className={cn("u-chip",
            src.isLive ? "u-chip-accent" : "u-chip-neutral")}>
            {src.isLive
              ? <><span className="u-dot u-dot-accent u-dot-pulse" />LIVE</>
              : "CLOSED"}
          </span>
        )}
      </div>

      {!src ? (
        <div className="u-caption-2 italic">Awaiting first pipeline run.</div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="u-mono-sm mb-1 text-fg-3">
                {src.dateLabel}
                {src.regime ? ` · ${src.regime.toUpperCase()}` : ""}
              </div>
              <div className="u-body-fg font-semibold leading-snug">
                {src.title}
              </div>
            </div>
            {src.ret !== null && (
              <span className={cn("u-num-md font-semibold shrink-0",
                toneForNumber(src.ret ?? 0) === "pos" ? "text-success"
                : toneForNumber(src.ret ?? 0) === "neg" ? "text-danger"
                : "text-fg")}>
                {fmtPct(src.ret)}
              </span>
            )}
          </div>

          <div>
            <div className="u-ticker-label mb-2">Reasoning</div>
            <p className="u-caption text-fg leading-relaxed">
              {src.humanReason}
            </p>
          </div>

          {src.blockers.length > 0 && (
            <div>
              <div className="u-ticker-label mb-2">Blocking</div>
              <div className="flex flex-wrap gap-1">
                {src.blockers.map(b => (
                  <span key={b} className="u-chip u-chip-warning">{b}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function buildHumanReason(t: TradeRow): string {
  const eng = t.engine === "A" ? "the mean-reversion engine"
    : t.engine === "B" ? "the directional engine" : "no engine";
  const reg = t.regime_at_entry === "stress" ? "a stress regime"
    : t.regime_at_entry === "directional" ? "a directional regime"
    : "a neutral regime";
  const outcome = t.net_ret_pct === null
    ? "Position still open."
    : t.net_ret_pct > 0
      ? `Closed at ${fmtPct(t.net_ret_pct)} — thesis confirmed.`
      : `Closed at ${fmtPct(t.net_ret_pct)} — thesis rejected.`;
  return `${cap(eng)} fired a long entry into ${reg} on ${t.entry_date}. ${outcome}`;
}

function buildHumanStateReason(s: CurrentState): string {
  const reg = s.stress_regime ? "Stress regime active"
    : s.directional_regime ? "Directional regime active"
    : "Regime currently neutral";
  if (s.fire) {
    return `${reg}. Engine ${s.engine} conditions aligned — long entry fired.`;
  }
  const blockers = extractBlockers(s.reason);
  if (blockers.length === 0) {
    return `${reg}. All gates favourable. New signals fill on the `
      + `next trading bar — same-bar fills are forbidden by the `
      + `next-bar guard.`;
  }
  return `${reg}. Entry blocked until ${joinEn(blockers.slice(0, 3))} align.`;
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function ActivityFallback({
  state, summary,
}: {
  state: CurrentState | undefined;
  summary: PaperSummary | undefined;
}) {
  const pct = (summary?.pipeline_status === "success" ? "running" : "idle");
  const regime = state?.stress_regime ? "STRESS"
    : state?.directional_regime ? "DIRECTIONAL" : "NEUTRAL";
  const blocking = extractBlockers(state?.reason ?? "");

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      <div className="u-card-tight">
        <div className="u-ticker-label mb-1.5">Pipeline</div>
        <div className="u-body-fg font-semibold">{pct.toUpperCase()}</div>
        <div className="u-caption-2 mt-1 font-mono">
          {summary?.last_decision_ts
            ? new Date(summary.last_decision_ts).toLocaleString()
            : "not run"}
        </div>
      </div>
      <div className="u-card-tight">
        <div className="u-ticker-label mb-1.5">Current Regime</div>
        <div className="u-body-fg font-semibold">{regime}</div>
        <div className="u-caption-2 mt-1">
          gates: {state?.gates_favorable ?? 0}/4 favorable
        </div>
      </div>
      <div className="u-card-tight">
        <div className="u-ticker-label mb-1.5">Blocking</div>
        {blocking.length === 0 ? (
          <>
            <div className="u-body-fg font-semibold">No blockers</div>
            <div className="u-caption-2 mt-1">
              Will fire on next qualifying bar.
            </div>
          </>
        ) : (
          <>
            <div className="u-body-fg font-semibold">
              {blocking.length} condition{blocking.length !== 1 ? "s" : ""}
            </div>
            <div className="u-caption-2 mt-1">{blocking.join(", ")}</div>
          </>
        )}
      </div>
    </div>
  );
}

function TickerCell({
  label, value, sub, tone = "neutral",
}: {
  label: string; value: React.ReactNode; sub: string;
  tone?: "success" | "danger" | "warning" | "neutral";
}) {
  const cls = {
    success: "text-success", danger: "text-danger",
    warning: "text-warning", neutral: "text-fg",
  }[tone];
  return (
    <div className="u-ticker-cell">
      <div className="u-ticker-label">{label}</div>
      <div className={cn("u-ticker-value", cls)}>{value}</div>
      <div className="u-ticker-sub">{sub}</div>
    </div>
  );
}

function WinLossStrip({ trades }: { trades: TradeRow[] }) {
  if (trades.length === 0)
    return <span className="text-fg-3">—</span>;
  return (
    <span className="inline-flex items-center gap-1">
      {trades.map(t => {
        const tone = toneForNumber(t.net_ret_pct ?? 0);
        const bg = tone === "pos" ? "var(--success)"
                 : tone === "neg" ? "var(--danger)" : "var(--fg-4)";
        return (
          <span key={t.trade_id}
                className="inline-block rounded-sm"
                style={{
                  width: 8, height: 12, background: bg,
                  opacity: t.status === "open" ? 0.5 : 1,
                }} />
        );
      })}
    </span>
  );
}
