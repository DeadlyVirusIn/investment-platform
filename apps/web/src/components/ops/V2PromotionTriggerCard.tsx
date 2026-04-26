// V2 Promotion Trigger panel — Phase 6.
// Renders server-supplied state / gates / confidence values verbatim.
// No client-side recomputation. Operator-action buttons appear only
// in the exact states the API permits. State advancement happens only
// on the next snapshot job run, never directly from the UI.

import { useEffect, useMemo, useState } from "react";

import { Label } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import {
  type ConfidenceBreakdown,
  type GateDetail,
  type SnapshotSummary,
  type V2PromotionState,
  useV2PromotionApprove,
  useV2PromotionGates,
  useV2PromotionRescind,
  useV2PromotionState,
} from "@/lib/v2Promotion/hooks";


const STATE_LABELS: Record<V2PromotionState, string> = {
  NOT_READY: "NOT READY",
  WATCH: "WATCH",
  READY_FOR_REVIEW: "READY FOR REVIEW",
  STRONG_CANDIDATE: "STRONG CANDIDATE",
  APPROVED_FOR_SHADOW_REPLACEMENT: "APPROVED FOR SHADOW REPLACEMENT",
};


function stateChipClass(state: V2PromotionState): string {
  switch (state) {
    case "NOT_READY":          return "u-chip u-chip-neutral";
    case "WATCH":              return "u-chip u-chip-info";
    case "READY_FOR_REVIEW":   return "u-chip u-chip-warning";
    case "STRONG_CANDIDATE":   return "u-chip u-chip-success border border-success";
    case "APPROVED_FOR_SHADOW_REPLACEMENT":
                                return "u-chip u-chip-success";
  }
}


function gateStatusChip(passed: boolean): string {
  return passed
    ? "u-chip u-chip-success"
    : "u-chip u-chip-danger";
}


function fmt(v: number | null | undefined, digits = 2, suffix = ""): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}


function StreakDots({
  current, required, label,
}: {
  current: number;
  required: number;
  label: string;
}) {
  const total = Math.max(required, current);
  const dots = Array.from({ length: total }, (_, i) => i < current);
  const truncate = total > 12;
  const display = truncate ? dots.slice(-12) : dots;
  return (
    <div className="flex items-center gap-2">
      <span className="u-caption-2 w-32 text-fg-3">{label}</span>
      <div className="flex items-center gap-0.5">
        {display.map((on, i) => (
          <span
            key={i}
            className={cn(
              "inline-block w-2 h-2 rounded-full",
              on ? "bg-success" : "bg-bg-2 border border-b1",
            )}
          />
        ))}
      </div>
      <span className="u-caption-2 font-mono ml-1">
        {current} / {required}{truncate ? "+" : ""}
      </span>
    </div>
  );
}


function ConfidenceBar({
  total, breakdown,
}: {
  total: number;
  breakdown: ConfidenceBreakdown | Record<string, never>;
}) {
  const tooltip = useMemo(() => {
    const b = breakdown as ConfidenceBreakdown;
    if (b == null || typeof b !== "object" || !("sample" in b)) return "";
    return [
      `sample        ${(b.sample * 100).toFixed(0)}%`,
      `verdict       ${(b.verdict_streak * 100).toFixed(0)}%`,
      `readiness     ${(b.readiness_streak * 100).toFixed(0)}%`,
      `edge          ${(b.edge * 100).toFixed(0)}%`,
      `tail          ${(b.tail * 100).toFixed(0)}%`,
      `regime        ${(b.regime * 100).toFixed(0)}%`,
      `stability     ${(b.stability * 100).toFixed(0)}%`,
    ].join("\n");
  }, [breakdown]);
  const pct = Math.round(total * 100);
  return (
    <div title={tooltip}>
      <div className="flex items-center justify-between mb-1">
        <span className="u-label-sm">Promotion confidence</span>
        <span className="u-caption-2 font-mono">{pct}%</span>
      </div>
      <div className="h-1.5 bg-bg-2 rounded overflow-hidden">
        <div
          className={cn(
            "h-full transition-all",
            total >= 0.7 ? "bg-success"
            : total >= 0.4 ? "bg-info"
            : "bg-fg-3",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}


function GateRow({ gate }: { gate: GateDetail }) {
  return (
    <tr>
      <td className="py-1 pr-3 font-mono u-caption-2">{gate.name}</td>
      <td className="py-1 pr-3">
        <span className={gateStatusChip(gate.passed)}>
          {gate.passed ? "PASS" : "FAIL"}
        </span>
      </td>
      <td className="py-1 u-caption-2 text-fg-2">{gate.reason}</td>
    </tr>
  );
}


// ---------------------------------------------------------------------------
// Approve modal
// ---------------------------------------------------------------------------

function ApproveModal({
  snapshot, onClose,
}: {
  snapshot: SnapshotSummary;
  onClose: () => void;
}) {
  const [approver, setApprover] = useState("");
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const mut = useV2PromotionApprove();
  const submitting = mut.isPending;
  const trimmedRationale = rationale.trim();
  const valid = approver.trim().length > 0 && trimmedRationale.length >= 20;

  function handleSubmit() {
    if (!valid || submitting) return;
    mut.mutate(
      {
        snapshot_id: snapshot.snapshot_id,
        approver: approver.trim(),
        rationale: trimmedRationale,
      },
      { onSuccess: () => setConfirmed(true) },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-bg u-card max-w-md w-full m-4">
        <Label>Approve V2 as preferred shadow directional sleeve</Label>
        {!confirmed && (
          <>
            <div className="u-caption-2 mt-2 mb-3 text-fg-2">
              This does NOT change production routing. This does NOT
              modify Engine B mode or risk parameters. It only re-labels
              which strategy is the preferred shadow candidate going
              forward. State advancement happens on the next snapshot
              job run.
            </div>
            <div className="space-y-2">
              <div>
                <label className="u-caption-2 text-fg-3">Approver (allowlisted email)</label>
                <input
                  type="email"
                  value={approver}
                  onChange={(e) => setApprover(e.target.value)}
                  className="w-full px-2 py-1 text-sm bg-bg-2 border border-b1 rounded font-mono"
                  placeholder="ops@example.com"
                  disabled={submitting}
                />
              </div>
              <div>
                <label className="u-caption-2 text-fg-3">
                  Rationale (≥ 20 chars; {trimmedRationale.length} / 20)
                </label>
                <textarea
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  rows={4}
                  className="w-full px-2 py-1 text-sm bg-bg-2 border border-b1 rounded"
                  disabled={submitting}
                />
              </div>
              {mut.isError && (
                <div className="u-caption-2 text-danger">
                  {String(mut.error?.message ?? "approval failed")}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="u-btn u-btn-ghost"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!valid || submitting}
                className="u-btn u-btn-primary"
              >
                {submitting ? "Submitting…" : "Approve Shadow Replacement"}
              </button>
            </div>
          </>
        )}
        {confirmed && (
          <div>
            <div className="u-caption-2 mt-2 mb-4 text-success">
              ✓ Approval recorded. Will take effect on the next snapshot
              job run; the UI will update once the new snapshot is
              created.
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="u-btn u-btn-primary"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Rescind modal
// ---------------------------------------------------------------------------

function RescindModal({
  approvedSnapshotId, onClose,
}: {
  approvedSnapshotId: number;
  onClose: () => void;
}) {
  const [approver, setApprover] = useState("");
  const [rationale, setRationale] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const mut = useV2PromotionRescind();
  const submitting = mut.isPending;
  const trimmedRationale = rationale.trim();
  const valid = approver.trim().length > 0 && trimmedRationale.length >= 20;

  function handleSubmit() {
    if (!valid || submitting) return;
    mut.mutate(
      {
        snapshot_id: approvedSnapshotId,
        approver: approver.trim(),
        rationale: trimmedRationale,
      },
      { onSuccess: () => setConfirmed(true) },
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-bg u-card max-w-md w-full m-4">
        <Label>Rescind V2 shadow-preference approval</Label>
        {!confirmed && (
          <>
            <div className="u-caption-2 mt-2 mb-3 text-fg-2">
              Reverts state to STRONG_CANDIDATE on the next snapshot
              job run. Does NOT affect production routing.
            </div>
            <div className="space-y-2">
              <div>
                <label className="u-caption-2 text-fg-3">Approver</label>
                <input
                  type="email"
                  value={approver}
                  onChange={(e) => setApprover(e.target.value)}
                  className="w-full px-2 py-1 text-sm bg-bg-2 border border-b1 rounded font-mono"
                  disabled={submitting}
                />
              </div>
              <div>
                <label className="u-caption-2 text-fg-3">
                  Rationale (≥ 20 chars; {trimmedRationale.length} / 20)
                </label>
                <textarea
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  rows={4}
                  className="w-full px-2 py-1 text-sm bg-bg-2 border border-b1 rounded"
                  disabled={submitting}
                />
              </div>
              {mut.isError && (
                <div className="u-caption-2 text-danger">
                  {String(mut.error?.message ?? "rescission failed")}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={onClose}
                disabled={submitting}
                className="u-btn u-btn-ghost"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!valid || submitting}
                className="u-btn u-btn-danger"
              >
                {submitting ? "Submitting…" : "Rescind Approval"}
              </button>
            </div>
          </>
        )}
        {confirmed && (
          <div>
            <div className="u-caption-2 mt-2 mb-4 text-success">
              ✓ Rescission recorded. Will take effect on the next
              snapshot job run.
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="u-btn u-btn-primary"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Main card
// ---------------------------------------------------------------------------

export default function V2PromotionTriggerCard() {
  const { data: stateData, isLoading } = useV2PromotionState();
  const { data: gatesData } = useV2PromotionGates(
    stateData?.snapshot?.snapshot_id,
  );

  const [showApproveModal, setShowApproveModal] = useState(false);
  const [showRescindModal, setShowRescindModal] = useState(false);

  // Defensive: close modals if the underlying state changes out from under
  // the operator (e.g. a snapshot job ran while the modal was open).
  useEffect(() => {
    if (stateData?.snapshot?.state !== "STRONG_CANDIDATE")
      setShowApproveModal(false);
    if (stateData?.snapshot?.state !== "APPROVED_FOR_SHADOW_REPLACEMENT")
      setShowRescindModal(false);
  }, [stateData?.snapshot?.state]);

  if (isLoading || !stateData) {
    return (
      <div className="u-card">
        <Label>V2 Promotion Trigger</Label>
        <div className="u-caption-2 mt-2">loading…</div>
      </div>
    );
  }

  const snap = stateData.snapshot;
  const approvals = stateData.approvals ?? [];

  if (!snap) {
    return (
      <div className="u-card">
        <div className="flex items-start justify-between mb-2">
          <div>
            <Label>V2 Promotion Trigger</Label>
            <div className="u-caption-2 mt-0.5">
              governance · operator-only decision · no production routing change
            </div>
          </div>
        </div>
        <div className="u-caption-2 text-fg-2">
          Shadow-preference only. Production routing unchanged.
        </div>
        <div className="u-caption-2 mt-3 text-fg-3">
          {stateData.note ?? "No snapshots yet — snapshot job has not run."}
        </div>
      </div>
    );
  }

  const showApproveButton = snap.state === "STRONG_CANDIDATE";
  const showRescindButton = snap.state === "APPROVED_FOR_SHADOW_REPLACEMENT";
  const approvedSnapshotId =
    approvals.find((a) => a.decision === "APPROVE")?.snapshot_id ?? snap.snapshot_id;

  return (
    <div className="u-card">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <Label>V2 Promotion Trigger</Label>
          <div className="u-caption-2 mt-0.5">
            governance · operator-only decision · no production routing change
          </div>
        </div>
        <span className={stateChipClass(snap.state)}>
          {STATE_LABELS[snap.state]}
        </span>
      </div>

      {/* Always-visible disclaimer */}
      <div className="mb-3 px-3 py-2 bg-bg-2 border-l-2 border-warning u-caption-2 text-fg-2">
        Shadow-preference only. Production routing unchanged.
      </div>

      {/* Snapshot summary */}
      <div className="mb-3 pb-3 border-b border-b1 grid grid-cols-2 md:grid-cols-4 gap-2 u-caption-2">
        <div>
          <div className="text-fg-3">ISO week</div>
          <div className="font-mono">{snap.iso_year}-W{String(snap.iso_week).padStart(2, "0")}</div>
        </div>
        <div>
          <div className="text-fg-3">as-of date</div>
          <div className="font-mono">{snap.as_of_date}</div>
        </div>
        <div>
          <div className="text-fg-3">divergent days</div>
          <div className="font-mono">{snap.n_divergent_days ?? "—"}</div>
        </div>
        <div>
          <div className="text-fg-3">edge bps</div>
          <div className="font-mono">{fmt(snap.edge_bps, 2)}</div>
        </div>
        <div>
          <div className="text-fg-3">impact-weighted edge</div>
          <div className="font-mono">{fmt(snap.impact_weighted_edge, 4)}</div>
        </div>
        <div>
          <div className="text-fg-3">prior state</div>
          <div className="font-mono">{snap.prior_state ?? "—"}</div>
        </div>
        <div>
          <div className="text-fg-3">comparison fetch</div>
          <div className={cn("font-mono",
              snap.comparison_fetch_ok ? "text-success" : "text-danger")}>
            {snap.comparison_fetch_ok ? "OK" : "FAIL"}
          </div>
        </div>
        <div>
          <div className="text-fg-3">tail-guard</div>
          <div className={cn("font-mono",
              snap.tail_guard_triggered ? "text-warning" : "text-fg")}>
            {snap.tail_guard_triggered ? "TRIGGERED" : "clear"}
          </div>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mb-3 pb-3 border-b border-b1">
        <ConfidenceBar
          total={snap.promotion_confidence}
          breakdown={(gatesData?.confidence_breakdown ?? {}) as ConfidenceBreakdown | Record<string, never>}
        />
      </div>

      {/* Streak strip */}
      <div className="mb-3 pb-3 border-b border-b1 space-y-1.5">
        <div className="u-label-sm mb-1">Streaks</div>
        <StreakDots
          current={snap.verdict_streak}
          required={4}
          label="Verdict (V2_BETTER)"
        />
        <StreakDots
          current={snap.readiness_streak}
          required={2}
          label="Readiness (STRONG)"
        />
      </div>

      {/* Gate breakdown */}
      <div className="mb-3 pb-3 border-b border-b1">
        <div className="u-label-sm mb-1.5">Gate breakdown</div>
        <table className="w-full">
          <thead>
            <tr className="text-fg-3">
              <th className="text-left u-caption-2 pb-1">gate</th>
              <th className="text-left u-caption-2 pb-1">status</th>
              <th className="text-left u-caption-2 pb-1">reason</th>
            </tr>
          </thead>
          <tbody>
            {gatesData
              ? Object.values(gatesData.gates).map((g) => (
                  <GateRow key={g.name} gate={g} />
                ))
              : (
                <tr>
                  <td colSpan={3} className="u-caption-2 text-fg-3 py-2">
                    loading gate detail…
                  </td>
                </tr>
              )}
          </tbody>
        </table>
      </div>

      {/* Rollback alert */}
      {snap.rollback_reason && (
        <div className="mb-3 px-3 py-2 bg-warning/10 border-l-2 border-warning u-caption-2 text-warning">
          ⚠ State rolled back from {snap.prior_state ?? "—"} to {snap.state} on {snap.as_of_date}: {snap.rollback_reason}
        </div>
      )}

      {/* Operator actions */}
      {(showApproveButton || showRescindButton) && (
        <div className="pt-2 flex justify-end gap-2">
          {showApproveButton && (
            <button
              type="button"
              onClick={() => setShowApproveModal(true)}
              className="u-btn u-btn-primary"
            >
              Approve Shadow Replacement…
            </button>
          )}
          {showRescindButton && (
            <button
              type="button"
              onClick={() => setShowRescindModal(true)}
              className="u-btn u-btn-danger"
            >
              Rescind Approval…
            </button>
          )}
        </div>
      )}

      {/* Modals */}
      {showApproveModal && snap && (
        <ApproveModal
          snapshot={snap}
          onClose={() => setShowApproveModal(false)}
        />
      )}
      {showRescindModal && snap && (
        <RescindModal
          approvedSnapshotId={approvedSnapshotId}
          onClose={() => setShowRescindModal(false)}
        />
      )}
    </div>
  );
}
