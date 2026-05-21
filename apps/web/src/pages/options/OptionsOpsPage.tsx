// Phase 6b-3-g — Ops surface (engineering · calm-by-default).
//
// Triage-first. Healthy state visually recedes. Failures emerge.
//
// Composition (5 layers, compressed):
//   1. Pulse strip            "engine dormant · all checks pass" or
//                             "engine dormant · 1 issue: universe drift"
//   2. Health triage          5 trust primitives in a calm matrix
//   3. Scheduler              real 2-row table
//   4. Recent runs            real 4-row job_run table
//   5. Pathways               three editorial doorways
//
// Per the queued direction:
//   "Compression over exhaustiveness. Calm-by-default. Healthy
//    systems should visually recede."
//   "The page should feel like the engine room beneath the
//    research floor. Not the main attraction."

import OptionsOpsPulse from
  "@/components/options/OptionsOpsPulse";
import OptionsHealthTriage from
  "@/components/options/OptionsHealthTriage";
import OptionsSchedulerTable from
  "@/components/options/OptionsSchedulerTable";
import OptionsRunHistoryTable from
  "@/components/options/OptionsRunHistoryTable";
// Phase Opt-C2 Pre-Canary 0.5 — canary portfolio status block.
import OptionsCanaryStatus from
  "@/components/options/OptionsCanaryStatus";
import OptionsOpsPathways from
  "@/components/options/OptionsOpsPathways";


export default function OptionsOpsPage() {
  return (
    <div className="opt-ops" data-test="options-ops-page">
      {/* 1. Pulse — triage-first */}
      <OptionsOpsPulse />

      {/* 2. Health triage — 5 trust primitives, calm matrix */}
      <OptionsHealthTriage />

      {/* 3. Scheduler — 2 real rows */}
      <OptionsSchedulerTable />

      {/* 4. Recent runs — 4 real job_run rows */}
      <OptionsRunHistoryTable />

      {/* 5. Canary portfolio status — Phase Opt-C2 Pre-Canary 0.5 */}
      <OptionsCanaryStatus />

      {/* 6. Pathways */}
      <OptionsOpsPathways />
    </div>
  );
}
