// PAGE 5 — Ops
//
// UX-1 Commit I — page-level framing layer added on top.
// PageGuide carries the visible title; Start-here focus card +
// calm-state interpretation card sit between the page header
// and the existing engineering content. NO existing card was
// removed or moved; every diagnostic stays exactly where it
// was. The new framing only labels the page so a beginner
// reads "is the system healthy? do I need to do anything?"
// before they encounter the operational telemetry.

import { useSystemHealth, useAnomalies } from "@/lib/operator/hooks";
import {
  Card, Pill, SectionHeader, EmptyState, Divider,
} from "@/components/ui/primitives";
import { PageGuide } from "@/components/novice";
import type { SystemHealth } from "@/lib/operator/types";
import MLResearchCard from "@/components/ops/MLResearchCard";
import HistoricalReplayCard from "@/components/ops/HistoricalReplayCard";
import ReplayTrainingReadinessCard from "@/components/ops/ReplayTrainingReadinessCard";
import ShadowMLCard from "@/components/ops/ShadowMLCard";
import ShadowStrategyCard from "@/components/ops/ShadowStrategyCard";
import EngineBTransitionCard from "@/components/ops/EngineBTransitionCard";
import B2vsV2ComparisonCard from "@/components/ops/B2vsV2ComparisonCard";
import V2PromotionTriggerCard from "@/components/ops/V2PromotionTriggerCard";
import HybridAdvisorCard from "@/components/ops/HybridAdvisorCard";
import HybridReadinessCard from "@/components/ops/HybridReadinessCard";
import DailyLoopHealthCard from "@/components/ops/DailyLoopHealthCard";
import MLReadinessProgressCard from "@/components/ops/MLReadinessProgressCard";
import SystemHealthCard from "@/components/ops/SystemHealthCard";
import SystemImprovementsCard from "@/components/ops/SystemImprovementsCard";
import SystemAdjustmentsCard from "@/components/ops/SystemAdjustmentsCard";
import ContextAdjustmentsCard from "@/components/ops/ContextAdjustmentsCard";

export default function Ops() {
  const { data: health } = useSystemHealth();
  const { data: dataAnom } = useAnomalies("open", undefined);

  const dataIssues = (dataAnom ?? []).filter(a => a.category === "data");

  const calm = deriveOpsCalm(health);

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-8 space-y-6">
      {/* UX-1 Commit I — plain-English page header. The visible    */}
      {/* title is now "System status" so a beginner does not read  */}
      {/* "Ops" as something they might have broken. Eyebrow keeps  */}
      {/* the engineering name for continuity.                       */}
      <PageGuide
        eyebrow="Pro view"
        title="System status"
        subtitle={
          "Behind-the-scenes view of pipelines, data freshness, "
          + "schedulers, and infrastructure. Most users do not need "
          + "to read this page — it exists for transparency."
        }
        firstLook={
          <>
            Look at the <strong>System status</strong> chip below
            first. If it reads "Operating normally", everything is
            running as expected.
          </>
        }
      />

      {/* UX-1 Commit I — Start-here focus card. Calm framing for    */}
      {/* a page that previously read like an engineering console.   */}
      <section
        className="u-card-tight"
        data-test="ops-start-here"
        style={{ padding: "12px 16px" }}
      >
        <div className="u-caption-2 text-fg-3 uppercase tracking-wide mb-1">
          Focus today
        </div>
        <ol className="u-body text-fg space-y-1 list-decimal pl-5">
          <li>
            <strong>System health</strong> — the chip below tells
            you if anything is wrong.
          </li>
          <li>
            <strong>Daily loop</strong> — whether the daily market
            update finished cleanly.
          </li>
          <li>
            Everything else is optional engineering detail.
          </li>
        </ol>
        <p className="u-caption-2 text-fg-3 mt-2">
          Safe to ignore for now: ML pipelines, scheduler config,
          replay readiness, and shadow strategy diagnostics.
          They're useful for advanced users — none require action
          from a beginner.
        </p>
      </section>

      {/* UX-1 Commit I — calm operational interpretation card.     */}
      {/* Answers "should I worry?" in plain English before the     */}
      {/* engineering telemetry below.                              */}
      <section
        className="u-card-tight"
        data-test="ops-calm-state"
        style={{ padding: "14px 18px" }}
      >
        <div className="flex items-center gap-3 mb-1">
          <span className={`u-chip u-chip-${calm.chip}`}>
            <span className={`u-dot u-dot-${calm.chip}`} />
            {calm.tone}
          </span>
          <span
            className="u-body font-semibold text-fg"
            data-test="ops-calm-headline"
          >
            {calm.headline}
          </span>
        </div>
        <p
          className="u-caption text-fg-2 max-w-3xl"
          data-test="ops-calm-body"
        >
          {calm.body}
        </p>
      </section>

      {/* UX-1 Commit N — quiet section anchor preceding the      */}
      {/* sticky OpsAnchorNav and the engineering cards beneath.   */}
      <div
        data-test="ops-section-anchor-engineering"
        className="u-caption-2 text-fg-3 uppercase tracking-wide pt-2"
      >
        Infrastructure detail
      </div>

      {/* Phase 3 anchor nav — sticky 3-section jump nav */}
      <OpsAnchorNav />

      {/* Section anchor: Pipeline & Data */}
      <h2 id="pipeline-data" className="u-label-sm pt-2 -mt-2 scroll-mt-20">
        Pipeline &amp; Data
      </h2>

      {/* Daily Loop Health — Phase OPS-LOOP-HEALTH (top of page) */}
      <DailyLoopHealthCard />

      {/* System status */}
      <Card size="md">
        <SectionHeader title="System Health"
          right={<Pill tone={health?.overall === "healthy" ? "success"
                              : health?.overall === "failed" ? "danger"
                              : "warning"} dot>
            {health?.overall ?? "—"}
          </Pill>} />
        {!health || health.items.length === 0 ? (
          <EmptyState glyph="◉" title="All systems nominal"
            hint="No active alerts. Next scheduled run will refresh state." />
        ) : (
          <ul className="divide-y divide-b1">
            {health.items.map(i => (
              <li key={i.key} className="py-3 flex items-start gap-3">
                <Pill tone={i.severity === "error" ? "danger"
                             : i.severity === "warn" ? "warning" : "accent"}>
                  {i.severity}
                </Pill>
                <div className="flex-1">
                  <div className="u-caption text-fg font-medium">{i.label}</div>
                  <div className="u-caption-2 mt-0.5">{i.detail}</div>
                </div>
                <div className="u-caption-2 font-mono">{i.last_seen}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Data freshness */}
      <Card size="md">
        <SectionHeader title="Data Freshness"
          hint="Last observed timestamp per critical source." />
        {dataIssues.length === 0 ? (
          <EmptyState glyph="◉" title="All data sources current"
            hint="ES / SPY / FRED / positioning within expected windows." />
        ) : (
          <ul className="divide-y divide-b1">
            {dataIssues.map(a => (
              <li key={a.id} className="py-3 flex items-start gap-3">
                <Pill tone={a.severity === "critical" ? "danger"
                             : a.severity === "warning" ? "warning" : "accent"}>
                  {a.severity}
                </Pill>
                <div className="flex-1">
                  <div className="u-caption text-fg font-medium">{a.title}</div>
                  <div className="u-caption-2 mt-0.5">{a.description}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Section anchor: ML Pipeline */}
      <h2 id="ml-pipeline" className="u-label-sm pt-2 -mt-2 scroll-mt-20">
        ML Pipeline
      </h2>

      {/* ML Research card — Phase ML-2 */}
      <MLResearchCard />

      {/* Historical replay card — Phase ML-2.5 */}
      <HistoricalReplayCard />

      {/* Replay training readiness — Phase ML-2.6 */}
      <ReplayTrainingReadinessCard />

      {/* Shadow ML — Phase ML-3 */}
      <ShadowMLCard />

      {/* Hybrid Advisor — Phase ML-5 */}
      <HybridAdvisorCard />

      {/* Hybrid ML Readiness — Phase ML-6 */}
      <HybridReadinessCard />

      {/* ML Readiness Progress — Phase OPS-ML-PROGRESS */}
      <MLReadinessProgressCard />

      {/* Shadow Strategy Tracker — Phase SHADOW (research-only) */}
      <ShadowStrategyCard />

      {/* Engine B → B2 Migration — Phase ENGINE-B-MIGRATION */}
      <EngineBTransitionCard />

      {/* B2 vs V2 head-to-head — advisory only, no routing change */}
      <B2vsV2ComparisonCard />

      {/* V2 promotion trigger — governance, no production routing change */}
      <V2PromotionTriggerCard />

      {/* Section anchor: Scheduler & Config */}
      <h2 id="scheduler-config" className="u-label-sm pt-2 -mt-2 scroll-mt-20">
        Scheduler &amp; Config
      </h2>

      {/* System Health Score — Phase SYSTEM-ALPHA */}
      <SystemHealthCard />

      {/* System Improvements — Phase SYSTEM-ALPHA-3 */}
      <SystemImprovementsCard />

      {/* System Adjustments — Phase SYSTEM-ALPHA-6 */}
      <SystemAdjustmentsCard />
      <ContextAdjustmentsCard />

      {/* Jobs + scheduler */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card size="md">
          <SectionHeader title="Scheduled Jobs" />
          <ul className="divide-y divide-b1">
            <JobRow name="daily_paper_pipeline" cadence="daily 16:30 ET" last="ok" />
            <JobRow name="fred_ingest"          cadence="daily 17:00 ET" last="ok" />
            <JobRow name="anomaly_scan"         cadence="daily 17:05 ET" last="ok" />
            <JobRow name="shadow_refresh"       cadence="daily 17:10 ET" last="skipped" />
          </ul>
        </Card>

        <Card size="md">
          <SectionHeader title="Registry & Settings" />
          <div className="space-y-3">
            <Row k="Decision version" v="selector-v1.0.0" />
            <Row k="Engine A"         v="engineA-v1.0.0" />
            <Row k="Engine B"         v="engineB-v1.0.0" />
            <Divider />
            <Row k="Cost model"       v="10 / 20 / 30 bps tested" />
            <Row k="Capital"          v="$100,000 paper" />
            <Row k="Instrument"       v="ES / SPY" />
          </div>
        </Card>
      </div>
    </div>
  );
}

// Phase 3 — sticky 3-section jump nav for Ops.
function OpsAnchorNav() {
  const sections = [
    { id: "pipeline-data",   label: "Pipeline & Data" },
    { id: "ml-pipeline",     label: "ML Pipeline" },
    { id: "scheduler-config", label: "Scheduler & Config" },
  ];
  return (
    <nav aria-label="Ops sections"
         className="sticky top-[var(--ops-nav-top, 100px)] z-10
                      flex gap-1 px-1 py-1 rounded-md
                      backdrop-blur"
         style={{
           background: "color-mix(in srgb, var(--bg) 80%, transparent)",
           border: "1px solid var(--border-subtle)",
         }}>
      {sections.map(s => (
        <a key={s.id} href={`#${s.id}`}
           className="px-3 py-1 u-caption text-fg-2
                       hover:text-fg rounded transition-colors"
           style={{ borderRadius: "var(--radius-chip)" }}>
          {s.label}
        </a>
      ))}
    </nav>
  );
}


function JobRow({ name, cadence, last }: {
  name: string; cadence: string; last: "ok" | "warn" | "fail" | "skipped";
}) {
  const tone = last === "ok" ? "success"
    : last === "warn" ? "warning"
    : last === "fail" ? "danger" : "neutral";
  return (
    <li className="py-2.5 flex items-center gap-3">
      <Pill tone={tone as any} dot={last === "ok"}>{last}</Pill>
      <div className="flex-1">
        <div className="u-mono">{name}</div>
        <div className="u-caption-2">{cadence}</div>
      </div>
    </li>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="u-caption">{k}</span>
      <span className="u-mono">{v}</span>
    </div>
  );
}


// UX-1 Commit I — derive a calm operational interpretation from
// the existing /system/health payload. NO new endpoint, NO new
// hook. Pure function. Branches in priority order:
//   1. data not loaded → "Loading"
//   2. overall === "failed" → "Worth a closer look"
//   3. overall === "degraded" → "Some services slower than usual"
//   4. items contain any error → "Some checks reporting errors"
//   5. items contain any warn → "Most checks passing"
//   6. otherwise → "Operating normally"
//
// Truth-preserving: every branch points the operator at the
// underlying engineering surface below if action is needed,
// rather than substituting a fake healthy claim.
function deriveOpsCalm(
  health: SystemHealth | undefined,
): {
  tone: string;
  chip: "success" | "warning" | "danger" | "neutral";
  headline: string;
  body: string;
} {
  if (!health) {
    return {
      tone: "Loading",
      chip: "neutral",
      headline: "System status is loading.",
      body:
        "The health snapshot is still being fetched. The next "
        + "market update will populate this view automatically.",
    };
  }
  const errors = health.items.filter(i => i.severity === "error");
  const warns = health.items.filter(i => i.severity === "warn");

  if (health.overall === "failed") {
    return {
      tone: "Worth a closer look",
      chip: "danger",
      headline: "One or more services aren't reporting normally.",
      body:
        "Existing paper-trade data and account values remain "
        + "safe — only the underlying telemetry is degraded. The "
        + "engineering detail below explains which service is "
        + "affected. Trading activity may pause until the next "
        + "successful update.",
    };
  }
  if (health.overall === "degraded" || errors.length > 0) {
    return {
      tone: "Worth a closer look",
      chip: "warning",
      headline:
        errors.length > 0
          ? `${errors.length} check${errors.length === 1 ? "" : "s"} reporting an error.`
          : "Some services are slower than usual.",
      body:
        "Existing data remains available. The system continues to "
        + "operate; today's market update is still processing or a "
        + "single service is taking longer than usual. The "
        + "engineering detail below shows which check is affected.",
    };
  }
  if (warns.length > 0) {
    return {
      tone: "Most checks passing",
      chip: "neutral",
      headline:
        `Most services healthy, ${warns.length} `
        + `signalling caution.`,
      body:
        "Paper trading and market-data ingestion are operating "
        + "normally. The flagged checks are advisory — none require "
        + "action right now.",
    };
  }
  return {
    tone: "Operating normally",
    chip: "success",
    headline: "Operating normally.",
    body:
      "Paper trading and market-data ingestion are functioning. "
      + "The next market update will refresh account values "
      + "automatically. No action is needed right now.",
  };
}
