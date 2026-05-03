// PAGE 5 — Ops

import { useSystemHealth, useAnomalies } from "@/lib/operator/hooks";
import {
  Card, Label, Pill, SectionHeader, EmptyState, Divider,
} from "@/components/ui/primitives";
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

  return (
    <div className="max-w-[1440px] mx-auto px-8 py-8 space-y-6">
      <header>
        <Label>Operations</Label>
        <h1 className="u-title mt-1">System Ops</h1>
        <p className="u-caption mt-1">
          Pipeline health, data freshness, schedulers, settings.
        </p>
      </header>

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
